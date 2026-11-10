"""Dataset ingestion, validation, cleaning and filtering."""

import json
from io import StringIO
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from reporting.database import connect, fetch_frame, store_dataset


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 100


def clean_dataframe(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if frame.empty:
        raise ValueError("The dataset has no data rows.")
    if len(frame.columns) > MAX_COLUMNS:
        raise ValueError(f"Datasets may have at most {MAX_COLUMNS} columns.")
    data = frame.copy()
    data.columns = _unique_column_names(data.columns)
    original_rows = len(data)
    data = data.dropna(how="all")
    if data.empty:
        raise ValueError("The dataset contains no non-empty data rows.")
    missing_before = int(data.isna().sum().sum())
    rows_before_deduplication = len(data)
    for column in data.columns:
        if pd.api.types.is_numeric_dtype(data[column]):
            median = data[column].median()
            fill_value = median if pd.notna(median) else 0
            data[column] = data[column].fillna(fill_value)
        else:
            data[column] = data[column].fillna("").astype(str).str.strip()
    data = data.drop_duplicates()
    removed_duplicates = rows_before_deduplication - len(data)
    data = data.reset_index(drop=True)
    return data, {
        "input_rows": original_rows,
        "clean_rows": len(data),
        "missing_values_filled": missing_before,
        "duplicates_removed": removed_duplicates,
    }


def _unique_column_names(columns) -> list[str]:
    seen = {}
    output = []
    for index, column in enumerate(columns, start=1):
        name = " ".join(str(column).strip().split()) or f"column_{index}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        output.append(name if count == 0 else f"{name}_{count + 1}")
    return output


def read_uploaded_dataset(filename: str, content: bytes) -> pd.DataFrame:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploads must be 10 MB or smaller.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xlsm"}:
        raise ValueError("Upload a CSV or Excel .xlsx file.")
    from io import BytesIO

    try:
        if suffix == ".csv":
            frame = pd.read_csv(BytesIO(content))
        else:
            frame = pd.read_excel(BytesIO(content), engine="openpyxl")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError, OSError, ValueError) as error:
        raise ValueError(f"Could not parse uploaded data: {error}") from error
    if len(frame) > MAX_ROWS:
        raise ValueError(f"Datasets may have at most {MAX_ROWS:,} rows.")
    cleaned, _stats = clean_dataframe(frame)
    return cleaned


def save_dataframe(
    frame: pd.DataFrame,
    name: str,
    source_name: str,
    database_path: Optional[Path] = None,
) -> int:
    cleaned, _stats = clean_dataframe(frame)
    records_json = cleaned.to_json(orient="records", date_format="iso", force_ascii=False)
    return store_dataset(
        name=name.strip() or Path(source_name).stem,
        source_name=Path(source_name).name,
        columns_json=json.dumps(list(cleaned.columns), ensure_ascii=False),
        records_json=records_json,
        row_count=len(cleaned),
        database_path=database_path,
    )


def load_dataset(dataset_id: int, database_path: Optional[Path] = None) -> pd.DataFrame:
    from reporting.database import initialize_database

    initialize_database(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT records_json FROM datasets WHERE id=?", (dataset_id,)
        ).fetchone()
    if row is None:
        raise ValueError("Dataset not found.")
    return pd.read_json(StringIO(row["records_json"]), orient="records")


def list_datasets(database_path: Optional[Path] = None) -> pd.DataFrame:
    return fetch_frame(
        "SELECT id,name,source_name,row_count,created_at FROM datasets ORDER BY id DESC",
        (),
        database_path,
    )


def filter_dataframe(
    frame: pd.DataFrame,
    date_column: Optional[str] = None,
    start_date=None,
    end_date=None,
    numeric_column: Optional[str] = None,
    operator: Optional[str] = None,
    threshold: Optional[float] = None,
) -> pd.DataFrame:
    filtered = frame.copy()
    if date_column and (start_date or end_date):
        if date_column not in filtered:
            raise ValueError("Selected date column does not exist.")
        values = pd.to_datetime(filtered[date_column], errors="coerce")
        if start_date:
            filtered = filtered[values.dt.date >= start_date]
            values = pd.to_datetime(filtered[date_column], errors="coerce")
        if end_date:
            filtered = filtered[values.dt.date <= end_date]
    operators = {
        ">": lambda values, value: values > value,
        ">=": lambda values, value: values >= value,
        "<": lambda values, value: values < value,
        "<=": lambda values, value: values <= value,
        "=": lambda values, value: values == value,
    }
    if numeric_column and operator and threshold is not None:
        if numeric_column not in filtered or operator not in operators:
            raise ValueError("Choose a valid numeric filter.")
        values = pd.to_numeric(filtered[numeric_column], errors="coerce")
        filtered = filtered[operators[operator](values, threshold)]
    return filtered.reset_index(drop=True)
