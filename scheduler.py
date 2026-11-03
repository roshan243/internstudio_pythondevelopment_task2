"""Blocking APScheduler-based daily, weekly, and monthly report scheduling."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from config import Settings
from database import Database
from data_collector import load_transactions
from email_sender import send_reports
from excel_generator import generate_excel_report
from pdf_generator import generate_pdf_report

logger = logging.getLogger(__name__)


def start_scheduler(
    frequency: str,
    report_time: str,
    settings: Settings,
    day_of_week: str = "mon",
    day_of_month: int = 1,
    email_recipients: list[str] | None = None,
) -> None:
    """Start the foreground scheduler and generate reports on each run."""
    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("Frequency must be daily, weekly, or monthly.")
    try:
        hour_text, minute_text = report_time.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, TypeError) as exc:
        raise ValueError("Report time must use the 24-hour HH:MM format.") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Report time must use the 24-hour HH:MM format.")
    if frequency == "monthly" and not 1 <= day_of_month <= 28:
        raise ValueError("Monthly scheduling day must be between 1 and 28.")
    if frequency == "weekly" and day_of_week.lower() not in {
        "mon", "tue", "wed", "thu", "fri", "sat", "sun"
    }:
        raise ValueError("Weekday must be mon, tue, wed, thu, fri, sat, or sun.")

    def generate_scheduled_reports() -> None:
        logger.info("Scheduled report generation started.")
        try:
            data = load_transactions(Database(settings.database_path))
            generated_reports = [
                generate_pdf_report(data, settings.reports_dir, settings.archive_dir),
                generate_excel_report(data, settings.reports_dir, settings.archive_dir),
            ]
            if email_recipients:
                send_reports(email_recipients, generated_reports, settings)
            logger.info("Scheduled report generation completed.")
        except Exception:
            logger.exception("Scheduled report generation or delivery failed.")
            raise

    scheduler = BlockingScheduler()
    trigger_arguments = {"hour": hour, "minute": minute}
    if frequency == "weekly":
        trigger_arguments["day_of_week"] = day_of_week.lower()
    elif frequency == "monthly":
        trigger_arguments["day"] = day_of_month
    scheduler.add_job(
        generate_scheduled_reports,
        trigger=frequency,
        id="automated_report_generation",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        **trigger_arguments,
    )
    logger.info(
        "Scheduler started: %s at %02d:%02d. Press Ctrl+C to stop.",
        frequency,
        hour,
        minute,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
    except Exception:
        logger.exception("Scheduler failed.")
        raise
