from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from ..downloads import DownloadJob, infer_filename
from ..models import AssetRecord, ScrapeResult
from .base import ScrapeContext


def extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() or None


def extract_meta(html: str, attr_name: str, attr_value: str) -> str | None:
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


def safe_stem(value: str, default: str = "asset") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or default


def clean_url(url: str, drop_params: set[str] | None = None) -> str:
    parsed = urlparse(url)
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not drop_params or key not in drop_params
    ]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(filtered), ""))


def media_kind(candidate: str) -> str | None:
    lower = urlparse(candidate).path.lower()
    if lower.endswith((".mp4", ".mov")):
        return "video"
    if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    return None


def extract_absolute_media_urls(html: str, base_url: str) -> list[str]:
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
            if media_kind(absolute):
                candidates.add(absolute)
    return sorted(candidates)


def extract_script_urls(html: str, domain_pattern: str) -> list[str]:
    normalized_html = html.replace("\\/", "/")
    pattern = rf"https?://{domain_pattern}/[^\"'\s<>]+"
    return sorted(set(re.findall(pattern, normalized_html, flags=re.IGNORECASE)))


def download_assets(
    result: ScrapeResult,
    context: ScrapeContext,
    source_dir: str,
    source_url: str,
    candidates: list[tuple[str, str]],
    stem: str,
) -> ScrapeResult:
    jobs = []
    kinds_by_url: dict[str, str] = {}
    for index, (candidate, kind) in enumerate(candidates, start=1):
        filename = infer_filename(candidate, f"{stem}-{index}")
        jobs.append(
            DownloadJob(
                url=candidate,
                destination=context.layout.raw_dir / source_dir / filename,
                source_url=source_url,
            )
        )
        kinds_by_url[candidate] = kind

    for download in context.downloader.download_all(jobs):
        if download.status == "failed":
            result.warnings.append(download.error or f"Failed to download {download.url}")
            continue
        result.assets.append(
            AssetRecord(
                source_url=source_url,
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
    return result
