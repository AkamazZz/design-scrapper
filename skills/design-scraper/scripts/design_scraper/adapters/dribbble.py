from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..downloads import DownloadJob, infer_filename
from ..models import AssetRecord, ScrapeResult
from .base import ScrapeContext, SourceAdapter


def _meta(html: str, attr_name: str, attr_value: str) -> str | None:
    patterns = [
        rf'<meta[^>]+{attr_name}="[^"]*{re.escape(attr_value)}[^"]*"[^>]+content="([^"]+)"',
        rf"<meta[^>]+{attr_name}='[^']*{re.escape(attr_value)}[^']*'[^>]+content='([^']+)'",
        rf'<meta[^>]+content="([^"]+)"[^>]+{attr_name}="[^"]*{re.escape(attr_value)}[^"]*"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return unescape(match.group(1)).strip()
    return None


def _clean_dribbble_image(url: str) -> str:
    parsed = urlparse(url)
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key not in {"resize", "compress", "quality"}
    ]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(filtered), ""))


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "dribbble-asset"


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() or None


def _priority_for_candidate(candidate: str) -> tuple[str, int] | None:
    lower = urlparse(candidate).path.lower()
    if lower.endswith(".mp4"):
        return "video", 0
    if any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image", 1
    return None


def _extract_script_media_candidates(html: str, base_url: str) -> list[tuple[str, str, int]]:
    normalized_html = html.replace("\\/", "/")
    pattern = r"https?://cdn\.dribbble\.com/[^\"'\s<>]+"
    results: list[tuple[str, str, int]] = []
    seen = set()
    for match in re.finditer(pattern, normalized_html, flags=re.IGNORECASE):
        candidate = _clean_dribbble_image(urljoin(base_url, match.group(0)))
        info = _priority_for_candidate(candidate)
        if info is None or candidate in seen:
            continue
        seen.add(candidate)
        kind, priority = info
        results.append((candidate, kind, priority))
    return results


def _variant_rank(candidate: str, kind: str) -> tuple[int, int, str]:
    path = urlparse(candidate).path.lower()
    if kind == "video":
        if "/userupload/" in path and "/original-" in path:
            return (0, 0, path)
        if "/userupload/" in path and "/large-" in path:
            return (0, 1, path)
        if "/userupload/" in path and "/small-" in path:
            return (0, 2, path)
        if "/users/" in path and "/videos/" in path:
            return (0, 3, path)
        return (0, 4, path)

    if "/original-" in path:
        return (1, 0, path)
    if "/large-" in path:
        return (1, 1, path)
    if "/small-" in path:
        return (1, 2, path)
    return (1, 3, path)


def _select_best_candidates(media_candidates: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    deduped: dict[tuple[str, str], tuple[str, str, int]] = {}
    for candidate, kind, priority in media_candidates:
        key = (kind, candidate)
        current = deduped.get(key)
        if current is None or (priority, _variant_rank(candidate, kind)) < (current[2], _variant_rank(current[0], current[1])):
            deduped[key] = (candidate, kind, priority)

    ordered = sorted(
        deduped.values(),
        key=lambda item: (item[2], _variant_rank(item[0], item[1])),
    )

    best_videos = [item for item in ordered if item[1] == "video"][:3]
    best_images = [item for item in ordered if item[1] == "image"][:2]
    return best_videos + best_images


class DribbbleAdapter(SourceAdapter):
    name = "dribbble"

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
        result.title = _meta(html, "property", "og:title") or _extract_title(html)
        result.author = _meta(html, "name", "twitter:creator") or _meta(html, "property", "og:site_name")

        media_candidates: list[tuple[str, str, int]] = []
        seen = set()

        video_patterns = [
            r'<source[^>]+src="([^"]+\.mp4[^"]*)"',
            r"<source[^>]+src='([^']+\.mp4[^']*)'",
            r'<video[^>]+src="([^"]+\.mp4[^"]*)"',
            r"<video[^>]+src='([^']+\.mp4[^']*)'",
        ]
        for pattern in video_patterns:
            for match in re.finditer(pattern, html, flags=re.IGNORECASE):
                candidate = urljoin(url, match.group(1).strip())
                if candidate not in seen:
                    seen.add(candidate)
                    media_candidates.append((candidate, "video", 0))

        image_patterns = [
            r'<img[^>]+src="([^"]+)"',
            r"<img[^>]+src='([^']+)'",
        ]
        for pattern in image_patterns:
            for match in re.finditer(pattern, html, flags=re.IGNORECASE):
                candidate = match.group(1).strip()
                if not candidate or candidate.startswith("data:"):
                    continue
                candidate = _clean_dribbble_image(urljoin(url, candidate))
                lower = urlparse(candidate).path.lower()
                if not any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
                    continue
                if candidate not in seen:
                    seen.add(candidate)
                    media_candidates.append((candidate, "image", 1))

        for candidate, kind, priority in _extract_script_media_candidates(html, url):
            if candidate not in seen:
                seen.add(candidate)
                media_candidates.append((candidate, kind, priority))

        og_image = _meta(html, "property", "og:image")
        if og_image:
            og_image = _clean_dribbble_image(urljoin(url, og_image))
            if og_image not in seen:
                media_candidates.append((og_image, "image", 2))

        if not media_candidates:
            result.status = "no_media_found"
            result.warnings.append("No downloadable Dribbble media found in page HTML.")
            result.notes.append("A Playwright MCP extraction pass may be required for this shot.")
            return result

        selected = _select_best_candidates(media_candidates)
        stem = _safe_stem(result.title or infer_filename(url, "dribbble-shot"))
        kinds_by_url = {}
        jobs = []
        for index, (candidate, kind, _priority) in enumerate(selected, start=1):
            filename = infer_filename(candidate, f"{stem}-{index}")
            jobs.append(
                DownloadJob(
                    url=candidate,
                    destination=context.layout.raw_dir / self.name / filename,
                    source_url=url,
                )
            )
            kinds_by_url[candidate] = kind

        for download in context.downloader.download_all(jobs):
            if download.status == "failed":
                result.warnings.append(download.error or f"Failed to download {download.url}")
                continue
            result.assets.append(
                AssetRecord(
                    source_url=url,
                    canonical_url=download.url,
                    local_path=str(download.destination),
                    kind=kinds_by_url.get(download.url, "image"),
                    status=download.status,
                    mime_type=download.mime_type,
                    sha256=download.sha256,
                    file_size=download.file_size,
                )
            )

        result.status = "downloaded" if result.assets else "download_failed"
        if any(asset.kind == "video" for asset in result.assets):
            result.notes.append("Original MP4 was prioritized when present.")
        return result
