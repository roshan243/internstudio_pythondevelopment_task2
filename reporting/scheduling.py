"""Persistent daily, weekly and monthly report schedule configuration."""

from datetime import datetime, timezone
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from reporting.database import connect, fetch_frame
from reporting.report_generator import validate_report_config


_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_schedule(
    name: str,
    config: dict,
    frequency: str,
    run_time: str,
    weekday: Optional[int] = None,
    monthday: Optional[int] = None,
) -> tuple[str, dict, str, Optional[int], Optional[int]]:
    clean_name = " ".join((name or "").split())
    if not clean_name:
        raise ValueError("Enter a schedule name.")
    clean_config = validate_report_config(config)
    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("Frequency must be daily, weekly, or monthly.")
    if not _TIME_PATTERN.fullmatch(run_time or ""):
        raise ValueError("Run time must use 24-hour HH:MM format.")
    if frequency == "weekly" and (weekday is None or weekday not in range(7)):
        raise ValueError("Choose a weekday for a weekly schedule.")
    if frequency == "monthly" and (monthday is None or monthday not in range(1, 29)):
        raise ValueError("Choose a day from 1 to 28 for a monthly schedule.")
    return (
        clean_name,
        clean_config,
        run_time,
        weekday if frequency == "weekly" else None,
        monthday if frequency == "monthly" else None,
    )


def create_schedule(
    name: str,
    config: dict,
    frequency: str,
    run_time: str,
    weekday: Optional[int] = None,
    monthday: Optional[int] = None,
    database_path: Optional[Path] = None,
) -> int:
    clean_name, clean_config, clean_time, clean_weekday, clean_monthday = validate_schedule(
        name, config, frequency, run_time, weekday, monthday
    )
    serialized = json.dumps(clean_config, sort_keys=True, default=str)
    with connect(database_path) as connection:
        duplicate = connection.execute(
            """SELECT id FROM scheduled_reports
            WHERE config_json=? AND frequency=? AND run_time=?
            AND COALESCE(weekday,-1)=COALESCE(?,-1)
            AND COALESCE(monthday,-1)=COALESCE(?,-1) AND enabled=1""",
            (serialized, frequency, clean_time, clean_weekday, clean_monthday),
        ).fetchone()
        if duplicate:
            raise ValueError("An enabled schedule with this report and time already exists.")
        cursor = connection.execute(
            """INSERT INTO scheduled_reports(name,config_json,frequency,run_time,weekday,monthday,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (
                clean_name,
                serialized,
                frequency,
                clean_time,
                clean_weekday,
                clean_monthday,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return int(cursor.lastrowid)


def list_schedules(database_path: Optional[Path] = None):
    return fetch_frame("SELECT * FROM scheduled_reports ORDER BY id DESC", (), database_path)


def set_schedule_state(
    schedule_id: int,
    *,
    enabled: Optional[bool] = None,
    paused: Optional[bool] = None,
    database_path: Optional[Path] = None,
) -> None:
    assignments = []
    values = []
    if enabled is not None:
        assignments.append("enabled=?")
        values.append(int(enabled))
    if paused is not None:
        assignments.append("paused=?")
        values.append(int(paused))
    if not assignments:
        raise ValueError("Provide a schedule state to change.")
    values.append(schedule_id)
    with connect(database_path) as connection:
        cursor = connection.execute(
            f"UPDATE scheduled_reports SET {', '.join(assignments)} WHERE id=?",
            tuple(values),
        )
        if cursor.rowcount == 0:
            raise ValueError("Scheduled report not found.")


def claim_schedule_run(
    schedule_id: int,
    run_key: str,
    database_path: Optional[Path] = None,
) -> bool:
    with connect(database_path) as connection:
        try:
            connection.execute(
                "INSERT INTO schedule_runs(schedule_id,run_key,created_at) VALUES(?,?,?)",
                (schedule_id, run_key, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
        except sqlite3.IntegrityError:
            return False
        connection.execute(
            "UPDATE scheduled_reports SET last_run_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), schedule_id),
        )
        return True
