"""Formatted Excel workbook generation with tables and charts."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo

from archive_manager import archive_report, create_report_path
from data_processor import category_summary, monthly_summary, summarize_transactions

logger = logging.getLogger(__name__)
HEADER_FILL = PatternFill("solid", fgColor="183153")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(size=16, bold=True, color="183153")


def generate_excel_report(
    transactions: pd.DataFrame,
    reports_dir: Path,
    archive_dir: Path,
    generated_at: datetime | None = None,
) -> Path:
    """Generate, save, and archive a multi-sheet Excel report."""
    generated_at = generated_at or datetime.now()
    output_path = create_report_path(reports_dir, "excel", generated_at)
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Summary"
    summary = summarize_transactions(transactions)
    summary_sheet["A1"] = "Automated Transaction Report"
    summary_sheet["A1"].font = TITLE_FONT
    summary_sheet["A2"] = "Generated"
    summary_sheet["B2"] = generated_at.strftime("%Y-%m-%d %H:%M:%S")
    summary_sheet.append([])
    summary_sheet.append(["Measure", "Value"])
    for cell in summary_sheet[4]:
        _style_header(cell)
    for label, value in (
        ("Transactions", summary["record_count"]),
        ("Total amount", summary["total"]),
        ("Average amount", summary["average"]),
        ("Minimum amount", summary["minimum"]),
        ("Maximum amount", summary["maximum"]),
    ):
        summary_sheet.append([label, value])
    for row in range(6, 11):
        summary_sheet.cell(row, 2).number_format = '"$"#,##0.00'

    monthly = monthly_summary(transactions)
    category = category_summary(transactions)
    _write_dataframe(workbook, "Monthly Summary", monthly)
    _write_dataframe(workbook, "Category Summary", category)
    _write_dataframe(
        workbook,
        "Transaction Data",
        transactions.drop(columns=["id"], errors="ignore"),
    )
    _add_chart(summary_sheet, workbook["Monthly Summary"], "Monthly totals", 13)
    _add_chart(summary_sheet, workbook["Category Summary"], "Category totals", 29)
    for sheet in workbook.worksheets:
        _format_sheet(sheet)

    workbook.save(output_path)
    archive_report(output_path, archive_dir)
    logger.info("Generated Excel report at %s.", output_path)
    return output_path


def _write_dataframe(workbook: Workbook, title: str, frame: pd.DataFrame) -> None:
    sheet = workbook.create_sheet(title)
    headers = list(frame.columns)
    sheet.append(headers)
    for cell in sheet[1]:
        _style_header(cell)
    for row in frame.itertuples(index=False, name=None):
        sheet.append([_excel_value(value) for value in row])
    if headers and len(frame):
        table = ExcelTable(
            displayName=title.replace(" ", "") + "Table",
            ref=f"A1:{_column_letter(len(headers))}{len(frame) + 1}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)
    for column_name in ("total", "average", "amount"):
        if column_name in headers:
            index = headers.index(column_name) + 1
            for row in range(2, len(frame) + 2):
                sheet.cell(row, index).number_format = '"$"#,##0.00'


def _add_chart(summary_sheet, source_sheet, title: str, anchor_row: int) -> None:
    if source_sheet.max_row < 2 or source_sheet.max_column < 3:
        return
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = title
    chart.y_axis.title = "Amount"
    chart.x_axis.title = source_sheet.cell(1, 1).value
    chart.height = 7
    chart.width = 14
    values = Reference(
        source_sheet,
        min_col=3,
        min_row=1,
        max_row=source_sheet.max_row,
    )
    labels = Reference(source_sheet, min_col=1, min_row=2, max_row=source_sheet.max_row)
    chart.add_data(values, titles_from_data=True)
    chart.set_categories(labels)
    summary_sheet.add_chart(chart, f"D{anchor_row}")


def _format_sheet(sheet) -> None:
    sheet.freeze_panes = "A2" if sheet.title not in {"Summary"} else "A4"
    sheet.sheet_view.showGridLines = False
    for column_cells in sheet.columns:
        column_letter = column_cells[0].column_letter
        width = max(
            (len(str(cell.value)) for cell in column_cells if cell.value is not None),
            default=10,
        )
        sheet.column_dimensions[column_letter].width = min(max(width + 2, 12), 48)
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="center")


def _style_header(cell) -> None:
    cell.fill = HEADER_FILL
    cell.font = HEADER_FONT
    cell.alignment = Alignment(vertical="center")


def _excel_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
