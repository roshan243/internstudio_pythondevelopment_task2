"""Separate persistent APScheduler worker for recurring report generation."""

import json
import signal
import time
from datetime import datetime
import sqlite3

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from reporting.database import connect, fetch_frame, initialize_database
from reporting.logging_config import LOGGER
from reporting.report_generator import generate_report
from reporting.scheduling import claim_schedule_run


def _run_report_schedule(schedule_id: int) -> None:
    run_key = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M")
    if not claim_schedule_run(schedule_id, run_key):
        LOGGER.info("Schedule %s already claimed for %s", schedule_id, run_key)
        return
    schedules = fetch_frame("SELECT * FROM scheduled_reports WHERE id=?", (schedule_id,))
    if schedules.empty:
        return
    schedule = schedules.iloc[0]
    started = time.monotonic()
    try:
        result = generate_report(json.loads(schedule["config_json"]))
        status = "success"
        details = f"Generated report #{result['id']}"
        report_id = result["id"]
    except (ValueError, OSError, KeyError, TypeError, ImportError, sqlite3.Error) as error:
        status = "failed"
        details = str(error)[:2000]
        report_id = None
        LOGGER.error("Scheduled report %s failed: %s", schedule_id, error)
    with connect() as connection:
        connection.execute(
            """INSERT INTO execution_logs(report_id,schedule_id,event_type,status,
            duration_seconds,details,created_at) VALUES(?,?,?,?,?,?,?)""",
            (
                report_id,
                schedule_id,
                "scheduled_generation",
                status,
                time.monotonic() - started,
                details,
                datetime.now().astimezone().isoformat(timespec="seconds"),
            ),
        )


def refresh_jobs(scheduler: BackgroundScheduler) -> None:
    schedules = fetch_frame("SELECT * FROM scheduled_reports")
    active = set()
    for _, row in schedules.iterrows():
        job_id = f"report-schedule-{int(row['id'])}"
        if not bool(row["enabled"]) or bool(row["paused"]):
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            continue
        hour, minute = (int(part) for part in row["run_time"].split(":"))
        options = {"hour": hour, "minute": minute}
        if row["frequency"] == "weekly":
            options["day_of_week"] = str(int(row["weekday"]))
        elif row["frequency"] == "monthly":
            options["day"] = int(row["monthday"])
        trigger = CronTrigger(**options)
        existing = scheduler.get_job(job_id)
        if existing is None:
            scheduler.add_job(
                _run_report_schedule,
                trigger=trigger,
                id=job_id,
                args=[int(row["id"])],
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
        elif str(existing.trigger) != str(trigger):
            scheduler.reschedule_job(job_id, trigger=trigger)
        active.add(job_id)
    for job in scheduler.get_jobs():
        if job.id.startswith("report-schedule-") and job.id not in active:
            scheduler.remove_job(job.id)


def main() -> None:
    initialize_database()
    scheduler = BackgroundScheduler(timezone="local")
    scheduler.start()
    refresh_jobs(scheduler)
    LOGGER.info("Report scheduler worker started.")

    def stop_worker(_signum, _frame) -> None:
        scheduler.shutdown(wait=False)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_worker)
    signal.signal(signal.SIGTERM, stop_worker)
    try:
        while True:
            time.sleep(30)
            refresh_jobs(scheduler)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
