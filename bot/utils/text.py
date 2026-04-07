from __future__ import annotations

import re


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def clip(text: str | None, limit: int = 160) -> str:
    value = (text or "").strip()
    return value if len(value) <= limit else value[:limit] + "..."
