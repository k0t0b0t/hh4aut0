from __future__ import annotations

from bot.core.exceptions import LLMValidationError
from bot.core.models import LLMAction, LLMPlan

ALLOWED = {"click", "fill", "select", "check", "uncheck", "submit", "next", "stop"}


def validate_plan(data: dict, mode: str) -> LLMPlan:
    actions = []
    raw_actions = data.get("actions")
    if not isinstance(raw_actions, list):
        raise LLMValidationError("actions must be list")
    for item in raw_actions:
        action = item.get("action")
        if action not in ALLOWED:
            raise LLMValidationError(f"bad action: {action}")
        target = item.get("target", "")
        if action != "stop" and not target:
            raise LLMValidationError("target is required")
        value = item.get("value")
        if action in {"fill", "select"} and value is None:
            raise LLMValidationError("fill/select require value")
        conf = item.get("confidence")
        if conf is not None and not isinstance(conf, (float, int)):
            raise LLMValidationError("confidence must be number")
        actions.append(LLMAction(action=action, target=target, value=value, reason=item.get("reason"), confidence=float(conf) if conf is not None else None))
    submit = None
    raw_submit = data.get("submit_candidate")
    if isinstance(raw_submit, dict):
        submit = LLMAction(
            action=raw_submit.get("action", "submit"),
            target=raw_submit.get("target", ""),
            value=raw_submit.get("value"),
            reason=raw_submit.get("reason"),
            confidence=float(raw_submit["confidence"]) if raw_submit.get("confidence") is not None else None,
        )
    return LLMPlan(mode=mode, screen_goal=data.get("screen_goal", ""), actions=actions, submit_candidate=submit, stop_reason=data.get("stop_reason"))
