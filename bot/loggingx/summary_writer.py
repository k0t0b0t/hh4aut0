from __future__ import annotations

from collections import Counter


def summarize_results(results: list[dict]) -> dict:
    statuses = Counter(r.get("status", "unknown") for r in results)
    return {"processed": len(results), "statuses": dict(statuses)}
