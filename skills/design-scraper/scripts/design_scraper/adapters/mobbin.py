from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ..fetchers import FetchWaitHint
from ..models import ScrapeResult
from .base import ScrapeContext, SourceAdapter
from .common import clean_url, download_assets, extract_meta, extract_script_urls, extract_title, media_kind, safe_stem


class MobbinAdapter(SourceAdapter):
    name = "mobbin"

    def matches(self, source: str | None, url: str) -> bool:
        return source == self.name

    def scrape(self, url: str, context: ScrapeContext) -> ScrapeResult:
        result = ScrapeResult(source=self.name, url=url, normalized_url=url, status="empty")
        headed = bool(
            getattr(getattr(context.fetcher, "launch_options", None), "headed", False)
        )
        wait_hint = FetchWaitHint(
            wait_until="domcontentloaded",
            timeout_ms=30000,
            selector_waits=(
                'img[src*="bytescale"]',
                'img[src*="app_screens"]',
            )
            if headed
            else (
                'img[src*="bytescale"]',
                'img[src*="app_screens"]',
                '[href*="/login"]',
                '[href*="/signup"]',
            ),
            selector_timeout_ms=4000,
            extra_delay_ms=1200,
        )
        try:
            fetched = context.fetcher.fetch(url, wait_hint=wait_hint)
        except OSError as exc:
            result.status = "fetch_failed"
            result.warnings.append(str(exc))
            return result

        html = fetched.html
        result.metadata.update(fetched.metadata or {})
        result.metadata["fetch_variant"] = fetched.variant
        if fetched.final_url:
            result.metadata["final_url"] = fetched.final_url
        result.title = extract_meta(html, "property", "og:title") or extract_title(html)

        final_url = (fetched.final_url or url).lower()
        auth_markers = (
            "/login",
            "/signup",
            "auth",
            "sign in",
            "log in",
            "sign up",
            "continue with google",
            "continue with apple",
        )
        if any(marker in final_url for marker in ("/login", "/signup", "/auth", "redirect_to=")) or (
            re.search(r"(log in|sign in|sign up|continue with google|continue with apple)", html, flags=re.IGNORECASE)
            and "app_screens" not in html
        ):
            result.status = "auth_required"
            result.warnings.append("Mobbin content appears to require an authenticated session.")
            result.notes.append("Authenticate in the Playwright-backed browser context and rerun.")
            return result

        candidates = []
        seen = set()
        for candidate in extract_script_urls(html, r"[^\"'/]*bytescale[^\"'/]*"):
            cleaned = clean_url(urljoin(url, candidate), {"watermark", "extend-bottom", "image"})
            if "app_screens" not in cleaned:
                continue
            screen_id = urlparse(cleaned).path.split("/")[-1]
            if screen_id in seen:
                continue
            seen.add(screen_id)
            kind = media_kind(cleaned)
            if kind:
                candidates.append((cleaned, kind))

        if not candidates:
            result.status = "no_media_found"
            result.warnings.append("No Mobbin screen assets found. A logged-in rendered fetch may be required.")
            return result

        stem = safe_stem(result.title or "mobbin")
        return download_assets(result, context, self.name, url, candidates[:12], stem)
