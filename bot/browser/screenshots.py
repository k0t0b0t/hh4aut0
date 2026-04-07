from __future__ import annotations

from pathlib import Path


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def capture_html(page, path: Path) -> str:
    write_text(path, await page.content())
    return str(path)


async def capture_screenshot(page, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)
    return str(path)
