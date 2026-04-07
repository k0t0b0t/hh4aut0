from __future__ import annotations

import re

from bot.apply.click_logic import FORM_FIELD_SELECTOR, click_with_postcheck, find_active_form_root
from bot.apply.detectors import find_next_locator, find_submit_locator


FIELD_REF_RE = re.compile(r"^F(\d+)$", re.I)


async def _visible_form_fields(container):
    try:
        loc = container.locator(FORM_FIELD_SELECTOR)
        count = await loc.count()
    except Exception:
        return []

    out = []
    for i in range(min(count, 200)):
        el = loc.nth(i)
        try:
            if await el.is_visible():
                out.append(el)
        except Exception:
            continue
    return out


async def _resolve_field_ref(page, target: str):
    m = FIELD_REF_RE.match((target or "").strip())
    if not m:
        return None

    raw_index = int(m.group(1))
    containers = []

    try:
        root, _ = await find_active_form_root(page)
        if root is not None:
            containers.append(root)
    except Exception:
        pass

    containers.append(page)

    for container in containers:
        fields = await _visible_form_fields(container)
        if not fields:
            continue

        if 1 <= raw_index <= len(fields):
            return fields[raw_index - 1]

        if raw_index == 0 and len(fields) > 0:
            return fields[0]

    return None


async def find_target(page, target: str):
    if not target:
        return None

    field_ref = await _resolve_field_ref(page, target)
    if field_ref is not None:
        return field_ref

    candidates = [
        page.locator(target),
        page.get_by_role("button", name=target, exact=False),
        page.get_by_role("link", name=target, exact=False),
        page.get_by_text(target, exact=False),
        page.locator(f"button:has-text('{target}')"),
        page.locator(f"a:has-text('{target}')"),
        page.locator(f"[role='button']:has-text('{target}')"),
    ]

    for loc in candidates:
        try:
            if await loc.count() > 0:
                return loc.first
        except Exception:
            continue
    return None


async def fill_locator(locator, value: str) -> None:
    try:
        await locator.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass
    try:
        await locator.fill(value)
        return
    except Exception:
        try:
            await locator.click(timeout=1500)
        except Exception:
            pass
        await locator.evaluate("""(el, value) => {
            if ('value' in el) {
              el.value = value;
              el.dispatchEvent(new Event('input', {bubbles: true}));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            } else { el.textContent = value; }
        }""", value)


async def _try_click(locator) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass

    try:
        await locator.click(timeout=2000)
        return True
    except Exception:
        pass

    try:
        await locator.click(force=True, timeout=2000)
        return True
    except Exception:
        pass

    return False


async def _is_checked(locator, expected: bool) -> bool:
    try:
        return (await locator.is_checked()) == expected
    except Exception:
        return False


async def set_checked(locator, checked: bool) -> bool:
    try:
        await locator.scroll_into_view_if_needed(timeout=1500)
    except Exception:
        pass

    input_type = ""
    try:
        input_type = ((await locator.get_attribute("type")) or "").strip().lower()
    except Exception:
        pass

    # 1. Стандартный playwright check/uncheck
    try:
        if checked:
            await locator.check(force=True, timeout=2000)
        else:
            await locator.uncheck(force=True, timeout=2000)
        if await _is_checked(locator, checked):
            return True
    except Exception:
        pass

    # 2. Для radio почти всегда надежнее кликать по label
    if input_type == "radio":
        try:
            label = locator.locator("xpath=ancestor::label[1]")
            if await label.count() > 0:
                if await _try_click(label.first):
                    if await _is_checked(locator, checked):
                        return True
            # иногда input лежит внутри label/div/span-структур
        except Exception:
            pass

    # 3. Клик по самому input
    try:
        if await _try_click(locator):
            if await _is_checked(locator, checked):
                return True
    except Exception:
        pass

    # 4. Клик по нескольким родителям выше
    parent_xpaths = [
        "xpath=ancestor::span[1]",
        "xpath=ancestor::div[1]",
        "xpath=ancestor::div[2]",
        "xpath=ancestor::div[3]",
        "xpath=ancestor::*[@role='radio'][1]",
    ]

    for xp in parent_xpaths:
        try:
            parent = locator.locator(xp)
            if await parent.count() > 0:
                if await _try_click(parent.first):
                    if await _is_checked(locator, checked):
                        return True
        except Exception:
            continue

    # 5. JS fallback
    try:
        await locator.evaluate(
            """(el, checked) => {
                el.checked = checked;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            }""",
            checked,
        )
        if await _is_checked(locator, checked):
            return True
    except Exception:
        pass

    return False


async def execute_action(page, action) -> dict:
    if action.action == "stop":
        return {"ok": True, "action": "stop"}

    locator = None
    if action.action == "next":
        locator = await find_next_locator(page, preferred_text=action.target or None)
    elif action.action == "submit":
        locator = await find_submit_locator(page, preferred_text=action.target or None)
    else:
        locator = await find_target(page, action.target)

    if locator is None:
        return {"ok": False, "error": f"target_not_found:{action.target}"}

    if action.action == "click":
        result = await click_with_postcheck(page, locator, expected="screen_changed", timeout=4000)
        return {"action": "click", "target": action.target, **result}

    if action.action == "next":
        result = await click_with_postcheck(page, locator, expected="screen_changed", timeout=5000)
        return {"action": "next", "target": action.target, **result}

    if action.action == "submit":
        result = await click_with_postcheck(page, locator, expected="submitted", timeout=5000)
        return {"action": "submit", "target": action.target, **result}

    if action.action == "fill":
        await fill_locator(locator, action.value or "")
        return {"ok": True, "action": "fill", "target": action.target, "value": action.value}

    if action.action == "select":
        try:
            await locator.select_option(label=action.value or "")
        except Exception:
            await locator.select_option(value=action.value or "")
        return {"ok": True, "action": "select", "target": action.target, "value": action.value}

    if action.action in {"check", "uncheck"}:
        ok = await set_checked(locator, action.action == "check")
        return {
            "ok": ok,
            "action": action.action,
            "target": action.target,
            "reason": "checked" if ok else "check_state_not_changed",
        }

    return {"ok": False, "error": f"unsupported_action:{action.action}"}
