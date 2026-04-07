from __future__ import annotations

from dataclasses import asdict

from bot.collector.pagination import try_ui_pagination_click
from bot.collector.vacancy_extractors import extract_vacancies_from_page
from bot.core.models import Vacancy
from bot.db.repo_vacancies import VacancyRepo
from bot.utils.urls import set_page_param


async def collect_new_vacancies(page, repo: VacancyRepo, urls: list[str], limit: int, max_pages: int, page_param_name: str = "page") -> tuple[list[Vacancy], list[dict]]:
    remaining = limit
    collected: list[Vacancy] = []
    events: list[dict] = []
    seen_run_ids: set[str] = set()

    for base_url in urls:
        if remaining <= 0:
            break
        for page_num in range(max_pages):
            if remaining <= 0:
                break
            page_url = set_page_param(base_url, page_num, page_param_name)
            try:
                await page.goto(page_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1800)
                page_vacancies = await extract_vacancies_from_page(page, remaining)
                added_here = 0
                for vacancy in page_vacancies:
                    if vacancy.vacancy_id in seen_run_ids:
                        continue
                    seen_run_ids.add(vacancy.vacancy_id)
                    if repo.exists(vacancy.vacancy_id):
                        continue
                    if repo.upsert_new(vacancy):
                        collected.append(vacancy)
                        added_here += 1
                        remaining -= 1
                        if remaining <= 0:
                            break
                events.append({"url": page_url, "page": page_num, "found": len(page_vacancies), "added": added_here})
                if added_here == 0 and page_num > 0:
                    break
            except Exception as exc:
                events.append({"url": page_url, "page": page_num, "error": str(exc)[:500], "status": "pagination_error"})
                try:
                    clicked = await try_ui_pagination_click(page, page_num)
                    events[-1]["ui_fallback_clicked"] = clicked
                except Exception:
                    pass
                break
    return collected, events
