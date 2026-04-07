from __future__ import annotations

import re

from bot.browser.navigation import safe_click


WARNING_TEXT_RE = re.compile(
    r"(в другой стране|другой стране|другом регионе|другой регион|"
    r"удал[её]нн|remote|релокац|"
    r"вы уверены|точно хотите откликнуться|"
    r"не подходит по локации|не совпада(ет|ют) по локации|"
    r"работа вне|готовы к релокации|готовы рассматривать)",
    re.I,
)

CONFIRM_BUTTON_RE = re.compile(
    r"(все\s*равно\s*откликнуться|всё\s*равно\s*откликнуться|"
    r"продолжить|да\b|подтвердить|apply|continue|confirm|yes\b)",
    re.I,
)

NEGATIVE_BUTTON_RE = re.compile(
    r"(отмена|cancel|закрыть|close|назад|back|нет\b|no\b|отменить)",
    re.I,
)

FORBIDDEN_BUTTON_RE = re.compile(
    r"(создать\s+резюме|resume|"
    r"укажу\s+профессию|ищу\s+любую\s+работу|не\s+знаю,\s*кем\s+хочу\s+работать|"
    r"резюме\s+и\s+профиль|отклики|сервисы|карьера|помощь|поиск)",
    re.I,
)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def _page_text(page) -> str:
    candidates = [
        page.locator("[role='dialog']").first,
        page.locator(".bloko-modal").first,
        page.locator("[data-qa='vacancy-response-popup']").first,
        page.locator("body").first,
    ]
    parts: list[str] = []
    for loc in candidates:
        try:
            if await loc.count() > 0 and await loc.is_visible():
                txt = await loc.inner_text()
                txt = _norm(txt)
                if txt:
                    parts.append(txt[:4000])
        except Exception:
            continue
    return " | ".join(parts)


async def _try_click_first_visible(locators, page, reason: str):
    for loc in locators:
        try:
            count = await loc.count()
        except Exception:
            continue

        for i in range(min(count, 8)):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue

                txt = ""
                try:
                    txt = _norm(await el.inner_text())
                except Exception:
                    pass

                if txt and FORBIDDEN_BUTTON_RE.search(txt):
                    continue
                if txt and NEGATIVE_BUTTON_RE.search(txt):
                    continue

                ok = await safe_click(el, timeout=3000)
                if ok:
                    await page.wait_for_timeout(1500)
                    return {
                        "handled": True,
                        "reason": reason,
                        "button_text": txt,
                    }
            except Exception:
                continue
    return None


async def handle_pre_apply_warning(page) -> dict:
    # 1. Сначала ловим точный HH-специфичный confirm
    exact_candidates = [
        page.locator("[data-qa='relocation-warning-confirm']"),
        page.locator("button[data-qa='relocation-warning-confirm']"),
        page.locator("[data-qa='relocation-warning-confirm'] button"),
    ]
    exact = await _try_click_first_visible(exact_candidates, page, "confirm_clicked_by_dataqa")
    if exact:
        exact["warning_preview"] = "matched by data-qa=relocation-warning-confirm"
        return exact

    text = await _page_text(page)

    relocation_scope = page.locator("[data-qa='relocation-warning-confirm'], [data-qa='relocation-warning-cancel']")
    try:
        relocation_present = await relocation_scope.count() > 0
    except Exception:
        relocation_present = False

    if not relocation_present and (not text or not WARNING_TEXT_RE.search(text)):
        return {"handled": False, "reason": "warning_not_detected"}

    # 2. По тексту ищем только явные confirm-кнопки
    text_candidates = [
        page.get_by_role("button", name="Все равно откликнуться", exact=False),
        page.get_by_text("Все равно откликнуться", exact=False),
        page.get_by_role("button", name="Всё равно откликнуться", exact=False),
        page.get_by_text("Всё равно откликнуться", exact=False),
        page.get_by_role("button", name="Продолжить", exact=False),
        page.get_by_text("Продолжить", exact=False),
        page.get_by_role("button", name="Подтвердить", exact=False),
        page.get_by_text("Подтвердить", exact=False),
        page.locator("button:has-text('Все равно откликнуться')"),
        page.locator("button:has-text('Всё равно откликнуться')"),
        page.locator("button:has-text('Продолжить')"),
        page.locator("button:has-text('Подтвердить')"),
    ]

    clicked = await _try_click_first_visible(text_candidates, page, "confirm_clicked_by_text")
    if clicked:
        clicked["warning_preview"] = text[:500]
        return clicked

    # 3. Последний резерв — только внутри modal/dialog/popup, не по body
    roots = [
        page.locator("[role='dialog']").first,
        page.locator(".bloko-modal").first,
        page.locator("[data-qa='vacancy-response-popup']").first,
    ]

    for root in roots:
        try:
            if await root.count() == 0 or not await root.is_visible():
                continue
        except Exception:
            continue

        buttons = root.locator("button, a, [role='button']")
        try:
            count = await buttons.count()
        except Exception:
            continue

        for i in range(min(count, 40)):
            el = buttons.nth(i)
            try:
                if not await el.is_visible():
                    continue
                txt = _norm(await el.inner_text())
                if not txt:
                    continue
                if FORBIDDEN_BUTTON_RE.search(txt):
                    continue
                if NEGATIVE_BUTTON_RE.search(txt):
                    continue
                if not CONFIRM_BUTTON_RE.search(txt):
                    continue

                ok = await safe_click(el, timeout=3000)
                if ok:
                    await page.wait_for_timeout(1500)
                    return {
                        "handled": True,
                        "reason": "confirm_clicked_fallback",
                        "button_text": txt,
                        "warning_preview": text[:500],
                    }
            except Exception:
                continue

    return {
        "handled": False,
        "reason": "confirm_button_not_found",
        "warning_preview": text[:500],
    }
