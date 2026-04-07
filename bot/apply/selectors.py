from __future__ import annotations

FORM_SELECTORS = "textarea, input, select, [contenteditable='true']"

APPLY_BUTTON_SELECTORS = [
    "[data-qa='vacancy-response-link-top']",
    "[data-qa='vacancy-response-link-bottom']",
    "main a:has-text('Откликнуться')",
    "main button:has-text('Откликнуться')",
    "a:has-text('Откликнуться')",
    "button:has-text('Откликнуться')",
]

SUBMIT_BUTTON_PATTERNS = ["Отправить", "Откликнуться", "Продолжить", "Далее", "Submit", "Apply"]

ALREADY_APPLIED_TEXTS = ["Вы откликнулись", "Вы уже откликались", "Отклик отправлен", "Откликнуться повторно"]
