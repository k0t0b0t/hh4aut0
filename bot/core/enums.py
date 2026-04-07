RETRYABLE_STATUSES = {
    "collect_error",
    "pagination_error",
    "open_error",
    "form_detected",
    "llm_failed",
    "bad_response",
    "manual_skipped",
    "submit_failed",
    "apply_error",
    "no_apply_button",
    "vacancy_not_available",
    "lost_after_apply",
}

FINAL_STATUSES = {"applied", "already_applied_on_hh"}

ALL_STATUSES = {
    "new",
    "queued",
    "collect_error",
    "pagination_error",
    "open_error",
    "apply_opened",
    "form_detected",
    "llm_in_progress",
    "applied",
    "already_applied_on_hh",
    "llm_failed",
    "bad_response",
    "manual_skipped",
    "submit_failed",
    "apply_error",
    "no_apply_button",
    "vacancy_not_available",
    "lost_after_apply",
}
