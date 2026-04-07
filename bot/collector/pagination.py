from __future__ import annotations

from bot.browser.navigation import safe_click


async def try_ui_pagination_click(page, page_num: int) -> bool:
    candidates = [
        page.get_by_role("link", name=str(page_num + 1)),
        page.get_by_role("button", name=str(page_num + 1)),
        page.locator(f"a:text-is('{page_num + 1}')"),
    ]
    for loc in candidates:
        try:
            count = await loc.count()
            for i in range(min(count, 3)):
                if await safe_click(loc.nth(i)):
                    await page.wait_for_timeout(1800)
                    return True
        except Exception:
            continue
    return False
