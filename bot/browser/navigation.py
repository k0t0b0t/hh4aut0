from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeoutError


async def safe_click(locator, timeout: int = 3000) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass
    try:
        await locator.click(timeout=timeout)
        return True
    except Exception:
        try:
            await locator.click(force=True, timeout=timeout)
            return True
        except Exception:
            return False


async def soft_wait(page, ms: int) -> None:
    try:
        await page.wait_for_timeout(ms)
    except PlaywrightTimeoutError:
        pass
