from __future__ import annotations

from bot.apply.runner import apply_vacancy
from bot.core.models import ApplyAttemptContext, Vacancy
from bot.loggingx.error_buckets import write_error_bucket
from bot.loggingx.run_logger import save_json
from bot.loggingx.summary_writer import summarize_results


async def _ensure_live_page(page):
    try:
        _ = page.url
        await page.title()
        return page
    except Exception:
        pass

    try:
        context = page.context
        new_page = await context.new_page()
        return new_page
    except Exception:
        return page


async def run_db(page, repo, cfg: dict, prompts: dict, llm_client, *, run_id: str, mode: str, statuses: list[str], limit: int, dry_run: bool, debug_submit: bool, llm_only: bool, force_debug: bool) -> dict:
    rows = repo.get_for_run_db(mode, limit, statuses)
    results = []

    for row in rows:
        page = await _ensure_live_page(page)

        vacancy = Vacancy(**{k: row.get(k, "") for k in ["vacancy_id", "url", "title", "company", "location", "salary_text", "snippet"]})
        ctx = ApplyAttemptContext(run_id=run_id, vacancy_id=vacancy.vacancy_id, url=vacancy.url, mode="run-db", dry_run=dry_run, debug_submit=debug_submit, llm_only=llm_only, force_debug=force_debug)
        result = await apply_vacancy(vacancy, page, ctx, cfg, prompts, llm_client, repo)
        results.append({"vacancy_id": vacancy.vacancy_id, "url": vacancy.url, "status": result.status, "message": result.message, "log_path": result.log_path})

    summary = {"run_id": run_id, "mode": mode, "statuses_filter": statuses, "results": results, "summary": summarize_results(results)}
    save_json(__import__('pathlib').Path(cfg["storage"]["reports_dir"]) / f"run_{run_id}.json", summary)
    for bucket in ("llm_failed", "bad_response", "manual_skipped", "lost_after_apply"):
        write_error_bucket(cfg["storage"]["reports_dir"], run_id, bucket, [r["url"] for r in results if r["status"] == bucket])
    return summary
