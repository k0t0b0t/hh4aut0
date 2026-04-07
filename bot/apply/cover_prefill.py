from __future__ import annotations

import re
from typing import Any

from bot.utils.template_render import render_text_template


COVER_FIELD_RE = re.compile(
    r"(сопровод|cover\s*letter|cover|motivation|"
    r"письмо\s*работодателю|message\s*to\s*employer|"
    r"about\s*yourself|о\s*себе|почему\s*вы)",
    re.I,
)

COVER_EXCLUDE_RE = re.compile(
    r"(зарплат|доход|оплат|выплат|salary|income|"
    r"resume|резюме|вопрос|анкета|questionnaire)",
    re.I,
)

COVER_BUTTON_RE = re.compile(
    r"(сопроводительное письмо|сопроводительное|cover\s*letter|cover|добавить)",
    re.I,
)


def _joined(field: dict[str, Any]) -> str:
    return " ".join(
        [
            field.get("label", "") or "",
            field.get("placeholder", "") or "",
            field.get("name", "") or "",
        ]
    ).strip()


def find_cover_fields(form_json: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for item in form_json.get("elements", []) or []:
        if not item.get("textual"):
            continue
        if item.get("is_select") or item.get("is_radio") or item.get("is_checkbox"):
            continue

        joined = _joined(item)
        if not joined:
            continue
        if COVER_EXCLUDE_RE.search(joined):
            continue
        if not COVER_FIELD_RE.search(joined):
            continue

        out.append(item)

    return out


def build_cover_text(cfg: dict[str, Any], vacancy: Any | None = None) -> str:
    raw = cfg.get("cover_letters", {}).get("default", "") or ""
    return render_text_template(raw, cfg, vacancy)


async def try_expand_cover_section(page) -> bool:
    # 🔒 guard: если textarea уже есть — ничего не раскрываем
    try:
        existing = await page.locator("form[id^='cover-letter-'] textarea").count()
        if existing > 0:
            return False
    except Exception:
        pass

async def try_expand_cover_section(page) -> bool:
    candidates = [
        page.get_by_role("button", name="Сопроводительное письмо", exact=False),
        page.get_by_role("button", name="Добавить", exact=False),
        page.get_by_text("Сопроводительное письмо", exact=False),
        page.get_by_text("Добавить", exact=False),
        page.locator("button:has-text('Сопроводительное')"),
        page.locator("button:has-text('Добавить')"),
        page.locator("[role='button']:has-text('Сопроводительное')"),
        page.locator("[role='button']:has-text('Добавить')"),
    ]

    for loc in candidates:
        try:
            count = await loc.count()
        except Exception:
            continue

        for i in range(min(count, 8)):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue

                text = ""
                try:
                    text = (await el.inner_text()).strip()
                except Exception:
                    pass

                if text and not COVER_BUTTON_RE.search(text):
                    continue

                await el.click(timeout=2000)
                await page.wait_for_timeout(700)
                return True
            except Exception:
                continue

    return False
