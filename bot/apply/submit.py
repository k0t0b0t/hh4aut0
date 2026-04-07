from __future__ import annotations

from bot.apply.click_logic import click_with_postcheck
from bot.apply.detectors import find_submit_locator


def ask_debug_submit() -> str:
    return input("Submit this stage? [yes/skip/no]: ").strip().lower()


async def finalize_submit(page, *, dry_run: bool, debug_submit: bool) -> tuple[bool, str]:
    locator = await find_submit_locator(page)
    if locator is None:
        return False, "submit_button_not_found"

    if dry_run:
        return True, "dry_run_skip_submit"

    if debug_submit:
        choice = ask_debug_submit()
        if choice not in {"yes", "y"}:
            return False, f"operator_{choice or 'skip'}"

    result = await click_with_postcheck(page, locator, expected="submitted", timeout=5000)
    if result.get("ok"):
        return True, "submitted"
    return False, result.get("reason", "submit_click_failed")
