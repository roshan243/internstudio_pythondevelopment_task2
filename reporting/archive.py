"""Historical report archive operations with safe file deletion."""

from pathlib import Path
from typing import Optional

from reporting.config import OUTPUT_DIR
from reporting.database import connect, fetch_frame


def list_reports(
    database_path: Optional[Path] = None,
    search: str = "",
    status: Optional[str] = None,
    output_format: Optional[str] = None,
):
    clauses = []
    parameters = []
    if search.strip():
        clauses.append("(r.title LIKE ? OR r.description LIKE ?)")
        parameters.extend([f"%{search.strip()}%", f"%{search.strip()}%"])
    if status:
        clauses.append("r.status=?")
        parameters.append(status)
    if output_format:
        clauses.append("r.format=?")
        parameters.append(output_format)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return fetch_frame(
        f"""SELECT r.*, d.name AS dataset_name FROM reports r
        LEFT JOIN datasets d ON d.id=r.dataset_id {where} ORDER BY r.id DESC""",
        tuple(parameters),
        database_path,
    )


def get_report(report_id: int, database_path: Optional[Path] = None):
    with connect(database_path) as connection:
        row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    return row


def delete_archived_report(
    report_id: int,
    database_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> None:
    root = Path(output_dir or OUTPUT_DIR).resolve()
    with connect(database_path) as connection:
        report = connection.execute(
            "SELECT file_path FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if report is None:
            raise ValueError("Archived report not found.")
        stored_path = report["file_path"]
        if stored_path:
            path = Path(stored_path).resolve()
            if root not in path.parents:
                raise ValueError("Refusing to delete a file outside the report archive.")
            if path.exists():
                path.unlink()
        connection.execute("DELETE FROM reports WHERE id=?", (report_id,))
