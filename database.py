"""SQLite database setup and transaction persistence."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from config import Settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL DEFAULT '',
    UNIQUE (transaction_date, category, amount, description)
);
CREATE INDEX IF NOT EXISTS idx_transactions_date
    ON transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category
    ON transactions (category);
"""


class Database:
    """Small SQLite repository for transaction records."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.path = Path(database_path) if database_path else Settings.from_env().database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create the schema, including indexes, if it does not already exist."""
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert_transactions(
        self, records: Iterable[tuple[str, str, float, str]]
    ) -> tuple[int, int]:
        """Insert records idempotently; return (inserted, already_present)."""
        rows = list(records)
        if not rows:
            return 0, 0
        with self.connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO transactions
                    (transaction_date, category, amount, description)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            inserted = connection.total_changes - before
        return inserted, len(rows) - inserted

    def fetch_transactions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[sqlite3.Row]:
        """Fetch transactions in date order, applying inclusive date filters."""
        clauses: list[str] = []
        parameters: list[str] = []
        if start_date:
            clauses.append("transaction_date >= ?")
            parameters.append(start_date)
        if end_date:
            clauses.append("transaction_date <= ?")
            parameters.append(end_date)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            return connection.execute(
                f"""
                SELECT id, transaction_date, category, amount, description
                FROM transactions {where}
                ORDER BY transaction_date, id
                """,
                parameters,
            ).fetchall()
