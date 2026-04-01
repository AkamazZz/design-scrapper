from __future__ import annotations

from urllib.parse import urljoin

from ..models import ScrapeResult
from .base import ScrapeContext, SourceAdapter
from .common import clean_url, download_assets, extract_meta, extract_script_urls, extract_title, media_kind, safe_stem


class PinterestAdapter(SourceAdapter):
    name = "pinterest"

    def matches(self, source: str | None, url: str) -> bool:
        return source == self.name

    def scrape(self, url: str, context: ScrapeContext) -> ScrapeResult:
        result = ScrapeResult(source=self.name, url=url, normalized_url=url, status="empty")
        try:
            fetched = context.fetcher.fetch(url)
        except OSError as exc:
            result.status = "fetch_failed"
            result.warnings.append(str(exc))
            return result

        html = fetched.html
        result.metadata.update(fetched.metadata or {})
        result.metadata["fetch_variant"] = fetched.variant
        result.title = extract_meta(html, "property", "og:title") or extract_title(html)

        candidates = []
        seen = set()
        for candidate in extract_script_urls(html, r"[^\"'/]*pinimg\.com"):
            absolute = clean_url(urljoin(url, candidate))
            if "/236x/" in absolute or "/60x60/" in absolute or "/75x75/" in absolute:
                continue
            kind = media_kind(absolute)
            if not kind or absolute in seen:
                continue
            seen.add(absolute)
            candidates.append((absolute, kind))

        og_image = extract_meta(html, "property", "og:image")
        if og_image:
            absolute = clean_url(urljoin(url, og_image))
            if absolute not in seen and media_kind(absolute):
                candidates.append((absolute, "image"))

        if not candidates:
            result.status = "no_media_found"
            result.warnings.append("No Pinterest pin media found in page markup.")
            return result

        stem = safe_stem(result.title or "pinterest")
        return download_assets(result, context, self.name, url, candidates[:8], stem)
