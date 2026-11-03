"""Explicit SMTP delivery for generated reports."""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from config import ConfigurationError, Settings

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailDeliveryError(RuntimeError):
    """Raised when SMTP delivery fails."""


def validate_email_address(address: str) -> str:
    """Validate and normalize a single email address."""
    normalized = address.strip()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError(f"Invalid email address: {address}")
    return normalized


def send_reports(
    recipients: list[str], attachments: list[Path], settings: Settings
) -> None:
    """Send reports as attachments using explicitly configured SMTP settings."""
    if not recipients:
        raise ValueError("Provide at least one recipient email address.")
    validated_recipients = [validate_email_address(item) for item in recipients]
    if not attachments:
        raise FileNotFoundError(
            "No archived reports were found. Generate a report before emailing."
        )
    for attachment in attachments:
        if not attachment.is_file():
            raise FileNotFoundError(f"Email attachment not found: {attachment}")

    required = {
        "SMTP_HOST": settings.smtp_host,
        "SMTP_USERNAME": settings.smtp_username,
        "SMTP_PASSWORD": settings.smtp_password,
        "SMTP_SENDER": settings.smtp_sender,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ConfigurationError(
            "Email is not configured. Set " + ", ".join(missing) + " in your .env file."
        )
    sender = validate_email_address(settings.smtp_sender or "")
    message = EmailMessage()
    message["Subject"] = "Automated Transaction Report"
    message["From"] = sender
    message["To"] = ", ".join(validated_recipients)
    message.set_content(
        "Please find the requested automated transaction report(s) attached."
    )
    for attachment in attachments:
        content_type = (
            "application/pdf"
            if attachment.suffix.lower() == ".pdf"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        main_type, sub_type = content_type.split("/", 1)
        message.add_attachment(
            attachment.read_bytes(),
            maintype=main_type,
            subtype=sub_type,
            filename=attachment.name,
        )

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
                context=ssl.create_default_context(),
            ) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
            ) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.exception("Could not deliver report email.")
        raise EmailDeliveryError(f"Email delivery failed: {exc}") from exc
    logger.info("Delivered %d report(s) to %s.", len(attachments), ", ".join(validated_recipients))
