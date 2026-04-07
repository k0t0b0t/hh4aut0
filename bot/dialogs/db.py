from __future__ import annotations

import sqlite3


def ensure_dialogs_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dialogs (
        chat_id TEXT PRIMARY KEY,
        chat_url TEXT,
        vacancy_title TEXT,
        company TEXT,
        vacancy_url TEXT,
        list_status_raw TEXT,

        status TEXT,
        last_error TEXT,
        attempt_count INTEGER DEFAULT 0,

        last_message_author TEXT,
        last_message_hash TEXT,

        reply_text TEXT,
        decision_json TEXT,
        history_json TEXT,

        created_at TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS dialog_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        case_type TEXT,
        vacancy_url TEXT,
        conversation_text TEXT,
        llm_decision_json TEXT,
        file_path TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
