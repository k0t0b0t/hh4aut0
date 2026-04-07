from __future__ import annotations

import re
from typing import Any


MUSTACHE_RE = re.compile(r"{{\s*([a-zA-Z0-9_.]+)\s*}}")
BRACE_RE = re.compile(r"{([a-zA-Z0-9_.]+)}")


def _resolve_path(ctx: dict[str, Any], path: str) -> Any:
    parts = [p for p in (path or "").split(".") if p]
    if not parts:
        return None

    cur: Any = ctx
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
            continue
        return None
    return cur


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(x) for x in value if x is not None)
    return str(value)


def _build_context(cfg: dict[str, Any], vacancy: Any | None = None) -> dict[str, Any]:
    vacancy_dict = {}
    if vacancy is not None:
        vacancy_dict = {
            "vacancy_id": getattr(vacancy, "vacancy_id", "") or "",
            "url": getattr(vacancy, "url", "") or "",
            "title": getattr(vacancy, "title", "") or "",
            "company": getattr(vacancy, "company", "") or "",
            "location": getattr(vacancy, "location", "") or "",
            "salary_text": getattr(vacancy, "salary_text", "") or "",
            "snippet": getattr(vacancy, "snippet", "") or "",
        }

    return {
        **cfg,
        "candidate": cfg,
        "vacancy": vacancy_dict,
        "title": vacancy_dict.get("title", ""),
        "company": vacancy_dict.get("company", ""),
        "vacancy_url": vacancy_dict.get("url", ""),
    }


def render_text_template(value: str | None, cfg: dict[str, Any], vacancy: Any | None = None) -> str:
    if value is None:
        return ""

    text = str(value)
    ctx = _build_context(cfg, vacancy)

    def replace_mustache(match: re.Match[str]) -> str:
        path = match.group(1)
        resolved = _resolve_path(ctx, path)
        if resolved is None and path.startswith("candidate."):
            resolved = _resolve_path(ctx, path[len("candidate."):])
        return _stringify(resolved) if resolved is not None else match.group(0)

    def replace_brace(match: re.Match[str]) -> str:
        path = match.group(1)
        resolved = _resolve_path(ctx, path)
        if resolved is None:
            return match.group(0)
        return _stringify(resolved)

    text = MUSTACHE_RE.sub(replace_mustache, text)
    text = BRACE_RE.sub(replace_brace, text)
    return text
