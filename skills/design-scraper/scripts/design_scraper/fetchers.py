from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from typing import Protocol

from .downloads import read_text_url


@dataclass
class FetchResult:
    url: str
    html: str
    variant: str
    final_url: str | None = None
    metadata: dict[str, str] | None = None


class HtmlFetcher(Protocol):
    variant: str

    def fetch(self, url: str) -> FetchResult:
        ...


class HttpFetcher:
    variant = "http"

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(url=url, html=read_text_url(url), variant=self.variant, final_url=url, metadata={})


class PlaywrightFetcher:
    variant = "playwright"

    def __init__(self, fallback: HttpFetcher | None = None, allow_fallback: bool = False):
        self.fallback = fallback or HttpFetcher()
        self.allow_fallback = allow_fallback

    def fetch(self, url: str) -> FetchResult:
        try:
            sync_api = importlib.import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            if not self.allow_fallback:
                raise OSError(
                    "Playwright was requested, but the Python Playwright package is not installed."
                ) from exc
            fallback_result = self.fallback.fetch(url)
            fallback_result.metadata = {
                **(fallback_result.metadata or {}),
                "requested_variant": self.variant,
                "effective_variant": self.fallback.variant,
                "fallback_reason": "python_playwright_not_installed",
            }
            return fallback_result

        sync_playwright = getattr(sync_api, "sync_playwright", None)
        if sync_playwright is None:
            raise OSError("playwright.sync_api is installed but sync_playwright is unavailable.")

        browser = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                final_url = page.url
        except Exception as exc:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if not self.allow_fallback:
                raise OSError(f"Playwright fetch failed: {type(exc).__name__}: {exc}") from exc
            fallback_result = self.fallback.fetch(url)
            fallback_result.metadata = {
                **(fallback_result.metadata or {}),
                "requested_variant": self.variant,
                "effective_variant": self.fallback.variant,
                "fallback_reason": f"playwright_runtime_error:{type(exc).__name__}",
            }
            return fallback_result
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

        return FetchResult(
            url=url,
            html=html,
            variant=self.variant,
            final_url=final_url,
            metadata={
                "requested_variant": self.variant,
                "effective_variant": self.variant,
            },
        )


class Crawl4AIFetcher:
    variant = "crawl4ai"

    def fetch(self, url: str) -> FetchResult:
        try:
            crawl4ai = importlib.import_module("crawl4ai")
        except ModuleNotFoundError as exc:
            raise OSError(
                "crawl4ai fetch variant was selected, but the `crawl4ai` package is not installed."
            ) from exc

        fetch_result = getattr(crawl4ai, "AsyncWebCrawler", None)
        if fetch_result is None:
            raise OSError(
                "crawl4ai is installed but AsyncWebCrawler is unavailable in this runtime."
            )

        async def _run() -> FetchResult:
            async with fetch_result() as crawler:
                result = await crawler.arun(url=url)
            html = getattr(result, "html", None) or getattr(result, "cleaned_html", None)
            if not html:
                raise OSError("crawl4ai completed but did not return HTML content.")
            final_url = getattr(result, "url", None) or getattr(result, "final_url", None) or url
            return FetchResult(
                url=url,
                html=html,
                variant=self.variant,
                final_url=final_url,
                metadata={
                    "requested_variant": self.variant,
                    "effective_variant": self.variant,
                },
            )

        try:
            return asyncio.run(_run())
        except RuntimeError as exc:
            raise OSError(f"crawl4ai runtime error: {exc}") from exc


def build_fetcher(variant: str) -> HtmlFetcher:
    if variant == "playwright":
        return PlaywrightFetcher()
    if variant == "crawl4ai":
        return Crawl4AIFetcher()
    if variant == "http":
        return HttpFetcher()
    raise ValueError(f"Unsupported fetch variant: {variant}")
