from __future__ import annotations

import asyncio
import importlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .downloads import read_text_url


@dataclass
class FetchWaitHint:
    wait_until: str = "domcontentloaded"
    timeout_ms: int = 30000
    selector_waits: tuple[str, ...] = ()
    selector_timeout_ms: int = 5000
    extra_delay_ms: int = 0


@dataclass
class FetchResult:
    url: str
    html: str
    variant: str
    final_url: str | None = None
    metadata: dict[str, str] | None = None


@dataclass
class PlaywrightLaunchOptions:
    headed: bool = False
    user_data_dir: str | None = None


class HtmlFetcher(Protocol):
    variant: str

    def fetch(self, url: str, wait_hint: FetchWaitHint | None = None) -> FetchResult:
        ...


class HttpFetcher:
    variant = "http"

    def fetch(self, url: str, wait_hint: FetchWaitHint | None = None) -> FetchResult:
        return FetchResult(url=url, html=read_text_url(url), variant=self.variant, final_url=url, metadata={})


class PlaywrightFetcher:
    variant = "playwright"

    def __init__(
        self,
        fallback: HttpFetcher | None = None,
        allow_fallback: bool = False,
        launch_options: PlaywrightLaunchOptions | None = None,
    ):
        self.fallback = fallback or HttpFetcher()
        self.allow_fallback = allow_fallback
        self.launch_options = launch_options or PlaywrightLaunchOptions()

    def profile_warnings(self) -> list[str]:
        if not self.launch_options.user_data_dir:
            return []
        profile_dir = Path(self.launch_options.user_data_dir).expanduser()
        if not profile_dir.exists():
            return []
        mode = stat.S_IMODE(profile_dir.stat().st_mode)
        if mode & 0o077:
            return [
                f"Playwright profile directory {profile_dir} is accessible by group/others; restrict it to mode 700."
            ]
        return []

    def fetch(self, url: str, wait_hint: FetchWaitHint | None = None) -> FetchResult:
        wait_hint = wait_hint or FetchWaitHint()
        goto_timeout = 0 if self.launch_options.headed else wait_hint.timeout_ms
        selector_timeout = 0 if self.launch_options.headed else wait_hint.selector_timeout_ms
        try:
            sync_api = importlib.import_module("playwright.sync_api")
        except ModuleNotFoundError as exc:
            if not self.allow_fallback:
                raise OSError(
                    "Playwright was requested, but the Python Playwright package is not installed."
                ) from exc
            fallback_result = self.fallback.fetch(url, wait_hint)
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
        context = None
        try:
            with sync_playwright() as playwright:
                if self.launch_options.user_data_dir:
                    profile_dir = Path(self.launch_options.user_data_dir).expanduser()
                    profile_dir.mkdir(parents=True, exist_ok=True)
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=not self.launch_options.headed,
                    )
                    page = context.new_page()
                else:
                    browser = playwright.chromium.launch(headless=not self.launch_options.headed)
                    page = browser.new_page()
                page.goto(url, wait_until=wait_hint.wait_until, timeout=goto_timeout)
                for selector in wait_hint.selector_waits:
                    try:
                        page.wait_for_selector(selector, timeout=selector_timeout)
                        break
                    except Exception:
                        continue
                if wait_hint.extra_delay_ms > 0:
                    page.wait_for_timeout(wait_hint.extra_delay_ms)
                html = page.content()
                final_url = page.url
        except Exception as exc:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if not self.allow_fallback:
                raise OSError(f"Playwright fetch failed: {type(exc).__name__}: {exc}") from exc
            fallback_result = self.fallback.fetch(url, wait_hint)
            fallback_result.metadata = {
                **(fallback_result.metadata or {}),
                "requested_variant": self.variant,
                "effective_variant": self.fallback.variant,
                "fallback_reason": f"playwright_runtime_error:{type(exc).__name__}",
            }
            return fallback_result
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
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
                "wait_until": wait_hint.wait_until,
                "headed": str(self.launch_options.headed).lower(),
                **(
                    {"user_data_dir": str(Path(self.launch_options.user_data_dir).expanduser())}
                    if self.launch_options.user_data_dir
                    else {}
                ),
            },
        )


class Crawl4AIFetcher:
    variant = "crawl4ai"

    def fetch(self, url: str, wait_hint: FetchWaitHint | None = None) -> FetchResult:
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


def build_fetcher(
    variant: str,
    *,
    playwright_user_data_dir: str | None = None,
    playwright_headed: bool = False,
) -> HtmlFetcher:
    if variant == "playwright":
        return PlaywrightFetcher(
            launch_options=PlaywrightLaunchOptions(
                headed=playwright_headed,
                user_data_dir=playwright_user_data_dir,
            )
        )
    if variant == "crawl4ai":
        return Crawl4AIFetcher()
    if variant == "http":
        return HttpFetcher()
    raise ValueError(f"Unsupported fetch variant: {variant}")
