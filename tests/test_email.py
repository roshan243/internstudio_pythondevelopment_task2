import smtplib
from unittest.mock import MagicMock, patch

import pytest

from config import ConfigurationError, Settings
from email_sender import EmailDeliveryError, send_reports


def smtp_settings(**overrides):
    values = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "user",
        "smtp_password": "secret",
        "smtp_sender": "reports@example.com",
        "smtp_use_ssl": False,
        "smtp_use_tls": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_email_is_sent_with_report_attachment(tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"pdf data")
    server = MagicMock()
    server.__enter__.return_value = server

    with patch("email_sender.smtplib.SMTP", return_value=server):
        send_reports(["user@example.com"], [attachment], smtp_settings())

    server.starttls.assert_called_once()
    server.login.assert_called_once_with("user", "secret")
    server.send_message.assert_called_once()


def test_missing_smtp_configuration_is_helpful(tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"pdf data")

    with pytest.raises(ConfigurationError, match="Email is not configured"):
        send_reports(
            ["user@example.com"],
            [attachment],
            smtp_settings(smtp_host=None, smtp_password=None),
        )


def test_email_rejects_bad_recipient(tmp_path):
    with pytest.raises(ValueError, match="Invalid email"):
        send_reports(["not-an-email"], [tmp_path / "report.pdf"], smtp_settings())


def test_smtp_failure_is_reported(tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"pdf data")
    with patch(
        "email_sender.smtplib.SMTP",
        side_effect=smtplib.SMTPAuthenticationError(535, b"denied"),
    ):
        with pytest.raises(EmailDeliveryError, match="Email delivery failed"):
            send_reports(["user@example.com"], [attachment], smtp_settings())
