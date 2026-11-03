# Automated Report Generation & Delivery System

A modular Python CLI application that imports transaction data into SQLite,
cleans and analyzes it with pandas, creates PDF and Excel reports with charts,
archives every generated report, and can deliver reports by SMTP or generate
them on a daily, weekly, or monthly schedule.

## Objectives and features

- Collect transaction data from SQLite or import it from CSV.
- Normalize dates, amounts, categories, and descriptions; skip invalid records
  and prevent exact duplicate imports.
- Calculate totals, averages, minimums, maximums, monthly summaries, and
  category summaries, with inclusive date-range filtering.
- Generate paginated PDF reports and formatted Excel workbooks with summary
  tables, detailed data, and charts.
- Preserve timestamped reports in both `reports/` and `archive/`.
- Explicitly send archived report attachments through configurable SMTP.
- Run a foreground APScheduler process for daily, weekly, or monthly reports.
- Record activity in `logs/app.log`.

## Technologies

Python 3.12+, SQLite, pandas, matplotlib, ReportLab, OpenPyXL, APScheduler,
python-dotenv, argparse, logging, and pytest. Email uses Python's standard
`smtplib`; no external API or paid service is required.

## Project structure

```text
automated_report_system/
├── main.py
├── config.py
├── database.py
├── data_collector.py
├── data_processor.py
├── pdf_generator.py
├── excel_generator.py
├── email_sender.py
├── scheduler.py
├── archive_manager.py
├── data/
│   └── sample_data.csv
├── reports/
├── archive/
├── logs/
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

Open a terminal in this directory. Python 3.12 or later is recommended.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS or Linux, activate the environment with
`source .venv/bin/activate`.

## Initialize the database

```powershell
python main.py init
```

This creates `data/reports.db`, creates the transaction table and indexes, and
imports the demonstration CSV. The import is safe to repeat: existing records
are not duplicated. Sample data covers several months and business categories.

## Import CSV data

CSV files must contain `transaction_date`, `category`, and `amount` columns;
`description` is optional. Dates should be parseable by pandas. Invalid dates
and non-positive or invalid amounts are skipped; a blank category is recorded
as `Uncategorized`.

```powershell
python main.py import --file data\sample_data.csv
```

## Generate reports

```powershell
python main.py generate --format pdf
python main.py generate --format excel
python main.py generate --format both
python main.py generate --format both --start-date 2025-01-01 --end-date 2025-03-31
```

Each report is written under `reports/` and copied to `archive/` with a
microsecond timestamp. PDF reports include executive statistics, monthly and
category tables, a chart, transaction details, and page numbers. Excel
workbooks include a summary sheet, monthly and category summary sheets, and a
detailed transaction sheet.

## Email configuration and delivery

Copy `.env.example` to `.env`, then set the SMTP host, port, username, password,
sender address, and TLS options for your mail provider. Use an app-specific
password when required by the provider. `.env` is ignored by git.

```powershell
Copy-Item .env.example .env
# Edit .env with your SMTP provider's settings.
python main.py email --to recipient@example.com
python main.py email --to first@example.com second@example.com --format pdf
```

Email is only attempted by this explicit command. It attaches the newest
archived report(s) matching the selected format. Without SMTP configuration,
the command exits with a helpful message and does not attempt delivery. SMTP
authentication, connection, and delivery errors are logged and surfaced.

## Scheduling

The scheduler runs in the foreground and uses the machine's local time. Stop it
with Ctrl+C. Daily runs occur every day; weekly runs default to Monday; monthly
runs default to day 1 (configurable from day 1 through 28). Each scheduled run
generates both formats and uses a non-overlapping, coalescing scheduler job.
Email is opt-in: pass `--email-to` to deliver the generated attachments on each
scheduled run; SMTP configuration is required. Without that option, scheduled
jobs only generate and archive reports.

```powershell
python main.py schedule --frequency daily --time 09:00
python main.py schedule --frequency weekly --time 08:30 --day-of-week fri
python main.py schedule --frequency monthly --time 07:15 --day-of-month 1
python main.py schedule --frequency daily --time 09:00 --email-to recipient@example.com
```

Keep the process and computer running for scheduled jobs to execute. Email is
never sent by the scheduler unless one or more recipients are explicitly
provided with `--email-to`.

## Archive history and logs

```powershell
python main.py history
```

The command lists archived PDF and Excel reports newest first. Application
activity is also written to `logs/app.log`.

## Testing

Install the requirements and run:

```powershell
python -m pytest -q
```

Tests use temporary SQLite databases and report folders. SMTP behavior is
mocked; the test suite never sends real email or accesses an external service.

## Sample CLI output

Generated filenames include the actual generation timestamp; paths and file
sizes vary by machine.

```text
python main.py init
INFO | Database initialized. Sample data: 12 inserted, 0 duplicates, 0 invalid.

python main.py generate --format both
INFO | Generated pdf report: ...\reports\transaction_report_....pdf
INFO | Generated excel report: ...\reports\transaction_report_....xlsx

python main.py history
INFO | transaction_report_....xlsx | xlsx | ... bytes
INFO | transaction_report_....pdf | pdf | ... bytes
```

## Screenshots

No screenshots are included yet. After generating reports, open the PDF and
workbook in your preferred viewer and add screenshots here if desired.

## Configuration reference

Optional path overrides are `REPORT_DATABASE_PATH`, `REPORTS_DIR`, `ARCHIVE_DIR`,
and `LOGS_DIR`. Relative paths are resolved from this project directory. SMTP
settings are `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_SENDER`, `SMTP_USE_SSL`, `SMTP_USE_TLS`, and `SMTP_TIMEOUT`.

## Future enhancements

- Add configurable business-specific schemas and richer import mappings.
- Support more delivery channels and per-report email templates.
- Add retention policies, report metadata, and archive integrity checks.
- Add scheduler persistence and timezone selection.
