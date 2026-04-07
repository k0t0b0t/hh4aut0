from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def ask_store_decision(bucket: str) -> str:
    return input(f"store? bucket={bucket} [yes/no/skip]: ").strip().lower()


def _bucket_dir(bucket: str) -> Path:
    bucket = (bucket or "none").strip()
    base = Path("data/dialogs")
    mapping = {
        "interview": base / "interview_invite",
        "test_task": base / "test_or_survey",
        "survey": base / "test_or_survey",
        "none": base / "misc",
    }
    path = mapping.get(bucket, base / "misc")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_case_file(chat_meta: dict, llm_context: dict, decision: dict) -> str:
    bucket = (decision.get("store_bucket") or "none").strip()
    out_dir = _bucket_dir(bucket)

    chat_id = str(chat_meta.get("chat_id") or "unknown")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{chat_id}_{ts}.json"

    payload = {
        "saved_at": datetime.now().isoformat(),
        "chat_meta": chat_meta,
        "llm_context": llm_context,
        "decision": decision,
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
