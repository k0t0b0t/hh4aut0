from __future__ import annotations

import base64

import httpx

from bot.llm.parser import extract_json
from bot.llm.prompt_builder import build_messages
from bot.llm.ssl import build_verify_and_cert
from bot.llm.validators import validate_plan


class LLMClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled") and self.cfg.get("base_url") and self.cfg.get("model"))

    def _headers(self) -> dict[str, str]:
        auth = self.cfg.get("auth", {})
        mode = auth.get("mode", "none")
        headers = {"Content-Type": "application/json", **(auth.get("extra_headers") or {})}
        if mode == "bearer" and auth.get("api_key"):
            headers[auth.get("header_name", "Authorization")] = f"{auth.get('scheme', 'Bearer')} {auth['api_key']}"
        elif mode == "basic" and auth.get("username"):
            token = base64.b64encode(f"{auth.get('username','')}:{auth.get('password','')}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        elif mode == "custom_header" and auth.get("header_name"):
            headers[auth["header_name"]] = auth.get("api_key", "")
        return headers

    async def plan(self, prompts: dict, candidate_profile: dict, screen_dump: dict, mode: str):
        messages = build_messages(prompts, candidate_profile, screen_dump, mode)
        verify, cert = build_verify_and_cert(self.cfg.get("ssl", {}))
        payload = {"model": self.cfg["model"], "messages": messages, "temperature": 0.1}
        async with httpx.AsyncClient(timeout=self.cfg.get("timeout_sec", 90), verify=verify, cert=cert) as client:
            response = await client.post(self.cfg["base_url"], headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = extract_json(content)
        plan = validate_plan(parsed, mode=mode)
        return plan, {"request": payload, "response": data}
