from __future__ import annotations

import hashlib
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; design-scraper/1.0)",
    "Accept": "*/*",
}


@dataclass
class DownloadJob:
    url: str
    destination: Path
    source_url: str
    fallback_screenshot: bool = False


@dataclass
class DownloadResult:
    url: str
    destination: Path
    status: str
    sha256: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    from_cache: bool = False


def infer_filename(url: str, default_stem: str = "asset") -> str:
    name = Path(urlparse(url).path).name
    return name or default_stem


def read_text_url(url: str, timeout: int = 30) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise OSError(f"Failed to fetch {url}: {exc}") from exc


def _download_one(job: DownloadJob, retries: int, timeout: int) -> DownloadResult:
    job.destination.parent.mkdir(parents=True, exist_ok=True)
    if job.destination.exists():
        file_bytes = job.destination.read_bytes()
        return DownloadResult(
            url=job.url,
            destination=job.destination,
            status="cached",
            sha256=hashlib.sha256(file_bytes).hexdigest(),
            file_size=len(file_bytes),
            mime_type=mimetypes.guess_type(job.destination.name)[0],
            from_cache=True,
        )

    request = Request(job.url, headers=DEFAULT_HEADERS)
    last_error = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                data = response.read()
                job.destination.write_bytes(data)
                return DownloadResult(
                    url=job.url,
                    destination=job.destination,
                    status="downloaded",
                    sha256=hashlib.sha256(data).hexdigest(),
                    file_size=len(data),
                    mime_type=response.headers.get_content_type(),
                )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))

    return DownloadResult(
        url=job.url,
        destination=job.destination,
        status="failed",
        error=last_error,
    )


class DownloadManager:
    def __init__(self, max_workers: int = 4, retries: int = 2, timeout: int = 30):
        self.max_workers = max_workers
        self.retries = retries
        self.timeout = timeout

    def download_all(self, jobs: Iterable[DownloadJob]) -> list[DownloadResult]:
        jobs = list(jobs)
        if not jobs:
            return []

        results: list[DownloadResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(_download_one, job, self.retries, self.timeout): job
                for job in jobs
            }
            for future in as_completed(future_map):
                results.append(future.result())
        return results
