from pathlib import Path
import smtplib

import pandas as pd
import pytest

from reporting import config
from reporting.data_service import save_dataframe
from reporting.database import connect, initialize_database
from reporting.delivery import send_report_email, validate_email
from reporting.scheduling import (
    claim_schedule_run,
    create_schedule,
    list_schedules,
    set_schedule_state,
    validate_schedule,
)
from reporting.scheduler_worker import refresh_jobs
from apscheduler.schedulers.background import BackgroundScheduler


def test_validate_email():
    assert validate_email(" analyst@example.org ") == "analyst@example.org"
    with pytest.raises(ValueError, match="valid recipient"):
        validate_email("not-an-email")


class MockSMTP:
    instances = []
    should_fail = False

    def __init__(self, *args, **kwargs):
        self.sent = []
        self.__class__.instances.append(self)

    def ehlo(self):
        pass

    def starttls(self, **kwargs):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        self.sent.append(message)
        if self.__class__.should_fail:
            raise smtplib.SMTPException("test failure")

    def quit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def mail_setup(tmp_path, monkeypatch):
    database = tmp_path / "mail.db"
    initialize_database(database)
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"%PDF test")
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(config, "SMTP_PORT", 587)
    monkeypatch.setattr(config, "SMTP_FROM", "reports@example.org")
    monkeypatch.setattr(config, "SMTP_USERNAME", "")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "")
    monkeypatch.setattr(config, "SMTP_USE_SSL", False)
    monkeypatch.setattr(config, "SMTP_STARTTLS", False)
    monkeypatch.setattr(config, "SMTP_RETRY_COUNT", 3)
    monkeypatch.setattr("reporting.delivery.smtplib.SMTP", MockSMTP)
    monkeypatch.setattr("reporting.delivery.time.sleep", lambda _seconds: None)
    MockSMTP.instances = []
    MockSMTP.should_fail = False
    return database, attachment


def test_email_delivery_success_is_logged(mail_setup):
    database, attachment = mail_setup

    result = send_report_email(
        "reader@example.org", "Monthly report", "Attached.", attachment, database_path=database
    )

    assert result["status"] == "success"
    assert result["attempts"] == 1
    assert MockSMTP.instances[0].sent[0]["To"] == "reader@example.org"
    with connect(database) as connection:
        row = connection.execute("SELECT status,attempts FROM email_deliveries").fetchone()
    assert row["status"] == "success"
    assert row["attempts"] == 1


def test_email_delivery_retries_and_records_failure(mail_setup):
    database, attachment = mail_setup
    MockSMTP.should_fail = True

    result = send_report_email(
        "reader@example.org", "Monthly report", "Attached.", attachment, database_path=database
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 3
    with connect(database) as connection:
        row = connection.execute("SELECT status,attempts,error FROM email_deliveries").fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] == 3
    assert "test failure" in row["error"]


def test_invalid_email_is_recorded(mail_setup):
    database, attachment = mail_setup
    with pytest.raises(ValueError, match="valid recipient"):
        send_report_email("invalid", "Subject", "Body", attachment, database_path=database)
    with connect(database) as connection:
        row = connection.execute("SELECT status,error FROM email_deliveries").fetchone()
    assert row["status"] == "failed"


def test_schedule_configuration_and_duplicate_guard(tmp_path):
    database = tmp_path / "schedules.db"
    initialize_database(database)
    dataset_id = save_dataframe(
        pd.DataFrame({"value": [1, 2]}), "Demo", "demo.csv", database
    )
    config_payload = {"title": "Daily snapshot", "dataset_id": dataset_id, "format": "pdf"}
    schedule_id = create_schedule(
        "Daily", config_payload, "daily", "08:30", database_path=database
    )
    with pytest.raises(ValueError, match="already exists"):
        create_schedule("Duplicate", config_payload, "daily", "08:30", database_path=database)
    set_schedule_state(schedule_id, paused=True, database_path=database)
    assert bool(list_schedules(database).iloc[0]["paused"])
    assert claim_schedule_run(schedule_id, "2026-11-10T08:30", database)
    assert not claim_schedule_run(schedule_id, "2026-11-10T08:30", database)


def test_weekly_and_monthly_schedule_validation():
    payload = {"title": "Report", "dataset_id": 1, "format": "pdf"}
    with pytest.raises(ValueError, match="weekday"):
        validate_schedule("Weekly", payload, "weekly", "09:00")
    with pytest.raises(ValueError, match="1 to 28"):
        validate_schedule("Monthly", payload, "monthly", "09:00", monthday=31)


def test_scheduler_refresh_is_idempotent(tmp_path, monkeypatch):
    database = tmp_path / "worker.db"
    initialize_database(database)
    monkeypatch.setattr("reporting.database.DATABASE_PATH", database)
    config_payload = {"title": "Scheduled", "dataset_id": 1, "format": "csv"}
    create_schedule("Every day", config_payload, "daily", "08:00", database_path=database)
    create_schedule(
        "Every Monday",
        {**config_payload, "title": "Weekly"},
        "weekly",
        "09:30",
        weekday=0,
        database_path=database,
    )
    scheduler = BackgroundScheduler()
    scheduler.start(paused=True)
    try:
        refresh_jobs(scheduler)
        first_jobs = scheduler.get_jobs()
        next_times = {job.id: job.next_run_time for job in first_jobs}
        refresh_jobs(scheduler)

        assert len(scheduler.get_jobs()) == 2
        assert {job.id: job.next_run_time for job in scheduler.get_jobs()} == next_times
    finally:
        scheduler.shutdown(wait=False)
