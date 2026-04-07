from __future__ import annotations

from pathlib import Path


def write_error_bucket(reports_dir: str, run_id: str, bucket: str, urls: list[str]) -> str:
    path = Path(reports_dir) / "errors" / f"{bucket}_{run_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    return str(path)
