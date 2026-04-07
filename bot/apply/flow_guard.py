from __future__ import annotations

import re


SUBMIT_RE = re.compile(r"(отправить|submit|send|откликнуться|apply)", re.I)


async def is_in_apply_flow(page) -> dict:
    # 1. URL-based fast path
    try:
        url = page.url or ""
    except Exception:
        url = ""

    if "applicant/vacancy_response" in url:
        return {"ok": True, "reason": "url_vacancy_response", "url": url}

    selectors = [
        "form#RESPONSE_MODAL_FORM_ID",
        "form[id^='cover-letter-']",
        "[data-qa='vacancy-response-popup']",
        "[data-qa='vacancy-response-popup'] form",
        "[role='dialog'] form",
    ]

    # 2. Strong DOM selectors
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                return {"ok": True, "reason": f"selector:{sel}", "url": url}
        except Exception:
            continue

    # 3. Generic form/dialog content check
    roots = [
        page.locator("form"),
        page.locator("[role='dialog']"),
        page.locator(".bloko-modal"),
    ]

    for root in roots:
        try:
            count = await root.count()
        except Exception:
            continue

        for i in range(min(count, 8)):
            el = root.nth(i)
            try:
                if not await el.is_visible():
                    continue
            except Exception:
                continue

            try:
                has_textarea = await el.locator("textarea").count() > 0
                has_radio = await el.locator("input[type='radio']").count() > 0
                has_select = await el.locator("select").count() > 0
            except Exception:
                has_textarea = has_radio = has_select = False

            has_submit_button = False
            try:
                buttons = el.locator("button, a, [role='button']")
                bcount = await buttons.count()
                for j in range(min(bcount, 10)):
                    b = buttons.nth(j)
                    try:
                        if not await b.is_visible():
                            continue
                        txt = (await b.inner_text()).strip()
                        if txt and SUBMIT_RE.search(txt):
                            has_submit_button = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if has_textarea or has_radio or has_select or has_submit_button:
                return {
                    "ok": True,
                    "reason": "generic_form_or_dialog_content",
                    "url": url,
                    "has_textarea": has_textarea,
                    "has_radio": has_radio,
                    "has_select": has_select,
                    "has_submit_button": has_submit_button,
                }

    return {"ok": False, "reason": "apply_flow_not_detected", "url": url}
