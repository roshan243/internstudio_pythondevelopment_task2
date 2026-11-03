"""Unique report filenames and historical archive operations."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from config import Settings

logger = logging.getLogger(__name__)
SUPPORTED_FORMATS = {".pdf", ".xlsx"}


def create_report_path(
    reports_dir: Path, report_format: str, generated_at: datetime | None = None
) -> Path:
    """Return a timestamped report path that will not overwrite an existing file."""
    extension = report_format.lower().lstrip(".")
    if extension == "excel":
        extension = "xlsx"
    if extension not in {"pdf", "xlsx"}:
        raise ValueError(f"Unsupported report format: {report_format}")
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = (generated_at or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    candidate = reports_dir / f"transaction_report_{stamp}.{extension}"
    suffix = 1
    while candidate.exists():
        candidate = reports_dir / f"transaction_report_{stamp}_{suffix}.{extension}"
        suffix += 1
    return candidate


def archive_report(report_path: str | Path, archive_dir: Path) -> Path:
    """Copy a generated report into the archive without overwriting history."""
    source = Path(report_path)
    if not source.is_file():
        raise FileNotFoundError(f"Generated report not found: {source}")
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported report type: {source.suffix}")
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / source.name
    if destination.exists():
        stem, suffix = source.stem, source.suffix
        sequence = 1
        while destination.exists():
            destination = archive_dir / f"{stem}_{sequence}{suffix}"
            sequence += 1
    shutil.copy2(source, destination)
    logger.info("Archived report at %s.", destination)
    return destination


def list_archived_reports(archive_dir: Path) -> list[Path]:
    """Return archived PDFs and Excel workbooks newest first."""
    if not archive_dir.exists():
        return []
    return sorted(
        (
            path
            for path in archive_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )


def latest_reports(archive_dir: Path, report_format: str = "both") -> list[Path]:
    """Find the newest archived report of each requested format."""
    allowed = {"pdf", "excel"}
    if report_format not in allowed | {"both"}:
        raise ValueError(f"Unsupported report format: {report_format}")
    wanted = {"pdf", "xlsx"} if report_format == "both" else {
        "xlsx" if report_format == "excel" else report_format
    }
    found: dict[str, Path] = {}
    for path in list_archived_reports(archive_dir):
        extension = path.suffix.lower().lstrip(".")
        if extension in wanted and extension not in found:
            found[extension] = path
    return [found[key] for key in ("pdf", "xlsx") if key in found]
