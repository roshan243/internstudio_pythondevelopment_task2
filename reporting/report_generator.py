"""Professional PDF, Excel and CSV report generation."""

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import time
from typing import Optional
from datetime import date
import math
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reporting.config import OUTPUT_DIR
from reporting.database import connect
from reporting.data_service import load_dataset
from reporting.logging_config import LOGGER


SUPPORTED_FORMATS = {"pdf", "xlsx", "csv"}
SUPPORTED_CHARTS = {"bar", "line", "pie"}


def _safe_spreadsheet_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Prevent text cells from being interpreted as formulas by spreadsheet apps."""
    safe = frame.copy()
    formula_prefixes = ("=", "+", "-", "@", "\t", "\r")
    for column in safe.columns:
        if pd.api.types.is_object_dtype(safe[column]) or pd.api.types.is_string_dtype(safe[column]):
            safe[column] = safe[column].map(
                lambda value: "'" + value
                if isinstance(value, str) and value.startswith(formula_prefixes)
                else value
            )
    return safe


def validate_report_config(config: dict) -> dict:
    title = " ".join(str(config.get("title", "")).split()).strip()
    if not title:
        raise ValueError("Report title is required.")
    dataset_id = config.get("dataset_id")
    if not isinstance(dataset_id, int) or dataset_id <= 0:
        raise ValueError("Select a valid dataset.")
    output_format = str(config.get("format", "pdf")).lower().lstrip(".")
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError("Choose PDF, Excel (.xlsx), or CSV format.")
    chart = str(config.get("chart_type", "bar")).lower()
    if chart not in SUPPORTED_CHARTS:
        raise ValueError("Chart type must be bar, line, or pie.")
    columns = config.get("columns") or []
    if not isinstance(columns, (list, tuple)) or any(not isinstance(item, str) for item in columns):
        raise ValueError("Report columns must be a list of column names.")
    if len(set(columns)) != len(columns):
        raise ValueError("Report columns must not contain duplicates.")
    start_date = _date_string(config.get("start_date"))
    end_date = _date_string(config.get("end_date"))
    if start_date and end_date and start_date > end_date:
        raise ValueError("Report start date must be on or before its end date.")
    for selected_date in (start_date, end_date):
        if selected_date:
            try:
                date.fromisoformat(selected_date)
            except (TypeError, ValueError):
                raise ValueError("Report dates must use YYYY-MM-DD format.") from None
    numeric_column = config.get("numeric_column") or None
    operator = config.get("operator") or None
    threshold = config.get("threshold")
    if numeric_column:
        if operator not in {">", ">=", "=", "<=", "<"}:
            raise ValueError("Choose a valid numeric comparison.")
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            raise ValueError("Numeric filter threshold must be a number.") from None
        if not math.isfinite(threshold):
            raise ValueError("Numeric filter threshold must be finite.")
    else:
        operator = None
        threshold = None
    return {
        "title": title,
        "description": str(config.get("description", "")).strip(),
        "dataset_id": dataset_id,
        "format": output_format,
        "chart_type": chart,
        "columns": list(columns),
        "date_column": config.get("date_column") or None,
        "start_date": start_date,
        "end_date": end_date,
        "numeric_column": numeric_column,
        "operator": operator,
        "threshold": threshold,
        "destination": str(config.get("destination", "")).strip(),
    }


def _date_string(value) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _safe_filename(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.")[:70]
    return slug or "report"


def _summary(frame: pd.DataFrame) -> pd.DataFrame:
    values = [
        ("Rows", len(frame)),
        ("Columns", len(frame.columns)),
        ("Missing values", int(frame.isna().sum().sum())),
        ("Duplicate rows", int(frame.duplicated().sum())),
    ]
    for column in frame.select_dtypes(include="number").columns:
        values.append((f"{column} — total", frame[column].sum()))
        values.append((f"{column} — average", frame[column].mean()))
    return pd.DataFrame(values, columns=["Metric", "Value"])


def _chart_image(frame: pd.DataFrame, chart_type: str) -> Optional[BytesIO]:
    if frame.empty or not len(frame.columns):
        return None
    numeric = frame.select_dtypes(include="number")
    if numeric.empty:
        return None
    value_column = numeric.columns[0]
    label_column = next(
        (column for column in frame.columns if column != value_column),
        value_column,
    )
    grouped = (
        frame.groupby(label_column, dropna=False)[value_column]
        .sum()
        .sort_values(ascending=False)
        .head(12)
    )
    fig, axis = plt.subplots(figsize=(8, 3.5))
    if chart_type == "pie":
        axis.pie(grouped.values, labels=[str(v) for v in grouped.index], autopct="%1.1f%%")
    elif chart_type == "line":
        axis.plot([str(v) for v in grouped.index], grouped.values, marker="o", color="#0f766e")
    else:
        axis.bar([str(v) for v in grouped.index], grouped.values, color="#0f766e")
    axis.set_title(f"{value_column} by {label_column}")
    if chart_type != "pie":
        axis.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _write_pdf(path: Path, config: dict, frame: pd.DataFrame, generated_at: str) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(letter),
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["Normal"], alignment=TA_LEFT, textColor=colors.HexColor("#475569")))
    story = [
        Paragraph(escape(config["title"]), styles["Title"]),
        Paragraph(f"Generated {generated_at}", styles["ReportSubtitle"]),
        Spacer(1, 0.15 * inch),
    ]
    if config["description"]:
        story.extend([Paragraph(escape(config["description"]).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 0.12 * inch)])
    story.append(Paragraph("Summary and key statistics", styles["Heading2"]))
    summary = _summary(frame)
    summary_values = [list(summary.columns)] + summary.astype(str).values.tolist()
    table = Table(summary_values, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([table, Spacer(1, 0.2 * inch)])
    chart = _chart_image(frame, config["chart_type"])
    if chart is not None:
        story.extend([Paragraph("Visualization", styles["Heading2"]), Image(chart, width=7.6 * inch, height=3.1 * inch)])
    story.append(Paragraph("Data table", styles["Heading2"]))
    display = frame.head(500).fillna("").astype(str)
    table_data = [list(display.columns)] + display.values.tolist()
    wrapped = Table(table_data, repeatRows=1, hAlign="LEFT")
    wrapped.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(wrapped)
    if len(frame) > 500:
        story.append(Paragraph("The PDF table is limited to the first 500 rows; use Excel or CSV for the full dataset.", styles["Italic"]))
    doc.build(story)


def _write_excel(path: Path, config: dict, frame: pd.DataFrame, generated_at: str) -> None:
    safe_frame = _safe_spreadsheet_frame(frame)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        safe_frame.to_excel(writer, index=False, sheet_name="Data")
        _safe_spreadsheet_frame(_summary(frame)).to_excel(
            writer, index=False, sheet_name="Summary"
        )
        workbook = writer.book
        summary_sheet = workbook["Summary"]
        summary_sheet["D1"] = _safe_spreadsheet_frame(
            pd.DataFrame({"value": [config["title"]]})
        ).iloc[0, 0]
        summary_sheet["D2"] = f"Generated {generated_at}"
        summary_sheet["D1"].font = Font(bold=True, size=16, color="0F766E")
        data_sheet = workbook["Data"]
        data_sheet.freeze_panes = "A2"
        data_sheet.auto_filter.ref = data_sheet.dimensions
        for cell in data_sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="0F766E")
        numeric_columns = [
            index + 1
            for index, column in enumerate(frame.columns)
            if pd.api.types.is_numeric_dtype(frame[column])
        ]
        if numeric_columns and len(frame.columns) >= 1 and len(frame) > 0:
            chart_class = {"bar": BarChart, "line": LineChart, "pie": PieChart}[config["chart_type"]]
            chart = chart_class()
            chart.title = config["title"]
            values = Reference(data_sheet, min_col=numeric_columns[0], min_row=1, max_row=min(len(frame), 1000) + 1)
            labels = Reference(data_sheet, min_col=1, min_row=2, max_row=min(len(frame), 1000) + 1)
            chart.add_data(values, titles_from_data=True)
            if not isinstance(chart, PieChart):
                chart.set_categories(labels)
            summary_sheet.add_chart(chart, "D4")


def _write_csv(path: Path, config: dict, frame: pd.DataFrame, generated_at: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        output.write(f"# {config['title']}\n")
        output.write(f"# Generated: {generated_at}\n")
        if config["description"]:
            output.write(f"# {config['description'].replace(chr(10), ' ')}\n")
        output.write("# Summary and statistics\n")
        _safe_spreadsheet_frame(_summary(frame)).to_csv(output, index=False)
        output.write("\n# Data\n")
        _safe_spreadsheet_frame(frame).to_csv(output, index=False)


def generate_report(config: dict, database_path: Optional[Path] = None, output_dir: Optional[Path] = None) -> dict:
    from reporting.data_service import filter_dataframe

    start_time = time.monotonic()
    normalized = validate_report_config(config)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_id = None
    with connect(database_path) as connection:
        cursor = connection.execute(
            """INSERT INTO reports(title,description,dataset_id,format,status,created_at,config_json)
            VALUES(?,?,?,?,?,?,?)""",
            (
                normalized["title"],
                normalized["description"],
                normalized["dataset_id"],
                normalized["format"],
                "running",
                generated_at,
                json.dumps(normalized, default=str),
            ),
        )
        report_id = int(cursor.lastrowid)
    try:
        frame = load_dataset(normalized["dataset_id"], database_path)
        if normalized["columns"]:
            missing = set(normalized["columns"]) - set(frame.columns)
            if missing:
                raise ValueError(f"Unknown columns: {', '.join(sorted(missing))}")
        frame = filter_dataframe(
            frame,
            date_column=normalized["date_column"],
            start_date=pd.to_datetime(normalized["start_date"]).date() if normalized["start_date"] else None,
            end_date=pd.to_datetime(normalized["end_date"]).date() if normalized["end_date"] else None,
            numeric_column=normalized["numeric_column"],
            operator=normalized["operator"],
            threshold=normalized["threshold"],
        )
        if normalized["columns"]:
            frame = frame[normalized["columns"]]
        if normalized["chart_type"] == "pie":
            numeric = frame.select_dtypes(include="number")
            if not numeric.empty and (numeric.iloc[:, 0] < 0).any():
                raise ValueError("Pie charts require non-negative values; choose a bar or line chart.")
        root_directory = Path(output_dir or OUTPUT_DIR).resolve()
        destination = Path(normalized["destination"])
        if destination.is_absolute() or destination.drive or ".." in destination.parts:
            raise ValueError("Report destination must be a folder inside the report archive.")
        directory = (root_directory / destination).resolve()
        if directory != root_directory and root_directory not in directory.parents:
            raise ValueError("Report destination must remain inside the report archive.")
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{report_id}_{_safe_filename(normalized['title'])}.{normalized['format']}"
        path = directory / filename
        if normalized["format"] == "pdf":
            _write_pdf(path, normalized, frame, generated_at)
        elif normalized["format"] == "xlsx":
            _write_excel(path, normalized, frame, generated_at)
        else:
            _write_csv(path, normalized, frame, generated_at)
        duration = time.monotonic() - start_time
        with connect(database_path) as connection:
            connection.execute(
                "UPDATE reports SET status='success',file_path=?,row_count=?,duration_seconds=? WHERE id=?",
                (str(path.resolve()), len(frame), duration, report_id),
            )
            connection.execute(
                """INSERT INTO execution_logs(report_id,event_type,status,duration_seconds,details,created_at)
                VALUES(?,?,?,?,?,?)""",
                (report_id, "generation", "success", duration, f"{len(frame)} report rows", generated_at),
            )
        LOGGER.info("Generated report %s at %s", report_id, path)
        return {"id": report_id, "path": path, "format": normalized["format"], "rows": len(frame)}
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        duration = time.monotonic() - start_time
        with connect(database_path) as connection:
            connection.execute(
                "UPDATE reports SET status='failed',error=?,duration_seconds=? WHERE id=?",
                (str(error)[:2000], duration, report_id),
            )
            connection.execute(
                """INSERT INTO execution_logs(report_id,event_type,status,duration_seconds,details,created_at)
                VALUES(?,?,?,?,?,?)""",
                (report_id, "generation", "failed", duration, str(error)[:2000], generated_at),
            )
        LOGGER.error("Report generation failed for %s: %s", report_id, error)
        raise
