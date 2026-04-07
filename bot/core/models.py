from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(slots=True)
class Vacancy:
    vacancy_id: str
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    salary_text: str = ""
    snippet: str = ""


@dataclass(slots=True)
class ApplyAttemptContext:
    run_id: str
    vacancy_id: str
    url: str
    mode: str
    dry_run: bool = False
    debug_submit: bool = False
    llm_only: bool = False
    force_debug: bool = False
    step_index: int = 0
    current_screen_index: int = 0


@dataclass(slots=True)
class LLMAction:
    action: str
    target: str
    value: str | None = None
    reason: str | None = None
    confidence: float | None = None


@dataclass(slots=True)
class LLMPlan:
    mode: str
    screen_goal: str
    actions: list[LLMAction] = field(default_factory=list)
    submit_candidate: LLMAction | None = None
    stop_reason: str | None = None


@dataclass(slots=True)
class ApplyResult:
    status: str
    message: str = ""
    form_json: dict[str, Any] | None = None
    fill_json: dict[str, Any] | None = None
    submit_result_json: dict[str, Any] | None = None
    log_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
