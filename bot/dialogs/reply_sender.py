from __future__ import annotations


TEXTAREA_SELECTOR = "[data-qa='chatik-new-message-text']"
SEND_BUTTON_SELECTOR = "[data-qa='chatik-do-send-message']"


async def fill_reply_text(page, text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False

    loc = page.locator(TEXTAREA_SELECTOR)
    if await loc.count() == 0:
        return False

    textarea = loc.first

    try:
        await textarea.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass

    try:
        await textarea.fill(text)
        await page.wait_for_timeout(250)
        return True
    except Exception:
        pass

    try:
        await textarea.click(timeout=1500)
    except Exception:
        pass

    try:
        await textarea.evaluate(
            """(el, value) => {
                if ('value' in el) {
                    el.value = value;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                } else {
                    el.textContent = value;
                }
            }""",
            text,
        )
        await page.wait_for_timeout(250)
        return True
    except Exception:
        return False


async def click_send(page) -> tuple[bool, str]:
    loc = page.locator(SEND_BUTTON_SELECTOR)
    if await loc.count() == 0:
        return False, "send_button_not_found"

    btn = loc.first

    try:
        await btn.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass

    try:
        await btn.click(timeout=2500)
        await page.wait_for_timeout(1200)
        return True, "sent"
    except Exception:
        try:
            await btn.click(force=True, timeout=2500)
            await page.wait_for_timeout(1200)
            return True, "sent_force"
        except Exception as exc:
            return False, f"send_click_failed:{exc}"


def ask_send_decision() -> str:
    return input("send? [yes/no/skip]: ").strip().lower()
