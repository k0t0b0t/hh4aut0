from __future__ import annotations

import re
from typing import Any

from bot.browser.navigation import safe_click

FORM_FIELD_SELECTOR = "textarea, input, select, [contenteditable='true']"

FORM_ROOT_CANDIDATES = [
    "form#RESPONSE_MODAL_FORM_ID",
    "form[id^='cover-letter-']",
    "form[action*='/applicant/vacancy_response/']",
    "[data-qa='vacancy-response-letter-form']",
    "[data-qa='vacancy-response-popup'] form",
    "[data-qa='vacancy-response-popup']",
    "[role='dialog'] form",
    "[role='dialog']",
    ".bloko-modal form",
    ".bloko-modal",
]

APPLY_BUTTON_RE = re.compile(r"(откликнуться|отклик|apply|respond)", re.I)
NEXT_BUTTON_RE = re.compile(r"(далее|продолжить|next|continue)", re.I)
SUBMIT_BUTTON_RE = re.compile(r"(отправить|submit|send|apply|откликнуться)", re.I)

NEGATIVE_BUTTON_RE = re.compile(r"(отмена|cancel|закрыть|close|назад|back)", re.I)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


async def detect_already_applied_on_page(page) -> dict[str, Any]:
    checks = [
        ("already_applied_text", page.locator("text=Вы откликнулись")),
        ("already_applied_text_2", page.locator("text=Вы уже откликались")),
        ("already_applied_text_3", page.locator("text=Отклик отправлен")),
        ("repeat_apply_text", page.locator("text=Откликнуться повторно")),
    ]

    found = []
    for name, locator in checks:
        try:
            if await locator.count() > 0:
                found.append(name)
        except Exception:
            pass

    return {
        "already_applied": len(found) > 0,
        "signals": found,
    }


async def _visible_field_count(locator) -> int:
    try:
        fields = locator.locator(FORM_FIELD_SELECTOR)
        total = await fields.count()
    except Exception:
        return 0

    visible = 0
    for i in range(min(total, 50)):
        el = fields.nth(i)
        try:
            if await el.is_visible():
                visible += 1
        except Exception:
            continue
    return visible


async def find_active_form_root(page):
    best = None
    best_score = -1
    best_selector = None

    for sel in FORM_ROOT_CANDIDATES:
        loc = page.locator(sel)
        try:
            count = await loc.count()
        except Exception:
            continue

        for i in range(min(count, 10)):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue
                score = await _visible_field_count(el)
            except Exception:
                continue

            if score > best_score:
                best = el
                best_score = score
                best_selector = sel

    if best is not None:
        return best, best_selector

    return None, None


async def _visible_button_candidates(container) -> list[tuple[Any, str]]:
    out: list[tuple[Any, str]] = []
    loc = container.locator("button, a, [role='button']")
    try:
        count = await loc.count()
    except Exception:
        return out

    for i in range(min(count, 40)):
        el = loc.nth(i)
        try:
            if not await el.is_visible():
                continue
            txt = _norm(await el.inner_text())
        except Exception:
            continue

        if not txt:
            continue
        out.append((el, txt))

    return out


async def _candidate_roots(page) -> list[Any]:
    selectors = [
        "form#RESPONSE_MODAL_FORM_ID",
        "form[id^='cover-letter-']",
        "form[action*='/applicant/vacancy_response/']",
        "[data-qa='vacancy-response-letter-form']",
        "[data-qa='vacancy-response-popup'] form",
        "[data-qa='vacancy-response-popup']",
        "[role='dialog'] form",
        "[role='dialog']",
        ".bloko-modal form",
        ".bloko-modal",
        "main",
        "body",
    ]
    roots = []
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if await loc.count() > 0:
                roots.append(loc.first)
        except Exception:
            continue
    return roots


async def screen_fingerprint(page) -> str:
    root, _ = await find_active_form_root(page)
    probe = root if root is not None else page.locator("body").first
    try:
        text = await probe.inner_text()
    except Exception:
        try:
            text = await page.locator("body").inner_text()
        except Exception:
            text = ""
    return _norm(text)[:4000]


async def click_with_postcheck(page, locator, *, expected: str, timeout: int = 5000) -> dict[str, Any]:
    before = await screen_fingerprint(page)

    ok = await safe_click(locator, timeout=timeout)
    if not ok:
        return {
            "ok": False,
            "clicked": False,
            "screen_changed": False,
            "form_opened": False,
            "submitted": False,
            "reason": "click_failed",
        }

    await page.wait_for_timeout(1600)

    after = await screen_fingerprint(page)
    changed = before != after

    form_opened = False
    try:
        root, _ = await find_active_form_root(page)
        if root is not None:
            field_count = await root.locator(FORM_FIELD_SELECTOR).count()
            form_opened = field_count > 0
        else:
            form_opened = await page.locator(FORM_FIELD_SELECTOR).count() > 0
    except Exception:
        pass

    submitted = False
    try:
        post = await detect_already_applied_on_page(page)
        submitted = bool(post.get("already_applied"))
    except Exception:
        pass

    if expected == "apply_opened":
        success = form_opened or changed
    elif expected == "screen_changed":
        success = changed or form_opened
    elif expected == "submitted":
        success = submitted or changed
    else:
        success = changed or form_opened or submitted

    return {
        "ok": success,
        "clicked": True,
        "screen_changed": changed,
        "form_opened": form_opened,
        "submitted": submitted,
        "reason": "ok" if success else f"{expected}_not_confirmed",
    }


async def find_apply_locator(page):
    explicit = [
        page.locator("[data-qa='vacancy-response-link-top']"),
        page.locator("[data-qa='vacancy-response-link-bottom']"),
        page.locator("form#RESPONSE_MODAL_FORM_ID button:has-text('Откликнуться')"),
        page.locator("[role='dialog'] button:has-text('Откликнуться')"),
        page.locator("main a:has-text('Откликнуться')"),
        page.locator("main button:has-text('Откликнуться')"),
        page.locator("a:has-text('Откликнуться')"),
        page.locator("button:has-text('Откликнуться')"),
    ]

    for locator in explicit:
        try:
            count = await locator.count()
            for i in range(min(count, 8)):
                el = locator.nth(i)
                try:
                    if await el.is_visible():
                        return el
                except Exception:
                    continue
        except Exception:
            continue

    for root in await _candidate_roots(page):
        for el, txt in await _visible_button_candidates(root):
            low = txt.lower()
            if NEGATIVE_BUTTON_RE.search(low):
                continue
            if APPLY_BUTTON_RE.search(low):
                return el

    return None


async def find_next_locator(page, preferred_text: str | None = None):
    for root in await _candidate_roots(page):
        items = await _visible_button_candidates(root)

        if preferred_text:
            for el, txt in items:
                if preferred_text.lower() in txt.lower():
                    return el

        for el, txt in items:
            low = txt.lower()
            if NEGATIVE_BUTTON_RE.search(low):
                continue
            if NEXT_BUTTON_RE.search(low):
                return el

    return None


async def find_submit_locator(page, preferred_text: str | None = None):
    explicit = [
        page.locator("[data-qa='vacancy-response-letter-submit']"),
        page.locator("form[id^='cover-letter-'] button[type='submit']"),
        page.locator("form[action*='/applicant/vacancy_response/'] button[type='submit']"),
        page.locator("[role='dialog'] button[type='submit']"),
        page.locator("button[type='submit']"),
    ]

    for locator in explicit:
        try:
            count = await locator.count()
            for i in range(min(count, 8)):
                el = locator.nth(i)
                try:
                    if await el.is_visible():
                        return el
                except Exception:
                    continue
        except Exception:
            continue

    for root in await _candidate_roots(page):
        items = await _visible_button_candidates(root)

        if preferred_text:
            for el, txt in items:
                if preferred_text.lower() in txt.lower():
                    return el

        for el, txt in items:
            low = txt.lower()
            if NEGATIVE_BUTTON_RE.search(low):
                continue
            if NEXT_BUTTON_RE.search(low):
                continue
            if SUBMIT_BUTTON_RE.search(low):
                return el

    return None
