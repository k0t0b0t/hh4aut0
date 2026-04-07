from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def to_dict_safe(obj: Any):
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, list):
        return [to_dict_safe(x) for x in obj]

    if isinstance(obj, tuple):
        return [to_dict_safe(x) for x in obj]

    if isinstance(obj, dict):
        return {str(k): to_dict_safe(v) for k, v in obj.items()}

    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass

    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass

    if is_dataclass(obj):
        try:
            return asdict(obj)
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        try:
            return {str(k): to_dict_safe(v) for k, v in obj.__dict__.items()}
        except Exception:
            pass

    slots = getattr(obj.__class__, "__slots__", None)
    if slots:
        out = {}
        for name in slots:
            try:
                out[name] = to_dict_safe(getattr(obj, name))
            except Exception:
                continue
        if out:
            return out

    return repr(obj)
