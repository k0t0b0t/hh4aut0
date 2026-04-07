from __future__ import annotations

from pathlib import Path

from bot.apply.runner import apply_vacancy
from bot.core.models import ApplyAttemptContext, Vacancy
from bot.loggingx.run_logger import save_json
from bot.utils.urls import extract_vacancy_id


async def run_one(page, repo, cfg: dict, prompts: dict, llm_client, *, run_id: str, url: str, dry_run: bool, debug_submit: bool, llm_only: bool, force_debug: bool) -> dict:
    vacancy = Vacancy(vacancy_id=extract_vacancy_id(url), url=url)
    repo.upsert_manual(vacancy)
    ctx = ApplyAttemptContext(run_id=run_id, vacancy_id=vacancy.vacancy_id, url=vacancy.url, mode="run-one", dry_run=dry_run, debug_submit=debug_submit, llm_only=llm_only, force_debug=force_debug)
    result = await apply_vacancy(vacancy, page, ctx, cfg, prompts, llm_client, repo)
    summary = {"run_id": run_id, "vacancy_id": vacancy.vacancy_id, "url": url, "result": result.as_dict()}
    save_json(Path(cfg["storage"]["reports_dir"]) / f"run_{run_id}.json", summary)
    return summary
