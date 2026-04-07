from __future__ import annotations

import json


def build_messages(prompts: dict, profile: dict, screen_dump: dict, mode: str) -> list[dict]:
    prompt = prompts.get(mode, {})
    system = prompt.get("system", "Return JSON only.")
    template = prompt.get("user_template", "Profile:\n{candidate_profile}\n\nScreen:\n{screen_dump}")
    user = template.format(
        candidate_profile=json.dumps(profile, ensure_ascii=False, indent=2),
        screen_dump=json.dumps(screen_dump, ensure_ascii=False, indent=2),
        vacancy_text="",
        dialog_context="",
        incoming_message="",
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
