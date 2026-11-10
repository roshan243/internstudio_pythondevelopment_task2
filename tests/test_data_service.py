from io import BytesIO

import pandas as pd
import pytest

from reporting.data_service import (
    clean_dataframe,
    filter_dataframe,
    load_dataset,
    read_uploaded_dataset,
    save_dataframe,
)
from reporting.database import initialize_database


def test_cleaning_fills_missing_and_removes_duplicate_rows():
    raw = pd.DataFrame(
        {
            " revenue ": [10.0, None, 10.0, None],
            " region ": [" North ", "South", " North ", None],
        }
    )

    cleaned, stats = clean_dataframe(raw)

    assert list(cleaned.columns) == ["revenue", "region"]
    assert len(cleaned) == 2
    assert cleaned.loc[1, "revenue"] == 10.0
    assert cleaned.loc[0, "region"] == "North"
    assert stats["duplicates_removed"] == 1
    assert stats["missing_values_filled"] == 1


def test_cleaning_rejects_all_blank_data():
    with pytest.raises(ValueError, match="non-empty"):
        clean_dataframe(pd.DataFrame({"a": [None, None]}))


def test_upload_csv_and_excel_validation():
    csv_bytes = b"name,amount\nA,10\nB,20\n"
    data = read_uploaded_dataset("data.csv", csv_bytes)
    assert len(data) == 2
    assert data["amount"].sum() == 30

    buffer = BytesIO()
    pd.DataFrame({"name": ["A"], "value": [1]}).to_excel(buffer, index=False)
    excel = read_uploaded_dataset("data.xlsx", buffer.getvalue())
    assert excel.iloc[0]["name"] == "A"

    with pytest.raises(ValueError, match="CSV or Excel"):
        read_uploaded_dataset("data.json", b"{}")


def test_dataset_database_roundtrip_and_filters(tmp_path):
    database = tmp_path / "data.db"
    initialize_database(database)
    dataset_id = save_dataframe(
        pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-02-01", "2026-03-01"],
                "amount": [10, 20, 30],
                "region": ["N", "S", "N"],
            }
        ),
        "Sales",
        "sales.csv",
        database,
    )
    loaded = load_dataset(dataset_id, database)
    filtered = filter_dataframe(
        loaded,
        "date",
        start_date=pd.Timestamp("2026-02-01").date(),
        numeric_column="amount",
        operator=">=",
        threshold=20,
    )

    assert len(filtered) == 2
    assert list(filtered["amount"]) == [20, 30]


def test_invalid_dataset_id_raises(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_dataset(999, tmp_path / "missing.db")
