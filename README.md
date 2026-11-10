# Automated Report Generation & Delivery System

A local-first Streamlit application for importing datasets, cleaning and analyzing data, generating professional PDF/Excel/CSV reports, archiving report history, scheduling recurring generation, and optionally sending PDF/Excel attachments by SMTP.

## Features

- Streamlit dashboard backed by real SQLite report, schedule and email-delivery records.
- Import CSV and Excel data; reject unsupported or oversized input, remove duplicate/blank rows and fill missing values.
- Filter data by dates and numerical comparisons; select report columns.
- Interactive Plotly analytics and summary statistics.
- Generate PDF reports with tables, summary statistics and a Matplotlib visualization; Excel reports with data/summary sheets and charts; and CSV reports with summary metadata and rows.
- Search/download report archive; destructive archive deletion requires an explicit confirmation.
- Persistent daily, weekly and monthly schedules with a separate APScheduler worker.
- SMTP delivery with configurable credentials, bounded retries and success/failure history.
- Rotating application logs and isolated pytest coverage.

## Technologies

Python 3.12+, Streamlit, Pandas, SQLite, Plotly, Matplotlib, ReportLab, OpenPyXL, APScheduler, SMTP, python-dotenv and Pytest.

## Screenshots

No screenshots are included yet. Launch the app, open the desired page and capture it with the operating system screenshot shortcut. Store approved screenshots in `screenshots/`.

## Folder Structure

```text
automated_report_generation_delivery/
├── app.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── data/
│   └── sample_sales.csv
├── reporting/
│   ├── archive.py
│   ├── config.py
│   ├── data_service.py
│   ├── database.py
│   ├── delivery.py
│   ├── logging_config.py
│   ├── report_generator.py
│   ├── scheduler_worker.py
│   └── scheduling.py
├── reports/
├── logs/
├── screenshots/
└── tests/
```

The local database, `.env`, logs and generated report files are excluded from Git.

## Installation (Windows / VS Code)

Open the project folder in VS Code, choose **Terminal → New Terminal**, and run:

```powershell
cd "C:\path\to\Python Project\automated_report_generation_delivery"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

In Command Prompt, activate using `.venv\Scripts\activate.bat`. If PowerShell blocks activation, use `.venv\Scripts\python.exe` instead of `python`.

## Launch the GUI

```powershell
streamlit run app.py
```

## Launch the Scheduler

Open a second terminal in the project folder, activate the same environment, then run:

```powershell
python -m reporting.scheduler_worker
```

The worker reloads schedule settings from SQLite every 30 seconds. Keep it running for scheduled reports to execute. The schedule uses the worker computer's local timezone.

## Usage

1. In **Data Collection**, upload a CSV/Excel file or load the included sample dataset.
2. In **Data Analysis**, filter by date and number, inspect summary statistics and visualize grouped values.
3. In **Report Builder**, select data/columns/filters, set the title, chart and format, and generate or save a reusable configuration.
   The optional report destination accepts only a relative subfolder inside the configured archive directory.
4. In **Report Archive**, search and download generated reports. Confirm before deleting an archived report.
5. In **Scheduling**, choose a saved report configuration and schedule it.
6. To email a PDF or Excel report, configure SMTP and use **Email Delivery**.

## SMTP Configuration

Set SMTP host, port, sender and (if required) username/password in `.env`. Credentials are never stored in source code or SQLite. For TLS-enabled SMTP, configure `SMTP_STARTTLS=true`; for implicit TLS, set `SMTP_USE_SSL=true` and use the provider's SSL port. Use an app-specific password if your provider requires one, and do not commit `.env`.

For local testing without a real mail server, automated tests use a mocked SMTP client. A real email delivery requires user-provided SMTP settings and was not performed as part of tests.

## Testing

```powershell
python -m pytest -q
```

Tests use temporary SQLite databases, in-memory datasets and mocked SMTP; they do not send email or require an external service.

## Known Limitations

- The scheduler is a separate local process and runs only while that process and computer remain active.
- PDF tables are limited to the first 500 dataset rows to keep files manageable; full data remains available in Excel/CSV.
- SMTP credentials and deliverability depend on the user's provider configuration and network policy.
- Data and report files are local; configure backups appropriate to your needs.
- If PyArrow cannot load on a machine, the interface shows a read-only text preview instead of an interactive table.
