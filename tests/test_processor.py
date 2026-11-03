import pandas as pd
import pytest

from data_collector import DataValidationError, clean_transactions, import_csv
from data_processor import (
    DataProcessingError,
    category_summary,
    monthly_summary,
    summarize_transactions,
    validate_date_range,
)
from database import Database


def test_cleaning_and_summaries(tmp_path):
    source = pd.DataFrame(
        [
            ("2025-01-01", "Sales", "10.10", None),
            ("invalid", "Sales", 5, "bad date"),
            ("2025-02-01", None, "20", "valid"),
            ("2025-02-03", "Ops", "bad", "bad amount"),
        ],
        columns=["transaction_date", "category", "amount", "description"],
    )
    cleaned = clean_transactions(source)

    assert len(cleaned) == 2
    assert cleaned.loc[1, "category"] == "Uncategorized"
    assert summarize_transactions(cleaned) == {
        "record_count": 2,
        "total": 30.1,
        "average": 15.05,
        "minimum": 10.1,
        "maximum": 20.0,
    }
    assert list(monthly_summary(cleaned)["month"]) == ["2025-01", "2025-02"]
    assert category_summary(cleaned).iloc[0]["category"] == "Uncategorized"


def test_csv_import_reports_invalid_and_duplicate_rows(tmp_path):
    source = tmp_path / "records.csv"
    source.write_text(
        "transaction_date,category,amount,description\n"
        "2025-01-01,Sales,10,Order\n"
        "2025-01-01,Sales,10,Order\n"
        "not-a-date,Sales,4,Bad\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "test.db")
    database.initialize()

    assert import_csv(source, database) == (1, 1, 1)


def test_missing_csv_columns_are_reported(tmp_path):
    source = tmp_path / "invalid.csv"
    source.write_text("category,amount\nSales,10\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="transaction_date"):
        import_csv(source, Database(tmp_path / "test.db"))


def test_date_range_validation():
    assert validate_date_range("2025-01-01", "2025-01-31") == (
        "2025-01-01",
        "2025-01-31",
    )
    with pytest.raises(DataProcessingError, match="on or before"):
        validate_date_range("2025-02-01", "2025-01-01")
