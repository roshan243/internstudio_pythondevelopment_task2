"""Streamlit GUI for report generation, archiving, scheduling and email delivery."""

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from reporting import config as app_config
from reporting.archive import delete_archived_report, get_report, list_reports
from reporting.data_service import (
    clean_dataframe,
    filter_dataframe,
    list_datasets,
    load_dataset,
    read_uploaded_dataset,
    save_dataframe,
)
from reporting.database import connect, fetch_frame, initialize_database
from reporting.delivery import send_report_email
from reporting.logging_config import LOGGER
from reporting.report_generator import generate_report, validate_report_config
from reporting.scheduling import create_schedule, list_schedules, set_schedule_state


st.set_page_config(
    page_title="Automated Report Generation & Delivery",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
initialize_database()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.7rem; max-width: 1500px;}
    [data-testid="stMetric"] {
      background: #fff; padding: 18px 20px; border-radius: 12px;
      border: 1px solid #e6eaf2; box-shadow: 0 2px 8px rgba(20,35,65,.04);
    }
    h1, h2, h3 {letter-spacing: -.025em;}
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = [
    "Dashboard",
    "Data Collection",
    "Data Analysis",
    "Report Builder",
    "Report Archive",
    "Scheduling",
    "Email Delivery",
    "Monitoring",
    "Settings",
]


def frame(query: str, parameters: tuple = ()) -> pd.DataFrame:
    return fetch_frame(query, parameters, app_config.DATABASE_PATH)


def title_block(title: str, subtitle: str) -> None:
    st.title(title)
    st.caption(subtitle)


def show_table(data: pd.DataFrame, height: int = 400) -> None:
    if data.empty:
        st.info("No records to display.")
    else:
        try:
            __import__("pyarrow")
        except ImportError:
            st.warning("PyArrow is unavailable; showing a read-only preview instead of an interactive table.")
            st.code(data.head(100).to_string(index=False, max_cols=20), language=None)
        else:
            st.dataframe(data, use_container_width=True, hide_index=True, height=height)


def _dataset_options() -> pd.DataFrame:
    return list_datasets(app_config.DATABASE_PATH)


def _dataset_select(label: str = "Dataset") -> tuple[int, str]:
    datasets = _dataset_options()
    if datasets.empty:
        st.info("Upload a dataset or load the sample dataset to continue.")
        st.stop()
    options = {
        f"{row['name']} — {row['row_count']} rows (#{row['id']})": int(row["id"])
        for _, row in datasets.iterrows()
    }
    selected_label = st.selectbox(label, list(options))
    return options[selected_label], selected_label


def dashboard() -> None:
    title_block(
        "Automated Report Generation & Delivery",
        "Report generation, delivery, and schedule statistics from your local database.",
    )
    if st.button("↻ Refresh dashboard"):
        st.rerun()
    stats = frame(
        """SELECT
        (SELECT COUNT(*) FROM reports) AS total,
        (SELECT COUNT(*) FROM reports WHERE status='success') AS successful,
        (SELECT COUNT(*) FROM reports WHERE status='failed') AS failed,
        (SELECT COUNT(*) FROM scheduled_reports WHERE enabled=1 AND paused=0) AS scheduled,
        (SELECT COUNT(*) FROM email_deliveries WHERE status='success') AS delivered"""
    ).iloc[0]
    cols = st.columns(5)
    for column, label, value in zip(
        cols,
        ["Reports generated", "Successful", "Failed", "Active schedules", "Emails delivered"],
        [stats.total, stats.successful, stats.failed, stats.scheduled, stats.delivered],
    ):
        column.metric(label, f"{int(value):,}")
    left, right = st.columns(2)
    with left:
        counts = frame(
            """SELECT substr(created_at,1,10) AS day, status, COUNT(*) AS reports
            FROM reports GROUP BY day,status ORDER BY day"""
        )
        st.subheader("Report generation activity")
        if counts.empty:
            st.info("Generate a report to see activity.")
        else:
            st.plotly_chart(px.bar(counts, x="day", y="reports", color="status", barmode="group"), use_container_width=True)
    with right:
        outcomes = frame("SELECT status, COUNT(*) AS deliveries FROM email_deliveries GROUP BY status")
        st.subheader("Email delivery outcomes")
        if outcomes.empty:
            st.info("Email delivery history will appear here.")
        else:
            st.plotly_chart(px.pie(outcomes, names="status", values="deliveries"), use_container_width=True)
    st.subheader("Recent report activity")
    show_table(
        frame(
            """SELECT id,title,format,status,row_count,duration_seconds,created_at,error
            FROM reports ORDER BY id DESC LIMIT 20"""
        )
    )


def data_collection() -> None:
    title_block("Data Collection", "Upload and clean CSV/Excel datasets, or load the included sample.")
    left, right = st.columns(2)
    with left:
        st.subheader("Upload dataset")
        upload = st.file_uploader("CSV or Excel (.xlsx)", type=["csv", "xlsx", "xlsm"])
        name = st.text_input("Dataset name", value=Path(upload.name).stem if upload else "")
        if st.button("Validate, clean and save", type="primary", disabled=upload is None):
            try:
                data = read_uploaded_dataset(upload.name, upload.getvalue())
                dataset_id = save_dataframe(
                    data, name, upload.name, app_config.DATABASE_PATH
                )
                st.success(f"Saved dataset #{dataset_id}: {len(data):,} cleaned rows.")
                st.rerun()
            except (ValueError, OSError, pd.errors.ParserError, ImportError) as error:
                LOGGER.warning("Dataset upload rejected: %s", error)
                st.error(f"Could not load dataset: {error}")
    with right:
        st.subheader("Sample dataset")
        st.write("The included sales sample contains real, deterministic example rows for demonstrations.")
        if st.button("Load sample sales data"):
            path = Path(__file__).resolve().parent / "data" / "sample_sales.csv"
            try:
                data = read_uploaded_dataset(path.name, path.read_bytes())
                dataset_id = save_dataframe(
                    data, "Sample Sales", path.name, app_config.DATABASE_PATH
                )
                st.success(f"Loaded sample dataset #{dataset_id}.")
                st.rerun()
            except (ValueError, OSError) as error:
                st.error(f"Could not load sample: {error}")
    datasets = _dataset_options()
    st.subheader("Stored datasets")
    show_table(datasets)
    if not datasets.empty:
        dataset_id, _ = _dataset_select("Preview dataset")
        try:
            data = load_dataset(dataset_id, app_config.DATABASE_PATH)
            cleaned, summary = clean_dataframe(data)
            c1, c2, c3 = st.columns(3)
            c1.metric("Rows after cleaning", f"{summary['clean_rows']:,}")
            c2.metric("Missing values filled", f"{summary['missing_values_filled']:,}")
            c3.metric("Duplicate rows removed", f"{summary['duplicates_removed']:,}")
            show_table(cleaned.head(500))
        except (ValueError, sqlite3.Error) as error:
            st.error(f"Dataset preview failed: {error}")


def _filtered_dataset(dataset_id: int) -> tuple[pd.DataFrame, list[str]]:
    data = load_dataset(dataset_id, app_config.DATABASE_PATH)
    columns = list(data.columns)
    with st.expander("Date and numerical filters", expanded=False):
        date_columns = ["No date filter"] + columns
        date_choice = st.selectbox("Date column", date_columns)
        date_column = None if date_choice == "No date filter" else date_choice
        start = st.date_input("Start date (optional)", value=None)
        end = st.date_input("End date (optional)", value=None)
        numeric = [column for column in columns if pd.api.types.is_numeric_dtype(data[column])]
        numeric_choice = st.selectbox("Numeric filter column", ["No numeric filter"] + numeric)
        numeric_column = None if numeric_choice == "No numeric filter" else numeric_choice
        operator = st.selectbox("Comparison", [">", ">=", "=", "<=", "<"], disabled=numeric_column is None)
        threshold = st.number_input("Threshold", value=0.0, disabled=numeric_column is None)
    if start and end and start > end:
        st.error("Start date must not be after end date.")
        return data.iloc[0:0], columns
    try:
        filtered = filter_dataframe(
            data,
            date_column=date_column,
            start_date=start,
            end_date=end,
            numeric_column=numeric_column,
            operator=operator if numeric_column else None,
            threshold=threshold if numeric_column else None,
        )
    except ValueError as error:
        st.error(str(error))
        filtered = data.iloc[0:0]
    return filtered, columns


def data_analysis() -> None:
    title_block("Data Analysis", "Apply date/numeric filters and visualize actual dataset values.")
    dataset_id, _ = _dataset_select()
    data, columns = _filtered_dataset(dataset_id)
    if data.empty:
        st.info("No rows remain after filtering.")
        return
    numeric = [column for column in columns if pd.api.types.is_numeric_dtype(data[column])]
    categorical = [column for column in columns if column not in numeric]
    st.metric("Filtered rows", f"{len(data):,}")
    if numeric:
        st.subheader("Numerical summaries")
        show_table(data[numeric].describe().transpose().reset_index(names="column"))
    if categorical and numeric:
        c1, c2, c3 = st.columns(3)
        category = c1.selectbox("Category", categorical)
        value = c2.selectbox("Value", numeric)
        chart_type = c3.selectbox("Chart", ["Bar", "Line", "Pie"])
        grouped = data.groupby(category, dropna=False)[value].sum().reset_index()
        if chart_type == "Line":
            chart = px.line(grouped, x=category, y=value, markers=True)
        elif chart_type == "Pie":
            chart = px.pie(grouped, names=category, values=value)
        else:
            chart = px.bar(grouped, x=category, y=value)
        st.plotly_chart(chart, use_container_width=True)
    elif not numeric:
        st.info("Add a numeric column to create value comparison charts.")
    st.subheader("Filtered data")
    show_table(data)


def _config_from_form(dataset_id: int, data: pd.DataFrame, title: str, description: str, columns: list[str], output_format: str, chart_type: str, date_column: str, start, end, numeric_column: str, operator: str, threshold: float) -> dict:
    return validate_report_config(
        {
            "title": title,
            "description": description,
            "dataset_id": dataset_id,
            "columns": columns,
            "format": output_format,
            "chart_type": chart_type,
            "date_column": date_column if date_column != "No date filter" else None,
            "start_date": start,
            "end_date": end,
            "numeric_column": numeric_column if numeric_column != "No numeric filter" else None,
            "operator": operator if numeric_column != "No numeric filter" else None,
            "threshold": threshold if numeric_column != "No numeric filter" else None,
        }
    )


def report_builder() -> None:
    title_block("Report Builder", "Configure a dataset, filters, selected columns and output format.")
    dataset_id, _ = _dataset_select()
    data = load_dataset(dataset_id, app_config.DATABASE_PATH)
    columns = list(data.columns)
    categorical_dates = ["No date filter"] + columns
    numeric_columns = ["No numeric filter"] + [
        column for column in columns if pd.api.types.is_numeric_dtype(data[column])
    ]
    with st.form("report_builder_form"):
        report_title = st.text_input("Report title", value="Dataset Summary")
        description = st.text_area("Description", value="")
        destination = st.text_input(
            "Report destination folder (inside reports/)",
            value="",
            help="Optional relative folder, for example monthly/2026. Parent-directory paths are not allowed.",
        )
        selected_columns = st.multiselect("Columns", columns, default=columns)
        output_format = st.selectbox("Output format", ["pdf", "xlsx", "csv"])
        chart_type = st.selectbox("Chart type", ["bar", "line", "pie"])
        date_column = st.selectbox("Optional date column", categorical_dates)
        c1, c2 = st.columns(2)
        start = c1.date_input("From date (optional)", value=None)
        end = c2.date_input("Through date (optional)", value=None)
        numeric_column = st.selectbox("Numeric filter column", numeric_columns)
        c3, c4 = st.columns(2)
        operator = c3.selectbox("Numeric comparison", [">", ">=", "=", "<=", "<"], disabled=numeric_column == "No numeric filter")
        threshold = c4.number_input("Threshold", value=0.0, disabled=numeric_column == "No numeric filter")
        config_name = st.text_input("Save configuration as (optional)")
        c5, c6 = st.columns(2)
        save = c5.form_submit_button("Save configuration")
        generate = c6.form_submit_button("Generate report", type="primary")
    if start and end and start > end:
        st.error("Report start date must be on or before its end date.")
        return
    if save or generate:
        try:
            report_config = _config_from_form(
                dataset_id,
                data,
                report_title,
                description,
                selected_columns,
                output_format,
                chart_type,
                date_column,
                start,
                end,
                numeric_column,
                operator,
                threshold,
            )
            report_config["destination"] = destination.strip()
            report_config = validate_report_config(report_config)
            if save:
                if not config_name.strip():
                    st.error("Enter a name for the saved configuration.")
                    return
                now = datetime.now().astimezone().isoformat(timespec="seconds")
                with connect(app_config.DATABASE_PATH) as connection:
                    connection.execute(
                        """INSERT INTO report_configs(name,config_json,created_at,updated_at)
                        VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                        config_json=excluded.config_json,updated_at=excluded.updated_at""",
                        (config_name.strip(), json.dumps(report_config, default=str), now, now),
                    )
                st.success(f"Saved report configuration “{config_name.strip()}”.")
            if generate:
                with st.spinner("Generating report…"):
                    result = generate_report(report_config, app_config.DATABASE_PATH)
                payload = result["path"].read_bytes()
                mime = {
                    "pdf": "application/pdf",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "csv": "text/csv",
                }[result["format"]]
                st.success(f"Generated report #{result['id']} with {result['rows']:,} rows.")
                st.download_button(
                    "Download generated report",
                    payload,
                    file_name=result["path"].name,
                    mime=mime,
                    key=f"download_report_{result['id']}",
                )
        except (ValueError, OSError, KeyError, TypeError, ImportError, sqlite3.Error) as error:
            st.error(f"Could not process report: {error}")
    with st.expander("Saved configurations"):
        show_table(frame("SELECT id,name,created_at,updated_at FROM report_configs ORDER BY id DESC"))


def report_archive() -> None:
    title_block("Report Archive", "Search historical reports, download completed files, and delete with confirmation.")
    c1, c2, c3 = st.columns(3)
    search = c1.text_input("Search title/description")
    status = c2.selectbox("Status", ["All", "success", "failed", "running"])
    output_format = c3.selectbox("Format", ["All", "pdf", "xlsx", "csv"])
    reports = list_reports(
        app_config.DATABASE_PATH,
        search=search,
        status=None if status == "All" else status,
        output_format=None if output_format == "All" else output_format,
    )
    show_table(reports)
    completed = reports[reports["status"] == "success"] if not reports.empty else reports
    if completed.empty:
        return
    options = {
        f"#{int(row['id'])} {row['title']} ({row['format']})": int(row["id"])
        for _, row in completed.iterrows()
    }
    selected = st.selectbox("Select archived report", list(options))
    report_id = options[selected]
    report = get_report(report_id, app_config.DATABASE_PATH)
    if report and report["file_path"]:
        path = Path(report["file_path"])
        try:
            payload = path.read_bytes()
            mime = {
                "pdf": "application/pdf",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "csv": "text/csv",
            }.get(report["format"], "application/octet-stream")
            st.download_button("Download archived report", payload, path.name, mime=mime)
        except OSError as error:
            st.error(f"Archived file is unavailable: {error}")
    if st.button("Prepare to delete selected report", type="secondary"):
        st.session_state["confirm_delete_report"] = report_id
    if st.session_state.get("confirm_delete_report") == report_id:
        st.warning("This deletes the archived report file and its database entry. This cannot be undone.")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm delete", type="primary"):
            try:
                delete_archived_report(report_id, app_config.DATABASE_PATH)
                st.session_state.pop("confirm_delete_report", None)
                st.success("Archived report deleted.")
                st.rerun()
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(f"Delete failed: {error}")
        if cancel.button("Cancel deletion"):
            st.session_state.pop("confirm_delete_report", None)
            st.rerun()


def scheduling() -> None:
    title_block("Scheduling", "Schedules are persistent. Keep the separate report worker running to execute them.")
    st.info("Start the worker in another terminal: `python -m reporting.scheduler_worker`")
    saved = frame("SELECT id,name,config_json FROM report_configs ORDER BY name")
    if saved.empty:
        st.info("Save a report configuration in Report Builder before scheduling it.")
    else:
        config_map = {f"{row['name']} (#{row['id']})": row for _, row in saved.iterrows()}
        with st.form("schedule_form"):
            name = st.text_input("Schedule name")
            selected = st.selectbox("Report configuration", list(config_map))
            frequency = st.selectbox("Frequency", ["daily", "weekly", "monthly"])
            run_time = st.time_input("Local execution time", value=datetime.now().replace(hour=9, minute=0).time())
            weekday = st.selectbox(
                "Day of week",
                list(range(7)),
                format_func=lambda value: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][value],
                disabled=frequency != "weekly",
            )
            monthday = st.selectbox("Day of month", list(range(1, 29)), disabled=frequency != "monthly")
            submit = st.form_submit_button("Save report schedule", type="primary")
        if submit:
            row = config_map[selected]
            try:
                schedule_id = create_schedule(
                    name,
                    json.loads(row["config_json"]),
                    frequency,
                    run_time.strftime("%H:%M"),
                    weekday if frequency == "weekly" else None,
                    monthday if frequency == "monthly" else None,
                    app_config.DATABASE_PATH,
                )
                st.success(f"Created schedule #{schedule_id}.")
            except ValueError as error:
                st.error(str(error))
    schedules = list_schedules(app_config.DATABASE_PATH)
    st.subheader("Saved schedules")
    if schedules.empty:
        st.info("No scheduled reports configured.")
    for _, row in schedules.iterrows():
        with st.container(border=True):
            st.write(f"**{row['name']}** — {row['frequency']} at {row['run_time']}")
            st.caption(
                f"Enabled: {bool(row['enabled'])} · Paused: {bool(row['paused'])} · "
                f"Last run: {row['last_run_at'] or 'Never'}"
            )
            c1, c2 = st.columns(2)
            if c1.button("Disable" if row["enabled"] else "Enable", key=f"schedule_enable_{row['id']}"):
                set_schedule_state(int(row["id"]), enabled=not bool(row["enabled"]), database_path=app_config.DATABASE_PATH)
                st.rerun()
            if c2.button("Resume" if row["paused"] else "Pause", key=f"schedule_pause_{row['id']}"):
                set_schedule_state(int(row["id"]), paused=not bool(row["paused"]), database_path=app_config.DATABASE_PATH)
                st.rerun()


def email_delivery() -> None:
    title_block("Email Delivery", "Send archived PDF or Excel reports through SMTP configured in the local .env file.")
    reports = list_reports(app_config.DATABASE_PATH, status="success")
    attachable = reports[reports["format"].isin(["pdf", "xlsx"])] if not reports.empty else reports
    if attachable.empty:
        st.info("Generate a PDF or Excel report before sending email.")
    else:
        options = {
            f"#{int(row['id'])} {row['title']} ({row['format']})": int(row["id"])
            for _, row in attachable.iterrows()
        }
        with st.form("email_form"):
            selected = st.selectbox("Report attachment", list(options))
            recipient = st.text_input("Recipient email")
            subject = st.text_input("Subject", value="Your requested report")
            message = st.text_area("Message", value="Please find the report attached.")
            send = st.form_submit_button("Send report", type="primary")
        if send:
            report_id = options[selected]
            report = get_report(report_id, app_config.DATABASE_PATH)
            try:
                result = send_report_email(
                    recipient,
                    subject,
                    message,
                    Path(report["file_path"]),
                    report_id,
                    app_config.DATABASE_PATH,
                )
                if result["status"] == "success":
                    st.success(f"Email sent after {result['attempts']} attempt(s).")
                else:
                    st.error(f"Email delivery failed after {result['attempts']} attempts: {result['error']}")
            except (ValueError, OSError, sqlite3.Error) as error:
                st.error(f"Could not send email: {error}")
    st.subheader("Delivery history")
    show_table(frame("SELECT * FROM email_deliveries ORDER BY id DESC LIMIT 200"))


def monitoring() -> None:
    title_block("Monitoring", "Track report generation, scheduled executions and email outcomes.")
    a, b = st.columns(2)
    with a:
        st.subheader("Report generation status")
        show_table(
            frame(
                """SELECT id,title,status,format,row_count,duration_seconds,created_at,error
                FROM reports ORDER BY id DESC LIMIT 300"""
            )
        )
    with b:
        st.subheader("Scheduled execution history")
        show_table(
            frame(
                """SELECT e.id,e.schedule_id,s.name AS schedule,e.status,e.duration_seconds,e.details,e.created_at
                FROM execution_logs e LEFT JOIN scheduled_reports s ON s.id=e.schedule_id
                ORDER BY e.id DESC LIMIT 300"""
            )
        )
    st.subheader("Email delivery status")
    show_table(frame("SELECT * FROM email_deliveries ORDER BY id DESC LIMIT 300"))


def settings() -> None:
    title_block("Settings", "Inspect local configuration without exposing SMTP secrets.")
    st.write(f"Database path: `{app_config.DATABASE_PATH}`")
    st.write(f"Report output directory: `{app_config.OUTPUT_DIR}`")
    st.write(f"SMTP configured: **{'Yes' if app_config.SMTP_HOST and app_config.SMTP_FROM else 'No'}**")
    st.caption("Credentials are read from `.env`; do not commit that file. See `.env.example`.")
    if st.button("Initialize/verify database"):
        initialize_database(app_config.DATABASE_PATH)
        st.success("Database schema is ready.")


def main() -> None:
    with st.sidebar:
        st.markdown("## 📊 Report Studio")
        st.caption("Generate · Schedule · Deliver")
        selected = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.divider()
        st.caption("Streamlit · SQLite · Local-first")
    routes = {
        "Dashboard": dashboard,
        "Data Collection": data_collection,
        "Data Analysis": data_analysis,
        "Report Builder": report_builder,
        "Report Archive": report_archive,
        "Scheduling": scheduling,
        "Email Delivery": email_delivery,
        "Monitoring": monitoring,
        "Settings": settings,
    }
    try:
        routes[selected]()
    except (sqlite3.Error, ValueError, OSError, ImportError) as error:
        LOGGER.exception("Application page failed: %s", error)
        st.error(f"This page could not be loaded: {error}")


if __name__ == "__main__":
    main()
