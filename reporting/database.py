"""SQLite persistence for datasets, reports, schedules, executions and delivery logs."""

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd

from reporting.config import DATABASE_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_name TEXT NOT NULL,
    columns_json TEXT NOT NULL,
    records_json TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
    format TEXT NOT NULL,
    status TEXT NOT NULL,
    file_path TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS report_configs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scheduled_reports (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    config_json TEXT NOT NULL,
    frequency TEXT NOT NULL CHECK(frequency IN ('daily','weekly','monthly')),
    run_time TEXT NOT NULL,
    weekday INTEGER,
    monthday INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    paused INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_run_at TEXT
);
CREATE TABLE IF NOT EXISTS schedule_runs (
    id INTEGER PRIMARY KEY,
    schedule_id INTEGER NOT NULL REFERENCES scheduled_reports(id),
    run_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(schedule_id, run_key)
);
CREATE TABLE IF NOT EXISTS email_deliveries (
    id INTEGER PRIMARY KEY,
    report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT,
    error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY,
    report_id INTEGER REFERENCES reports(id) ON DELETE SET NULL,
    schedule_id INTEGER REFERENCES scheduled_reports(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL NOT NULL DEFAULT 0,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_created ON execution_logs(created_at);
"""


def _db_path(database_path: Optional[Path] = None) -> Path:
    path = Path(database_path or DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def connect(database_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_db_path(database_path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Optional[Path] = None) -> None:
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)


def fetch_frame(
    query: str,
    parameters: tuple = (),
    database_path: Optional[Path] = None,
) -> pd.DataFrame:
    with connect(database_path) as connection:
        return pd.read_sql_query(query, connection, params=parameters)


def store_dataset(
    name: str,
    source_name: str,
    columns_json: str,
    records_json: str,
    row_count: int,
    database_path: Optional[Path] = None,
) -> int:
    from datetime import datetime, timezone

    with connect(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO datasets(name,source_name,columns_json,records_json,row_count,created_at)
            VALUES(?,?,?,?,?,?)""",
            (
                name,
                source_name,
                columns_json,
                records_json,
                row_count,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)
