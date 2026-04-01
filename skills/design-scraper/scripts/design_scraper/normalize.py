from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


SUPPORTED_SOURCES: dict[str, tuple[str, ...]] = {
    "dribbble": ("dribbble.com",),
    "mobbin": ("mobbin.com",),
    "app_store": ("apps.apple.com",),
    "behance": ("behance.net", "www.behance.net"),
    "pinterest": ("pinterest.com", "www.pinterest.com"),
    "awwwards": ("awwwards.com", "www.awwwards.com"),
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if not k.lower().startswith("utm_")]
    query = urlencode(sorted(query_items))
    return urlunparse((scheme, netloc, path, "", query, ""))


def detect_source(url: str) -> str | None:
    netloc = urlparse(url).netloc.lower()
    for source, hosts in SUPPORTED_SOURCES.items():
        if netloc in hosts:
            return source
    return None

