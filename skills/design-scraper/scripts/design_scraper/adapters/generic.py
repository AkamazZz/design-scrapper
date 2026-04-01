from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse

from ..downloads import DownloadJob, infer_filename
from ..models import AssetRecord, ScrapeResult
from .base import ScrapeContext, SourceAdapter


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() or None


def _extract_meta(html: str, attr_name: str, attr_value: str) -> str | None:
    patterns = [
        rf'<meta[^>]+{attr_name}="{re.escape(attr_value)}"[^>]+content="([^"]+)"',
        rf"<meta[^>]+{attr_name}='{re.escape(attr_value)}'[^>]+content='([^']+)'",
        rf'<meta[^>]+content="([^"]+)"[^>]+{attr_name}="{re.escape(attr_value)}"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return unescape(match.group(1)).strip()
    return None


def _extract_media_urls(html: str, base_url: str) -> list[str]:
    candidates = set()
    patterns = [
        r'<source[^>]+src="([^"]+)"',
        r"<source[^>]+src='([^']+)'",
        r'<video[^>]+src="([^"]+)"',
        r"<video[^>]+src='([^']+)'",
        r'<img[^>]+src="([^"]+)"',
        r"<img[^>]+src='([^']+)'",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.IGNORECASE):
            raw = match.group(1).strip()
            if not raw or raw.startswith("data:"):
                continue
            absolute = urljoin(base_url, raw)
            path = urlparse(absolute).path.lower()
            if any(path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov")):
                candidates.add(absolute)
    return sorted(candidates)


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "asset"


class DirectMediaAdapter(SourceAdapter):
    name = "direct_media"
    generic = True

    def matches(self, source: str | None, url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

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
        result.title = _extract_title(html)
        media_urls = _extract_media_urls(html, url)
        if not media_urls:
            result.status = "no_media_found"
            result.warnings.append("No direct media URLs found in page markup.")
            return result

        jobs = []
        stem = _safe_stem(result.title or urlparse(url).netloc)
        for index, media_url in enumerate(media_urls[:6], start=1):
            filename = infer_filename(media_url, f"{stem}-{index}")
            jobs.append(
                DownloadJob(
                    url=media_url,
                    destination=context.layout.raw_dir / "generic" / filename,
                    source_url=url,
                )
            )

        for download in context.downloader.download_all(jobs):
            if download.status == "failed":
                result.warnings.append(download.error or f"Failed to download {download.url}")
                continue
            kind = "video" if (download.mime_type or "").startswith("video/") or download.destination.suffix.lower() == ".mp4" else "image"
            result.assets.append(
                AssetRecord(
                    source_url=url,
                    canonical_url=download.url,
                    local_path=str(download.destination),
                    kind=kind,
                    status=download.status,
                    mime_type=download.mime_type,
                    sha256=download.sha256,
                    file_size=download.file_size,
                )
            )

        result.status = "downloaded" if result.assets else "download_failed"
        return result


class OpenGraphAdapter(SourceAdapter):
    name = "open_graph"
    generic = True

    def matches(self, source: str | None, url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

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
        result.title = _extract_meta(html, "property", "og:title") or _extract_title(html)
        og_image = _extract_meta(html, "property", "og:image") or _extract_meta(html, "name", "og:image")
        if not og_image:
            result.status = "no_media_found"
            result.warnings.append("No og:image found on page.")
            return result

        filename = infer_filename(og_image, f"{_safe_stem(result.title or 'og-image')}.bin")
        destination = context.layout.raw_dir / "generic" / filename
        download = context.downloader.download_all(
            [DownloadJob(url=urljoin(url, og_image), destination=destination, source_url=url)]
        )[0]

        if download.status == "failed":
            result.status = "download_failed"
            result.warnings.append(download.error or "Download failed")
            return result

        result.status = "downloaded"
        result.assets.append(
            AssetRecord(
                source_url=url,
                canonical_url=download.url,
                local_path=str(download.destination),
                kind="image",
                status=download.status,
                mime_type=download.mime_type,
                sha256=download.sha256,
                file_size=download.file_size,
            )
        )
        return result
