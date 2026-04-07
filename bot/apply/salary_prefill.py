from __future__ import annotations

import re
from typing import Any


SALARY_FIELD_RE = re.compile(
    r"(зарплат|заработн|доход|оплат|выплат|оклад|вознагражден|"
    r"salary|income|compensation|pay|payment)",
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


def find_salary_fields(form_json: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for item in form_json.get("elements", []) or []:
        if not item.get("textual"):
            continue
        if item.get("is_select") or item.get("is_radio") or item.get("is_checkbox"):
            continue

        joined = _joined(item)
        if not joined:
            continue
        if not SALARY_FIELD_RE.search(joined):
            continue

        out.append(item)

    return out


def _format_rub(value: Any) -> str:
    try:
        n = int(str(value).replace(" ", "").replace("_", ""))
    except Exception:
        return str(value)
    return f"{n:,}".replace(",", " ")


def build_salary_text(cfg: dict[str, Any]) -> str:
    value = (
        cfg.get("preferences", {}).get("salary_rub")
        or cfg.get("candidate", {}).get("preferences", {}).get("salary_rub")
    )
    if value in (None, ""):
        return ""

    return f"{_format_rub(value)} руб."
