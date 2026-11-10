"""SMTP email delivery with configuration validation, retries and audit records."""

from email.message import EmailMessage
import re
import smtplib
import ssl
import time
from pathlib import Path
from typing import Optional

from reporting import config
from reporting.database import connect
from reporting.logging_config import LOGGER


_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def validate_email(value: str) -> str:
    recipient = (value or "").strip()
    if len(recipient) > 254 or not _EMAIL_RE.fullmatch(recipient):
        raise ValueError("Enter a valid recipient email address.")
    return recipient


def _record_delivery(
    report_id: Optional[int],
    recipient: str,
    subject: str,
    status: str,
    attempts: int,
    error: str = "",
    database_path: Optional[Path] = None,
) -> None:
    from datetime import datetime, timezone

    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO email_deliveries(report_id,recipient,subject,status,attempts,sent_at,error)
            VALUES(?,?,?,?,?,?,?)""",
            (
                report_id,
                recipient,
                subject[:998],
                status,
                attempts,
                datetime.now(timezone.utc).isoformat(timespec="seconds") if status == "success" else None,
                error[:2000],
            ),
        )


def send_report_email(
    recipient: str,
    subject: str,
    message: str,
    attachment_path: Path,
    report_id: Optional[int] = None,
    database_path: Optional[Path] = None,
) -> dict:
    """Send an attachment through configured SMTP and persist every final outcome."""
    def reject(error: ValueError) -> None:
        _record_delivery(
            report_id,
            str(recipient)[:254],
            str(subject)[:998],
            "failed",
            0,
            str(error),
            database_path,
        )
        raise error

    try:
        email = validate_email(recipient)
    except ValueError as error:
        reject(error)
    clean_subject = (subject or "").strip()
    if not clean_subject or len(clean_subject) > 998:
        reject(ValueError("Email subject is required and must be at most 998 characters."))
    attachment = Path(attachment_path).resolve()
    if not attachment.is_file():
        reject(ValueError("The report attachment does not exist."))
    if not config.SMTP_HOST or not config.SMTP_FROM:
        reject(ValueError("Configure SMTP_HOST and SMTP_FROM in the .env file first."))
    if not 1 <= config.SMTP_PORT <= 65535:
        reject(ValueError("SMTP_PORT must be between 1 and 65535."))

    email_message = EmailMessage()
    email_message["From"] = config.SMTP_FROM
    email_message["To"] = email
    email_message["Subject"] = clean_subject
    email_message.set_content(message or "Your requested report is attached.")
    subtype = "pdf" if attachment.suffix.lower() == ".pdf" else "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    maintype = "application" if attachment.suffix.lower() in {".pdf", ".xlsx"} else "text"
    if attachment.suffix.lower() not in {".pdf", ".xlsx"}:
        reject(ValueError("Email attachment must be a PDF or Excel (.xlsx) report."))
    try:
        attachment_bytes = attachment.read_bytes()
    except OSError as error:
        reject(ValueError(f"Could not read the report attachment: {error}"))
    email_message.add_attachment(
        attachment_bytes, maintype=maintype, subtype=subtype, filename=attachment.name
    )

    last_error = ""
    for attempt in range(1, config.SMTP_RETRY_COUNT + 1):
        client = None
        try:
            if config.SMTP_USE_SSL:
                client = smtplib.SMTP_SSL(
                    config.SMTP_HOST,
                    config.SMTP_PORT,
                    timeout=20,
                    context=ssl.create_default_context(),
                )
            else:
                client = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
                client.ehlo()
                if config.SMTP_STARTTLS:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
            if config.SMTP_USERNAME:
                client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            client.send_message(email_message)
            _record_delivery(
                report_id, email, clean_subject, "success", attempt, database_path=database_path
            )
            LOGGER.info("Report email delivered to %s on attempt %s", email, attempt)
            return {"status": "success", "attempts": attempt, "error": ""}
        except (smtplib.SMTPException, OSError, ssl.SSLError) as error:
            last_error = f"{type(error).__name__}: {error}"
            LOGGER.warning("Email attempt %s failed: %s", attempt, last_error)
            if attempt < config.SMTP_RETRY_COUNT:
                time.sleep(min(2 ** (attempt - 1), 4))
        finally:
            if client is not None:
                try:
                    client.quit()
                except (smtplib.SMTPException, OSError):
                    client.close()

    _record_delivery(
        report_id,
        email,
        clean_subject,
        "failed",
        config.SMTP_RETRY_COUNT,
        last_error,
        database_path,
    )
    return {"status": "failed", "attempts": config.SMTP_RETRY_COUNT, "error": last_error}
