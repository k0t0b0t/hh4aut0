from __future__ import annotations

from playwright.async_api import async_playwright, Browser, Page


class BrowserSession:
    def __init__(self, cdp_url: str, goto_timeout_ms: int):
        self.cdp_url = cdp_url
        self.goto_timeout_ms = goto_timeout_ms
        self._pw = None
        self.browser: Browser | None = None
        self.page: Page | None = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
        pages = []
        for ctx in self.browser.contexts:
            pages.extend(ctx.pages)
        if pages:
            self.page = pages[0]
        elif self.browser.contexts:
            self.page = await self.browser.contexts[0].new_page()
        else:
            raise RuntimeError("Нет доступных browser contexts в CDP браузере")
        self.page.set_default_timeout(self.goto_timeout_ms)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._pw:
            await self._pw.stop()

    async def goto(self, url: str):
        assert self.page is not None
        await self.page.goto(url, wait_until="domcontentloaded", timeout=self.goto_timeout_ms)
        await self.page.wait_for_timeout(1800)
        return self.page
