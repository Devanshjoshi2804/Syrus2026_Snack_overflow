from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from tempfile import NamedTemporaryFile

from onboardai.config import AppConfig


class BrowserAdapter(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, url: str) -> tuple[str, list[str]]:
        raise NotImplementedError


class MockBrowserAdapter(BrowserAdapter):
    def is_available(self) -> bool:
        return False

    def open_url(self, url: str) -> tuple[str, list[str]]:
        return (f"Opened {url}", [])


class PlaywrightBrowserAdapter(BrowserAdapter):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def is_available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.browser_headless)
                browser.close()
            return True
        except Exception:
            return False

    def open_url(self, url: str) -> tuple[str, list[str]]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.config.browser_headless)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            title = page.title()
            with NamedTemporaryFile(delete=False, suffix=".png", dir=Path("outputs/completion_reports")) as handle:
                page.screenshot(path=handle.name, full_page=True)
                screenshot_path = handle.name
            browser.close()
        return (f"Opened {url} with title '{title}'", [screenshot_path])


def build_browser_adapter(config: AppConfig) -> BrowserAdapter:
    if config.browser_backend == "playwright":
        adapter = PlaywrightBrowserAdapter(config)
        if adapter.is_available():
            return adapter
    return MockBrowserAdapter()
