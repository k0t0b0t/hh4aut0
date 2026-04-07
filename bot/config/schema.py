from __future__ import annotations

from pathlib import Path


def ensure_dirs(cfg: dict) -> None:
    storage = cfg["storage"]
    for key in ("logs_dir", "reports_dir", "screenshots_dir", "html_dir"):
        Path(storage[key]).mkdir(parents=True, exist_ok=True)
    Path(storage["db_path"]).parent.mkdir(parents=True, exist_ok=True)
