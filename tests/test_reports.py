import json

from openpyxl import load_workbook
import pandas as pd
import pytest

from reporting.archive import delete_archived_report, list_reports
from reporting.data_service import save_dataframe
from reporting.database import connect, initialize_database
from reporting.report_generator import generate_report, validate_report_config


@pytest.fixture
def report_environment(tmp_path):
    database = tmp_path / "reports.db"
    output = tmp_path / "archive"
    initialize_database(database)
    dataset_id = save_dataframe(
        pd.DataFrame(
            {
                "date": ["2026-01-02", "2026-02-04", "2026-03-10"],
                "region": ["North", "South", "North"],
                "revenue": [100.0, 250.0, 300.0],
            }
        ),
        "Quarterly Sales",
        "sales.csv",
        database,
    )
    return database, output, dataset_id


@pytest.mark.parametrize("output_format", ["pdf", "xlsx", "csv"])
def test_generate_all_report_formats(report_environment, output_format):
    database, output, dataset_id = report_environment
    config = {
        "title": f"Sales {output_format}",
        "description": "Quarterly results",
        "dataset_id": dataset_id,
        "columns": ["date", "region", "revenue"],
        "format": output_format,
        "chart_type": "bar",
        "date_column": "date",
        "start_date": "2026-02-01",
        "end_date": "2026-03-31",
    }

    result = generate_report(config, database, output)

    assert result["path"].is_file()
    assert result["rows"] == 2
    assert result["format"] == output_format
    contents = result["path"].read_bytes()
    assert contents.startswith(b"%PDF") if output_format == "pdf" else contents.startswith(b"PK") if output_format == "xlsx" else b"region" in contents
    reports = list_reports(database, search=f"Sales {output_format}")
    assert reports.iloc[0]["status"] == "success"


def test_invalid_report_configuration():
    with pytest.raises(ValueError, match="title"):
        validate_report_config({"dataset_id": 1})
    with pytest.raises(ValueError, match="on or before"):
        validate_report_config(
            {
                "title": "Bad date range",
                "dataset_id": 1,
                "start_date": "2026-03-01",
                "end_date": "2026-01-01",
            }
        )


def test_generation_failure_is_archived(report_environment):
    database, output, dataset_id = report_environment
    with pytest.raises(ValueError, match="Unknown columns"):
        generate_report(
            {
                "title": "Broken report",
                "dataset_id": dataset_id,
                "columns": ["does-not-exist"],
                "format": "csv",
            },
            database,
            output,
        )
    with connect(database) as connection:
        report = connection.execute("SELECT status,error FROM reports").fetchone()
    assert report["status"] == "failed"
    assert "Unknown columns" in report["error"]


def test_archive_deletion_is_scoped(report_environment):
    database, output, dataset_id = report_environment
    result = generate_report({"title": "Delete me", "dataset_id": dataset_id, "format": "csv"}, database, output)

    delete_archived_report(result["id"], database, output)

    assert not result["path"].exists()
    assert list_reports(database).empty


def test_archive_rejects_file_outside_archive(report_environment, tmp_path):
    database, output, dataset_id = report_environment
    result = generate_report({"title": "Protected", "dataset_id": dataset_id, "format": "csv"}, database, output)
    outside = tmp_path / "valuable.txt"
    outside.write_text("keep", encoding="utf-8")
    with connect(database) as connection:
        connection.execute("UPDATE reports SET file_path=? WHERE id=?", (str(outside), result["id"]))

    with pytest.raises(ValueError, match="outside"):
        delete_archived_report(result["id"], database, output)
    assert outside.read_text(encoding="utf-8") == "keep"


def test_report_destination_is_scoped_to_archive(report_environment):
    database, output, dataset_id = report_environment
    result = generate_report(
        {
            "title": "Nested",
            "dataset_id": dataset_id,
            "format": "csv",
            "destination": "monthly/2026",
        },
        database,
        output,
    )
    assert result["path"].parent == output / "monthly" / "2026"

    with pytest.raises(ValueError, match="inside the report archive"):
        generate_report(
            {
                "title": "Escaped",
                "dataset_id": dataset_id,
                "format": "csv",
                "destination": "../outside",
            },
            database,
            output,
        )


def test_spreadsheet_exports_escape_formula_text(report_environment):
    database, output, _dataset_id = report_environment
    formula_id = save_dataframe(
        pd.DataFrame({"label": ["=1+1"], "value": [2]}),
        "Formula Input",
        "formula.csv",
        database,
    )
    csv_report = generate_report(
        {"title": "Safe CSV", "dataset_id": formula_id, "format": "csv"},
        database,
        output,
    )
    assert b"'=1+1" in csv_report["path"].read_bytes()

    excel_report = generate_report(
        {"title": "Safe Excel", "dataset_id": formula_id, "format": "xlsx"},
        database,
        output,
    )
    workbook = load_workbook(excel_report["path"], data_only=False)
    assert workbook["Data"]["A2"].value == "'=1+1"
