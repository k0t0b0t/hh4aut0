from __future__ import annotations

import re
from typing import Any

COVER_RE = re.compile(
    r"(сопровод|cover letter|cover|motivation|about yourself|"
    r"почему вы|письмо работодателю|напишите о себе)",
    re.I,
)

QUESTIONNAIRE_RE = re.compile(
    r"(ответьте на вопросы|опрос|анкета|перечислите|опишите|"
    r"какой у вас опыт|с каким количеством|работали ли вы|есть ли у вас)",
    re.I,
)


def _text(field: dict[str, Any]) -> str:
    return " ".join(
        [
            field.get("label", "") or "",
            field.get("placeholder", "") or "",
            field.get("name", "") or "",
        ]
    ).strip()


def is_safe_single_cover_screen(form_json: dict[str, Any]) -> bool:
    elements = form_json.get("elements", []) or []

    fields = [
        x for x in elements
        if x.get("kind") in {"textarea", "field"}
    ]

    if len(fields) != 1:
        return False

    field = fields[0]

    if not field.get("textual"):
        return False

    if field.get("is_select") or field.get("is_radio") or field.get("is_checkbox"):
        return False

    joined = _text(field)

    if not joined:
        return False

    if QUESTIONNAIRE_RE.search(joined):
        return False

    if not COVER_RE.search(joined):
        return False

    return True


def find_safe_cover_field(form_json: dict[str, Any]) -> dict[str, Any] | None:
    if not is_safe_single_cover_screen(form_json):
        return None

    for item in form_json.get("elements", []) or []:
        if item.get("kind") in {"textarea", "field"}:
            return item

    return None
