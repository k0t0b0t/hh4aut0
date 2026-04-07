from __future__ import annotations

from dataclasses import asdict

from bot.collector.search_collector import collect_new_vacancies
from bot.core.models import ApplyAttemptContext
from bot.apply.runner import apply_vacancy
from bot.loggingx.error_buckets import write_error_bucket
from bot.loggingx.run_logger import save_json
from bot.loggingx.summary_writer import summarize_results


async def run_search(page, repo, cfg: dict, prompts: dict, llm_client, *, run_id: str, urls: list[str], limit: int, dry_run: bool, debug_submit: bool, llm_only: bool, force_debug: bool, max_pages: int) -> dict:
    collected, collect_events = await collect_new_vacancies(
        page,
        repo,
        urls,
        limit,
        max_pages,
        cfg["search"]["page_param_name"],
    )

    results = []
    for vacancy in collected:
        ctx = ApplyAttemptContext(
            run_id=run_id,
            vacancy_id=vacancy.vacancy_id,
            url=vacancy.url,
            mode="run-search",
            dry_run=dry_run,
            debug_submit=debug_submit,
            llm_only=llm_only,
            force_debug=force_debug,
        )
        result = await apply_vacancy(vacancy, page, ctx, cfg, prompts, llm_client, repo)
        results.append(
            {
                "vacancy_id": vacancy.vacancy_id,
                "url": vacancy.url,
                "status": result.status,
                "message": result.message,
                "log_path": result.log_path,
            }
        )

    summary = {
        "run_id": run_id,
        "urls": urls,
        "limit": limit,
        "collected": [asdict(v) for v in collected],
        "collect_events": collect_events,
        "results": results,
        "summary": summarize_results(results),
    }

    save_json(__import__("pathlib").Path(cfg["storage"]["reports_dir"]) / f"run_{run_id}.json", summary)

    for bucket in ("llm_failed", "bad_response", "manual_skipped"):
        urls_bucket = [r["url"] for r in results if r["status"] == bucket]
        write_error_bucket(cfg["storage"]["reports_dir"], run_id, bucket, urls_bucket)

    return summary
