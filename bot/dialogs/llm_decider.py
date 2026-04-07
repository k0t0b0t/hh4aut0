from __future__ import annotations

import base64
import json
from dataclasses import dataclass, asdict

import httpx

from bot.llm.parser import extract_json
from bot.llm.ssl import build_verify_and_cert


@dataclass
class DialogDecision:
    decision: str
    status: str
    reply_text: str
    store_bucket: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


class DialogLLMDecider:
    def __init__(self, llm_cfg: dict, prompts_cfg: dict, profile_cfg: dict):
        self.llm_cfg = llm_cfg or {}
        self.prompts_cfg = prompts_cfg or {}
        self.profile_cfg = profile_cfg or {}

    def enabled(self) -> bool:
        return bool(
            self.llm_cfg.get("enabled")
            and self.llm_cfg.get("base_url")
            and self.llm_cfg.get("model")
        )

    def _headers(self) -> dict[str, str]:
        auth = self.llm_cfg.get("auth", {})
        mode = auth.get("mode", "none")
        headers = {"Content-Type": "application/json", **(auth.get("extra_headers") or {})}

        if mode == "bearer" and auth.get("api_key"):
            headers[auth.get("header_name", "Authorization")] = f"{auth.get('scheme', 'Bearer')} {auth['api_key']}"
        elif mode == "basic" and auth.get("username"):
            token = base64.b64encode(
                f"{auth.get('username','')}:{auth.get('password','')}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {token}"
        elif mode == "custom_header" and auth.get("header_name"):
            headers[auth["header_name"]] = auth.get("api_key", "")

        return headers

    def _candidate_profile_only(self) -> dict:
        return {
            "candidate": self.profile_cfg.get("candidate", {}),
            "resume": self.profile_cfg.get("resume", {}),
            "skills": self.profile_cfg.get("skills", {}),
            "preferences": self.profile_cfg.get("preferences", {}),
            "answers": self.profile_cfg.get("answers", {}),
            "cover_letters": self.profile_cfg.get("cover_letters", {}),
            "dialog_profile": self.profile_cfg.get("dialog_profile", {}),
        }

    def _build_messages(self, dialog_ctx: dict) -> list[dict]:
        prompt = (self.prompts_cfg or {}).get("dialogs_auto", {}) or {}

        system = prompt.get(
            "system",
            (
                "Ты помощник для ответов в hh.ru чатах."
                "Верни только JSON."
                "Будь кратким, вежливым, Не будь навязчивым."
                "Если ответ не очевиден из промпта, разрешен generate, в соответствии профилю кандидата."
                "Используй messages как полный контекст."
                "Отвечай одним совокупным ответом только на сообщения работодателя из pending_employer_indexes."
                "Не отвечай только на сообщения, которые пришли после сообщения кандидата. На все вопросы из этих сообщений."
                "Не дублируй ответ на повторяющиеся вопросы."
            ),
        )

        default_template = (
            "Профиль кандидата:\n__CANDIDATE_PROFILE__\n\n"
            "Контекст диалога:\n__DIALOG_CONTEXT__\n\n"
            "Правила интерпретации:\n"
            "- messages: полный контекст окна\n"
            "- pending_employer_indexes: индексы сообщений работодателя, на которые нужно ответить сейчас\n"
            "- last_employer_message_index: индекс последнего сообщения работодателя для подсветки\n"
            "- сформируй ОДИН совокупный reply_text по всем pending_employer_indexes\n"
            "- не повторяй одинаковые ответы на дублирующиеся вопросы\n\n"
            "Верни JSON строго такого вида:\n"
            "{\n"
            '  "decision": "reply | no_reply_needed | store_only | reply_and_store",\n'
            '  "status": "reply_ready_llm | no_reply_needed_llm | interview_invite_llm | test_or_survey_llm | llm_failed",\n'
            '  "reply_text": "string or empty",\n'
            '  "store_bucket": "interview | test_task | survey | none",\n'
            '  "reason": "short explanation"\n'
            "}\n"
        )

        user_template = prompt.get("user_template", default_template)

        user = (
            user_template
            .replace("__CANDIDATE_PROFILE__", json.dumps(self._candidate_profile_only(), ensure_ascii=False, indent=2))
            .replace("__DIALOG_CONTEXT__", json.dumps(dialog_ctx, ensure_ascii=False, indent=2))
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _validate_decision(self, data: dict) -> DialogDecision:
        decision = (data.get("decision") or "").strip()
        status = (data.get("status") or "").strip()
        reply_text = (data.get("reply_text") or "").strip()
        store_bucket = (data.get("store_bucket") or "none").strip()
        reason = (data.get("reason") or "").strip()

        allowed_decisions = {"reply", "no_reply_needed", "store_only", "reply_and_store"}
        allowed_statuses = {
            "reply_ready_llm",
            "no_reply_needed_llm",
            "interview_invite_llm",
            "test_or_survey_llm",
            "llm_failed",
        }
        allowed_buckets = {"interview", "test_task", "survey", "none"}

        if decision not in allowed_decisions:
            raise ValueError(f"invalid decision: {decision}")

        if status not in allowed_statuses:
            raise ValueError(f"invalid status: {status}")

        if store_bucket not in allowed_buckets:
            raise ValueError(f"invalid store_bucket: {store_bucket}")

        if decision in {"reply", "reply_and_store"} and not reply_text:
            raise ValueError("reply_text is required for reply/reply_and_store")

        return DialogDecision(
            decision=decision,
            status=status,
            reply_text=reply_text,
            store_bucket=store_bucket,
            reason=reason,
        )

    async def decide(self, dialog_ctx: dict) -> tuple[DialogDecision, dict]:
        messages = self._build_messages(dialog_ctx)
        verify, cert = build_verify_and_cert(self.llm_cfg.get("ssl", {}))
        payload = {
            "model": self.llm_cfg["model"],
            "messages": messages,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(
            timeout=self.llm_cfg.get("timeout_sec", 90),
            verify=verify,
            cert=cert,
        ) as client:
            response = await client.post(
                self.llm_cfg["base_url"],
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        parsed = extract_json(content)
        decision = self._validate_decision(parsed)

        return decision, {
            "request": payload,
            "response": data,
            "parsed": parsed,
        }
