from __future__ import annotations

import re
from urllib.parse import urljoin

from ..models import ScrapeResult
from .base import ScrapeContext, SourceAdapter
from .common import clean_url, download_assets, extract_meta, extract_script_urls, extract_title, media_kind, safe_stem


def _upgrade_app_store_image(url: str) -> str:
    upgraded = re.sub(r"/\d+x\d+bb", "/1290x2796bb", url)
    upgraded = re.sub(r"/\d+x\d+\w+\.", "/1290x2796bb.", upgraded)
    return clean_url(upgraded)


class AppStoreAdapter(SourceAdapter):
    name = "app_store"

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
        result.author = extract_meta(html, "name", "apple:developer") or extract_meta(html, "property", "og:site_name")

        candidates = []
        seen = set()
        for candidate in extract_script_urls(html, r"[^\"'/]*mzstatic\.com"):
            upgraded = _upgrade_app_store_image(urljoin(url, candidate))
            kind = media_kind(upgraded)
            if not kind or upgraded in seen:
                continue
            seen.add(upgraded)
            candidates.append((upgraded, kind))

        og_image = extract_meta(html, "property", "og:image")
        if og_image:
            upgraded = _upgrade_app_store_image(urljoin(url, og_image))
            if upgraded not in seen and media_kind(upgraded):
                candidates.append((upgraded, "image"))

        if not candidates:
            result.status = "no_media_found"
            result.warnings.append("No App Store screenshots found in page markup.")
            return result

        stem = safe_stem(result.title or "app-store")
        return download_assets(result, context, self.name, url, candidates[:10], stem)
