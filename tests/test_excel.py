from datetime import datetime

import pandas as pd
from openpyxl import load_workbook

from excel_generator import generate_excel_report


def test_excel_generation_has_sheets_tables_and_charts(tmp_path):
    data = pd.DataFrame(
        [
            {
                "id": 1,
                "transaction_date": "2025-01-05",
                "category": "Sales",
                "amount": 100.0,
                "description": "Order",
            },
            {
                "id": 2,
                "transaction_date": "2025-02-05",
                "category": "Operations",
                "amount": 50.0,
                "description": "Supplies",
            },
        ]
    )
    reports = tmp_path / "reports"
    archive = tmp_path / "archive"
    report = generate_excel_report(
        data, reports, archive, datetime(2025, 5, 1, 9, 30)
    )
    workbook = load_workbook(report)

    assert set(workbook.sheetnames) == {
        "Summary",
        "Monthly Summary",
        "Category Summary",
        "Transaction Data",
    }
    assert workbook["Summary"]["B6"].value == 150.0
    assert len(workbook["Summary"]._charts) == 2
    assert len(workbook["Monthly Summary"].tables) == 1
    assert (archive / report.name).is_file()
