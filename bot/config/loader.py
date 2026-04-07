from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def default_config() -> dict[str, Any]:
    return {
        "system": {"app_name": "hh-bot-v2", "timezone": "Europe/Moscow"},
        "browser": {
            "cdp_url": "http://127.0.0.1:9222",
            "goto_timeout_ms": 60000,
            "action_timeout_ms": 7000,
            "wait_after_click_ms": 1800,
            "wait_after_fill_ms": 300,
            "headless": False,
        },
        "search": {"max_pages_per_url": 10, "page_param_name": "page", "stop_on_pagination_error": True},
        "apply": {
            "detect_already_applied": True,
            "allow_safe_cover_autofill": True,
            "safe_cover_requires_single_field": True,
            "llm_only_default": False,
            "max_llm_attempts_per_stage": 1,
            "dry_run_skip_submit": True,
        },
        "debug": {
            "save_html_snapshot": True,
            "save_screenshot": True,
            "save_form_json": True,
            "save_llm_payloads_only_in_debug": True,
            "write_error_bucket_files": True,
        },
        "storage": {
            "db_path": "./data/db/hhbot.sqlite3",
            "logs_dir": "./data/logs",
            "reports_dir": "./data/reports",
            "screenshots_dir": "./data/logs/screenshots",
            "html_dir": "./data/logs/html",
        },
        "llm": {
            "enabled": False,
            "transport": "openai_compatible",
            "base_url": "",
            "model": "",
            "timeout_sec": 90,
            "auth": {
                "mode": "none",
                "api_key": "",
                "username": "",
                "password": "",
                "header_name": "Authorization",
                "scheme": "Bearer",
                "extra_headers": {},
            },
            "ssl": {"verify_ssl": True, "ca_cert_path": "", "client_cert_path": "", "client_key_path": ""},
        },
        "modes": {"default_run_search_limit": 20, "default_run_db_limit": 20, "default_debug_submit": False},
        "candidate": {},
        "resume": {},
        "skills": {},
        "preferences": {},
        "cover_letters": {"default": "Здравствуйте! Меня заинтересовала вакансия {title}. Буду рад обсудить детали."},
        "answers": {"yes": "Да", "no": "Нет", "default_text": "Готов обсудить подробнее на собеседовании."},
        "dialog_profile": {},
        "prompts": {},
    }


def load_all_configs() -> dict[str, Any]:
    cfg = default_config()
    for name in ("config.yaml", "profile.yaml", "prompts.yaml"):
        cfg = _deep_merge(cfg, _load_yaml(CONFIG_DIR / name))
    return _expand_env(cfg)
