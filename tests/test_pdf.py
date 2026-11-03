from datetime import datetime

import pandas as pd

from pdf_generator import generate_pdf_report


def test_pdf_generation_and_archiving(tmp_path):
    data = pd.DataFrame(
        [
            {
                "id": 1,
                "transaction_date": "2025-01-05",
                "category": "Sales",
                "amount": 100.0,
                "description": "Order",
            }
        ]
    )
    reports = tmp_path / "reports"
    archive = tmp_path / "archive"

    report = generate_pdf_report(
        data, reports, archive, datetime(2025, 5, 1, 9, 30)
    )

    assert report.is_file()
    assert report.stat().st_size > 1000
    assert (archive / report.name).is_file()
    assert report.read_bytes().startswith(b"%PDF-")


def test_pdf_generation_with_empty_data(tmp_path):
    data = pd.DataFrame(
        columns=["id", "transaction_date", "category", "amount", "description"]
    )
    report = generate_pdf_report(data, tmp_path / "reports", tmp_path / "archive")
    assert report.is_file()
