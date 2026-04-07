from __future__ import annotations

from datetime import datetime


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_id() -> str:
    return datetime.now().strftime("run_%Y%m%d_%H%M%S")
