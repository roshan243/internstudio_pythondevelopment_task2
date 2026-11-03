from unittest.mock import MagicMock, patch

import pytest

from config import Settings
from scheduler import start_scheduler


@pytest.mark.parametrize(
    ("frequency", "options"),
    [
        ("daily", {}),
        ("weekly", {"day_of_week": "fri"}),
        ("monthly", {"day": 12}),
    ],
)
def test_scheduler_registers_non_overlapping_report_job(
    tmp_path, frequency, options
):
    settings = Settings(
        base_dir=tmp_path,
        database_path=tmp_path / "data" / "test.db",
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "archive",
        logs_dir=tmp_path / "logs",
    )
    scheduler = MagicMock()
    with patch("scheduler.BlockingScheduler", return_value=scheduler):
        start_scheduler(
            frequency,
            "08:45",
            settings,
            day_of_week="fri",
            day_of_month=12,
        )

    job = scheduler.add_job.call_args
    assert job.kwargs["trigger"] == frequency
    assert job.kwargs["hour"] == 8
    assert job.kwargs["minute"] == 45
    assert job.kwargs["coalesce"] is True
    assert job.kwargs["max_instances"] == 1
    for key, value in options.items():
        assert job.kwargs[key] == value
    scheduler.start.assert_called_once()


def test_scheduler_rejects_invalid_time_before_starting(tmp_path):
    settings = Settings(base_dir=tmp_path)
    with pytest.raises(ValueError, match="HH:MM"):
        start_scheduler("daily", "25:00", settings)


@pytest.mark.parametrize(
    ("recipients", "should_send"),
    [(None, False), (["reports@example.com"], True)],
)
def test_scheduled_email_is_opt_in(tmp_path, recipients, should_send):
    settings = Settings(
        base_dir=tmp_path,
        database_path=tmp_path / "data" / "test.db",
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "archive",
        logs_dir=tmp_path / "logs",
    )
    scheduler = MagicMock()
    scheduler.start.side_effect = lambda: scheduler.add_job.call_args.args[0]()
    pdf_path = tmp_path / "report.pdf"
    excel_path = tmp_path / "report.xlsx"

    with (
        patch("scheduler.BlockingScheduler", return_value=scheduler),
        patch("scheduler.load_transactions", return_value=object()),
        patch("scheduler.generate_pdf_report", return_value=pdf_path),
        patch("scheduler.generate_excel_report", return_value=excel_path),
        patch("scheduler.send_reports") as send_reports,
    ):
        start_scheduler(
            "daily",
            "08:45",
            settings,
            email_recipients=recipients,
        )

    if should_send:
        send_reports.assert_called_once_with(
            recipients, [pdf_path, excel_path], settings
        )
    else:
        send_reports.assert_not_called()
