from __future__ import annotations

from typing import List, Dict


CHAT_SELECTOR = "a[data-qa^='chatik-open-chat-']"


async def collect_dialogs(page, limit: int = 20) -> List[Dict]:
    seen = set()
    result = []

    for _ in range(20):  # ограничение скролла
        items = page.locator(CHAT_SELECTOR)

        count = await items.count()

        for i in range(count):
            el = items.nth(i)

            try:
                href = await el.get_attribute("href")
                qa = await el.get_attribute("data-qa")
            except Exception:
                continue

            if not href or not qa:
                continue

            chat_id = qa.replace("chatik-open-chat-", "")

            if chat_id in seen:
                continue

            seen.add(chat_id)

            result.append({
                "chat_id": chat_id,
                "chat_url": href,
            })

            if len(result) >= limit:
                return result

        # скроллим вниз
        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(1000)

    return result
