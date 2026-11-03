"""Data loading, normalization, CSV import, and sample-data creation."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from database import Database

logger = logging.getLogger(__name__)
TRANSACTION_COLUMNS = [
    "id",
    "transaction_date",
    "category",
    "amount",
    "description",
]
IMPORT_COLUMNS = ["transaction_date", "category", "amount", "description"]


class DataValidationError(ValueError):
    """Raised when imported tabular data does not have the required structure."""


def clean_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize transaction data and remove rows with invalid dates or amounts."""
    aliases = {"date": "transaction_date"}
    frame = frame.rename(
        columns={column: aliases.get(column.lower().strip(), column.lower().strip())
                 for column in frame.columns}
    ).copy()
    required = {"transaction_date", "category", "amount"}
    missing_columns = required - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise DataValidationError(f"Missing required CSV column(s): {missing}.")

    frame["transaction_date"] = pd.to_datetime(
        frame["transaction_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").round(2)
    frame["category"] = frame["category"].fillna("").astype(str).str.strip()
    frame["category"] = frame["category"].replace("", "Uncategorized")
    if "description" not in frame.columns:
        frame["description"] = ""
    frame["description"] = frame["description"].fillna("").astype(str).str.strip()

    valid = (
        frame["transaction_date"].notna()
        & frame["amount"].notna()
        & (frame["amount"] > 0)
    )
    invalid_count = int((~valid).sum())
    if invalid_count:
        logger.warning("Skipped %d row(s) with invalid dates or amounts.", invalid_count)

    cleaned_columns = (["id"] if "id" in frame.columns else []) + IMPORT_COLUMNS
    cleaned = frame.loc[valid, cleaned_columns].copy()
    cleaned["amount"] = cleaned["amount"].astype(float)
    return cleaned.reset_index(drop=True)


def import_csv(file_path: str | Path, database: Database) -> tuple[int, int, int]:
    """Import a CSV and return (inserted, duplicates, invalid_rows)."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")
    try:
        source = pd.read_csv(path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise DataValidationError(f"Could not read CSV file '{path}': {exc}") from exc
    cleaned = clean_transactions(source)
    invalid_rows = len(source) - len(cleaned)
    rows = (
        (row.transaction_date, row.category, float(row.amount), row.description)
        for row in cleaned[IMPORT_COLUMNS].itertuples(index=False)
    )
    inserted, duplicates = database.insert_transactions(rows)
    logger.info(
        "Imported %d new record(s) from %s; %d duplicate(s), %d invalid row(s).",
        inserted,
        path.name,
        duplicates,
        invalid_rows,
    )
    return inserted, duplicates, invalid_rows


def load_transactions(
    database: Database,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Load cleaned database records into a consistently shaped DataFrame."""
    records = database.fetch_transactions(start_date, end_date)
    frame = pd.DataFrame([dict(row) for row in records], columns=TRANSACTION_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return clean_transactions(frame)


def create_sample_data(file_path: str | Path) -> Path:
    """Create the demonstration CSV without replacing an existing file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    sample = pd.DataFrame(
        [
            ("2025-01-05", "Sales", 1250.00, "Online order"),
            ("2025-01-12", "Marketing", 220.50, "Campaign materials"),
            ("2025-01-19", "Operations", 430.00, "Office supplies"),
            ("2025-02-03", "Sales", 1840.00, "Wholesale order"),
            ("2025-02-14", "Marketing", 315.25, "Email campaign"),
            ("2025-02-21", "Operations", 510.00, "Equipment repair"),
            ("2025-03-02", "Sales", 2100.00, "Online order"),
            ("2025-03-11", "Marketing", 280.00, "Promotional event"),
            ("2025-03-22", "Operations", 395.75, "Shipping supplies"),
            ("2025-04-04", "Sales", 1630.00, "Retail order"),
            ("2025-04-16", "Marketing", 190.00, "Print campaign"),
            ("2025-04-25", "Operations", 620.00, "Maintenance"),
        ],
        columns=IMPORT_COLUMNS,
    )
    sample.to_csv(path, index=False)
    logger.info("Created sample CSV at %s.", path)
    return path
