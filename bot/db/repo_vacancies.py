from __future__ import annotations

import json
from typing import Iterable

from bot.core.enums import RETRYABLE_STATUSES
from bot.core.models import Vacancy
from bot.db.sqlite import connect


class VacancyRepo:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def count_all(self) -> int:
        with connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]

    def count_by_status(self) -> list[tuple[str, int]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM vacancies GROUP BY status ORDER BY COUNT(*) DESC"
            ).fetchall()
            return [(r[0], r[1]) for r in rows]

    def list_recent(self, limit: int) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT vacancy_id, title, company, location, salary_text, url, status, attempt_count, created_at FROM vacancies ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def exists(self, vacancy_id: str) -> bool:
        with connect(self.db_path) as conn:
            return conn.execute("SELECT 1 FROM vacancies WHERE vacancy_id = ? LIMIT 1", (vacancy_id,)).fetchone() is not None

    def upsert_new(self, vacancy: Vacancy) -> bool:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT status, applied_at FROM vacancies WHERE vacancy_id=?", (vacancy.vacancy_id,)).fetchone()
            if row:
                return False
            conn.execute(
                """INSERT INTO vacancies(vacancy_id,url,title,company,location,salary_text,snippet,status,updated_at)
                VALUES(?,?,?,?,?,?,?,'new',CURRENT_TIMESTAMP)""",
                (vacancy.vacancy_id, vacancy.url, vacancy.title, vacancy.company, vacancy.location, vacancy.salary_text, vacancy.snippet),
            )
            conn.commit()
            return True

    def upsert_manual(self, vacancy: Vacancy) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO vacancies(vacancy_id,url,title,company,location,salary_text,snippet,status,updated_at)
                VALUES(?,?,?,?,?,?,?,'new',CURRENT_TIMESTAMP)
                ON CONFLICT(vacancy_id) DO UPDATE SET url=excluded.url, updated_at=CURRENT_TIMESTAMP""",
                (vacancy.vacancy_id, vacancy.url, vacancy.title, vacancy.company, vacancy.location, vacancy.salary_text, vacancy.snippet),
            )
            conn.commit()

    def get_for_run_db(self, mode: str, limit: int, statuses: list[str] | None = None) -> list[dict]:
        with connect(self.db_path) as conn:
            if mode == "new":
                q = "SELECT * FROM vacancies WHERE status='new' ORDER BY id ASC LIMIT ?"
                rows = conn.execute(q, (limit,)).fetchall()
            elif mode == "retry-errors":
                placeholders = ",".join("?" * len(RETRYABLE_STATUSES))
                q = f"SELECT * FROM vacancies WHERE status IN ({placeholders}) ORDER BY id ASC LIMIT ?"
                rows = conn.execute(q, (*sorted(RETRYABLE_STATUSES), limit)).fetchall()
            elif mode == "not-applied":
                q = "SELECT * FROM vacancies WHERE applied_at IS NULL AND status NOT IN ('applied','already_applied_on_hh') ORDER BY id ASC LIMIT ?"
                rows = conn.execute(q, (limit,)).fetchall()
            elif mode == "statuses":
                statuses = statuses or []
                placeholders = ",".join("?" * len(statuses)) or "''"
                q = f"SELECT * FROM vacancies WHERE status IN ({placeholders}) ORDER BY id ASC LIMIT ?"
                rows = conn.execute(q, (*statuses, limit)).fetchall()
            else:
                raise ValueError(f"Unsupported mode: {mode}")
            return [dict(r) for r in rows]

    def get_by_ids(self, vacancy_ids: Iterable[str]) -> list[dict]:
        ids = list(vacancy_ids)
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with connect(self.db_path) as conn:
            rows = conn.execute(f"SELECT * FROM vacancies WHERE vacancy_id IN ({placeholders}) ORDER BY id ASC", ids).fetchall()
            return [dict(r) for r in rows]

    def get_by_id(self, vacancy_id: str) -> dict | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM vacancies WHERE vacancy_id=? LIMIT 1", (vacancy_id,)).fetchone()
            return dict(row) if row else None

    def mark_start_attempt(self, vacancy_id: str, run_id: str, status: str = "queued") -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE vacancies SET attempt_count=attempt_count+1, updated_at=CURRENT_TIMESTAMP, last_run_id=?, status=? WHERE vacancy_id=?",
                (run_id, status, vacancy_id),
            )
            conn.commit()

    def update_status(self, vacancy_id: str, status: str, *, last_error: str = "", form_json: dict | None = None, fill_json: dict | None = None, submit_result_json: dict | None = None, log_path: str = "") -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """UPDATE vacancies
                SET status=?, last_error=?, updated_at=CURRENT_TIMESTAMP,
                    last_log_path=CASE WHEN ?='' THEN last_log_path ELSE ? END,
                    form_json=CASE WHEN ? IS NULL THEN form_json ELSE ? END,
                    fill_json=CASE WHEN ? IS NULL THEN fill_json ELSE ? END,
                    submit_result_json=CASE WHEN ? IS NULL THEN submit_result_json ELSE ? END,
                    applied_at=CASE WHEN ? IN ('applied','already_applied_on_hh') THEN CURRENT_TIMESTAMP ELSE applied_at END
                WHERE vacancy_id=?""",
                (
                    status, last_error[:2000], log_path, log_path,
                    None if form_json is None else json.dumps(form_json, ensure_ascii=False), None if form_json is None else json.dumps(form_json, ensure_ascii=False),
                    None if fill_json is None else json.dumps(fill_json, ensure_ascii=False), None if fill_json is None else json.dumps(fill_json, ensure_ascii=False),
                    None if submit_result_json is None else json.dumps(submit_result_json, ensure_ascii=False), None if submit_result_json is None else json.dumps(submit_result_json, ensure_ascii=False),
                    status, vacancy_id,
                ),
            )
            conn.commit()
