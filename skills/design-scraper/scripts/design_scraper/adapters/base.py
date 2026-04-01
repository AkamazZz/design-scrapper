from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..downloads import DownloadManager
from ..fetchers import HtmlFetcher
from ..models import OutputLayout, ScrapeResult


@dataclass
class ScrapeContext:
    layout: OutputLayout
    project: str | None
    tags: list[str]
    run_id: str
    downloader: DownloadManager
    fetcher: HtmlFetcher


class SourceAdapter:
    name = "unknown"
    generic = False

    def matches(self, source: str | None, url: str) -> bool:
        return source == self.name

    def scrape(self, url: str, context: ScrapeContext) -> ScrapeResult:
        raise NotImplementedError


class PlaceholderAdapter(SourceAdapter):
    def __init__(self, name: str):
        self.name = name

    def scrape(self, url: str, context: ScrapeContext) -> ScrapeResult:
        raw_hint = str(Path(context.layout.raw_dir, self.name))
        result = ScrapeResult(
            source=self.name,
            url=url,
            normalized_url=url,
            status="not_implemented",
            warnings=[f"{self.name} adapter is not implemented yet."],
            notes=[f"Reserved output directory: {raw_hint}"],
        )
        return result


class AdapterRegistry:
    def __init__(self, adapters: list[SourceAdapter]):
        self.adapters = adapters

    def select(self, source: str | None, url: str) -> SourceAdapter | None:
        for adapter in self.adapters:
            if not adapter.generic and adapter.matches(source, url):
                return adapter
        for adapter in self.adapters:
            if adapter.generic and adapter.matches(source, url):
                return adapter
        return None
