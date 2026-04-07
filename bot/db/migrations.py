from __future__ import annotations

from bot.db.sqlite import connect


DDL = """
CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title TEXT DEFAULT '',
    company TEXT DEFAULT '',
    location TEXT DEFAULT '',
    salary_text TEXT DEFAULT '',
    snippet TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    last_error TEXT DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    applied_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_id TEXT DEFAULT '',
    last_log_path TEXT DEFAULT '',
    form_json TEXT DEFAULT '',
    fill_json TEXT DEFAULT '',
    submit_result_json TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies(status);
CREATE INDEX IF NOT EXISTS idx_vacancies_created_at ON vacancies(created_at);
CREATE INDEX IF NOT EXISTS idx_vacancies_applied_at ON vacancies(applied_at);
"""


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()
