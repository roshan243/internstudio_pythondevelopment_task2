"""Reusable report calculations and date-range validation."""

from __future__ import annotations

from datetime import date

import pandas as pd


class DataProcessingError(ValueError):
    """Raised for invalid report filters or processing inputs."""


def validate_date_range(
    start_date: str | None, end_date: str | None
) -> tuple[str | None, str | None]:
    """Validate ISO dates and ensure the start does not follow the end."""
    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except ValueError as exc:
        raise DataProcessingError("Dates must use the YYYY-MM-DD format.") from exc
    if start and end and start > end:
        raise DataProcessingError("Start date must be on or before end date.")
    return start.isoformat() if start else None, end.isoformat() if end else None


def summarize_transactions(frame: pd.DataFrame) -> dict[str, int | float]:
    """Return headline statistics for a transaction DataFrame."""
    amounts = pd.to_numeric(frame.get("amount", pd.Series(dtype=float)), errors="coerce")
    amounts = amounts.dropna()
    return {
        "record_count": int(len(amounts)),
        "total": round(float(amounts.sum()), 2),
        "average": round(float(amounts.mean()), 2) if not amounts.empty else 0.0,
        "minimum": round(float(amounts.min()), 2) if not amounts.empty else 0.0,
        "maximum": round(float(amounts.max()), 2) if not amounts.empty else 0.0,
    }


def monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transaction totals and counts by calendar month."""
    if frame.empty:
        return pd.DataFrame(columns=["month", "record_count", "total", "average"])
    data = frame.copy()
    data["month"] = pd.to_datetime(data["transaction_date"]).dt.to_period("M").astype(str)
    result = data.groupby("month", as_index=False).agg(
        record_count=("amount", "count"),
        total=("amount", "sum"),
        average=("amount", "mean"),
    )
    return _round_amount_columns(result)


def category_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transaction totals and counts by category."""
    if frame.empty:
        return pd.DataFrame(columns=["category", "record_count", "total", "average"])
    result = frame.groupby("category", as_index=False).agg(
        record_count=("amount", "count"),
        total=("amount", "sum"),
        average=("amount", "mean"),
    )
    result = _round_amount_columns(result)
    return result.sort_values("total", ascending=False).reset_index(drop=True)


def _round_amount_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in ("total", "average"):
        frame[column] = frame[column].round(2)
    return frame
