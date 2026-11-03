"""Command-line entry point for the automated report system."""

from __future__ import annotations

import argparse
import logging
import sys

from archive_manager import latest_reports, list_archived_reports
from config import ConfigurationError, Settings, configure_logging
from data_collector import create_sample_data, import_csv, load_transactions
from data_processor import DataProcessingError, validate_date_range
from database import Database
from email_sender import EmailDeliveryError, send_reports
from excel_generator import generate_excel_report
from pdf_generator import generate_pdf_report
from scheduler import start_scheduler

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect, analyze, generate, and deliver transaction reports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize the database and sample data.")

    import_parser = subparsers.add_parser("import", help="Import transaction data from CSV.")
    import_parser.add_argument("--file", required=True, help="Path to a transaction CSV.")

    generate_parser = subparsers.add_parser("generate", help="Generate report files.")
    generate_parser.add_argument(
        "--format", choices=("pdf", "excel", "both"), default="both"
    )
    generate_parser.add_argument("--start-date", help="Inclusive start date (YYYY-MM-DD).")
    generate_parser.add_argument("--end-date", help="Inclusive end date (YYYY-MM-DD).")

    email_parser = subparsers.add_parser("email", help="Email archived reports.")
    email_parser.add_argument(
        "--to", required=True, nargs="+", help="Recipient email address(es)."
    )
    email_parser.add_argument(
        "--format", choices=("pdf", "excel", "both"), default="both"
    )

    schedule_parser = subparsers.add_parser("schedule", help="Start scheduled report generation.")
    schedule_parser.add_argument(
        "--frequency", choices=("daily", "weekly", "monthly"), required=True
    )
    schedule_parser.add_argument(
        "--time", default="09:00", help="24-hour local time (HH:MM); default: 09:00."
    )
    schedule_parser.add_argument(
        "--day-of-week", default="mon", help="Weekly day: mon through sun; default: mon."
    )
    schedule_parser.add_argument(
        "--day-of-month",
        type=int,
        default=1,
        help="Monthly day, 1-28; default: 1.",
    )
    schedule_parser.add_argument(
        "--email-to",
        nargs="+",
        help="Optional recipient(s) for each scheduled report; requires SMTP configuration.",
    )

    subparsers.add_parser("history", help="List previously generated archived reports.")
    return parser


def run_command(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database_path)
    if args.command == "init":
        settings.ensure_directories()
        database.initialize()
        sample_path = create_sample_data(settings.base_dir / "data" / "sample_data.csv")
        inserted, duplicates, invalid = import_csv(sample_path, database)
        logger.info(
            "Database initialized. Sample data: %d inserted, %d duplicates, %d invalid.",
            inserted,
            duplicates,
            invalid,
        )
    elif args.command == "import":
        database.initialize()
        inserted, duplicates, invalid = import_csv(args.file, database)
        logger.info(
            "Import complete: %d inserted, %d duplicates, %d invalid.",
            inserted,
            duplicates,
            invalid,
        )
    elif args.command == "generate":
        database.initialize()
        start, end = validate_date_range(args.start_date, args.end_date)
        transactions = load_transactions(database, start, end)
        formats = ("pdf", "excel") if args.format == "both" else (args.format,)
        for report_format in formats:
            if report_format == "pdf":
                path = generate_pdf_report(
                    transactions, settings.reports_dir, settings.archive_dir
                )
            else:
                path = generate_excel_report(
                    transactions, settings.reports_dir, settings.archive_dir
                )
            logger.info("Generated %s report: %s", report_format, path)
    elif args.command == "email":
        attachments = latest_reports(settings.archive_dir, args.format)
        send_reports(args.to, attachments, settings)
        logger.info("Email delivery completed successfully.")
    elif args.command == "schedule":
        database.initialize()
        start_scheduler(
            args.frequency,
            args.time,
            settings,
            args.day_of_week,
            args.day_of_month,
            args.email_to,
        )
    elif args.command == "history":
        reports = list_archived_reports(settings.archive_dir)
        if not reports:
            logger.info("No archived reports found.")
        else:
            for path in reports:
                logger.info("%s | %s | %s bytes", path.name, path.suffix[1:], path.stat().st_size)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        configure_logging(settings)
        return run_command(args, settings)
    except (
        ConfigurationError,
        DataProcessingError,
        EmailDeliveryError,
        OSError,
        ValueError,
    ) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1
    except Exception:
        logging.getLogger(__name__).exception("Unexpected application error.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
