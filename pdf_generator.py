"""Professional PDF report generation with summary tables and charts."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from archive_manager import archive_report, create_report_path
from data_processor import category_summary, monthly_summary, summarize_transactions

logger = logging.getLogger(__name__)
NAVY = colors.HexColor("#183153")
BLUE = colors.HexColor("#2F6690")
PALE_BLUE = colors.HexColor("#EAF1F8")


def generate_pdf_report(
    transactions: pd.DataFrame,
    reports_dir: Path,
    archive_dir: Path,
    generated_at: datetime | None = None,
) -> Path:
    """Generate, save, and archive a PDF summary and transaction detail report."""
    generated_at = generated_at or datetime.now()
    output_path = create_report_path(reports_dir, "pdf", generated_at)
    summary = summarize_transactions(transactions)
    styles = getSampleStyleSheet()
    styles["Title"].textColor = NAVY
    styles["Title"].alignment = TA_CENTER
    styles["Heading2"].textColor = NAVY
    elements = [
        Paragraph("Automated Transaction Report", styles["Title"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Generated {generated_at:%B %d, %Y at %H:%M}",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Executive summary", styles["Heading2"]),
        _table(
            [
                ["Measure", "Value"],
                ["Transactions", str(summary["record_count"])],
                ["Total amount", _currency(summary["total"])],
                ["Average amount", _currency(summary["average"])],
                ["Minimum amount", _currency(summary["minimum"])],
                ["Maximum amount", _currency(summary["maximum"])],
            ],
            [75 * mm, 75 * mm],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Monthly performance", styles["Heading2"]),
    ]

    monthly = monthly_summary(transactions)
    category = category_summary(transactions)
    if not monthly.empty:
        chart = _make_chart(monthly, "month", "total", "Monthly transaction totals")
        elements.append(Image(chart, width=160 * mm, height=70 * mm))
    else:
        elements.append(Paragraph("No transaction data is available.", styles["Normal"]))
    elements.extend(
        [
            _table(
                _summary_table_data(monthly, "Month"),
                [50 * mm, 30 * mm, 35 * mm, 35 * mm],
            ),
            Spacer(1, 5 * mm),
            Paragraph("Category summary", styles["Heading2"]),
            _table(
                _summary_table_data(category, "Category"),
                [55 * mm, 30 * mm, 35 * mm, 35 * mm],
            ),
            PageBreak(),
            Paragraph("Transaction details", styles["Heading2"]),
            _detail_table(transactions),
        ]
    )

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="Automated Transaction Report",
        author="Automated Report Generation & Delivery System",
    )
    document.build(elements, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
    archive_report(output_path, archive_dir)
    logger.info("Generated PDF report at %s.", output_path)
    return output_path


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 1), (-1, -1), PALE_BLUE),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CAD5E0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _summary_table_data(frame: pd.DataFrame, first_header: str) -> list[list[str]]:
    rows = [[first_header, "Records", "Total", "Average"]]
    for row in frame.itertuples(index=False):
        rows.append(
            [
                str(row[0]),
                str(row[1]),
                _currency(row[2]),
                _currency(row[3]),
            ]
        )
    if len(rows) == 1:
        rows.append(["No data", "0", _currency(0), _currency(0)])
    return rows


def _detail_table(transactions: pd.DataFrame) -> Table:
    rows = [["Date", "Category", "Amount", "Description"]]
    for row in transactions.itertuples(index=False):
        rows.append(
            [
                str(row.transaction_date),
                str(row.category)[:32],
                _currency(row.amount),
                str(row.description)[:90],
            ]
        )
    if len(rows) == 1:
        rows.append(["No transactions", "", "", ""])
    return _table(rows, [36 * mm, 42 * mm, 35 * mm, 150 * mm])


def _make_chart(frame: pd.DataFrame, label: str, value: str, title: str) -> BytesIO:
    buffer = BytesIO()
    figure, axis = plt.subplots(figsize=(8, 3.5))
    labels = frame[label].astype(str).tolist()
    axis.bar(range(len(labels)), frame[value], color="#2F6690")
    axis.set_xticks(range(len(labels)), labels)
    axis.set_title(title, fontsize=11, color="#183153")
    axis.set_ylabel("Amount")
    axis.tick_params(axis="x", labelrotation=25)
    figure.tight_layout()
    figure.savefig(buffer, format="png", dpi=150)
    plt.close(figure)
    buffer.seek(0)
    return buffer


def _draw_page_number(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BLUE)
    canvas.drawRightString(
        document.pagesize[0] - 15 * mm,
        9 * mm,
        f"Page {document.page}",
    )
    canvas.restoreState()


def _currency(value: int | float) -> str:
    return f"${float(value):,.2f}"
