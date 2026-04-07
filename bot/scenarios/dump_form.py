from __future__ import annotations

from pathlib import Path

from bot.apply.detectors import click_apply_button, collect_form_screen_dump, wait_for_form
from bot.browser.screenshots import capture_html, capture_screenshot
from bot.loggingx.run_logger import save_json


async def dump_form(page, cfg: dict, *, url: str, run_id: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=cfg["browser"]["goto_timeout_ms"])
    await page.wait_for_timeout(1800)
    await click_apply_button(page)
    await wait_for_form(page, timeout_loops=5)

    screen = await collect_form_screen_dump(page, 1)

    html_path = await capture_html(page, Path(cfg["storage"]["html_dir"]) / f"dump_{run_id}.html")
    png_path = await capture_screenshot(page, Path(cfg["storage"]["screenshots_dir"]) / f"dump_{run_id}.png")

    payload = {
        "run_id": run_id,
        "url": url,
        "screen": screen,
        "html_path": html_path,
        "screenshot_path": png_path,
    }
    save_json(Path(cfg["storage"]["reports_dir"]) / f"run_{run_id}.json", payload)
    return payload
