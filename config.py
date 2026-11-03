"""Application configuration and environment-variable handling."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - requirements install python-dotenv
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent


class ConfigurationError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    database_path: Path = BASE_DIR / "data" / "reports.db"
    reports_dir: Path = BASE_DIR / "reports"
    archive_dir: Path = BASE_DIR / "archive"
    logs_dir: Path = BASE_DIR / "logs"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str | None = None
    smtp_use_ssl: bool = False
    smtp_use_tls: bool = True
    smtp_timeout: int = 20

    @classmethod
    def from_env(cls, base_dir: Path = BASE_DIR) -> "Settings":
        """Create settings from environment variables and an optional .env file."""
        base_dir = Path(base_dir).resolve()
        if load_dotenv is not None:
            load_dotenv(base_dir / ".env", override=False)

        def configured_path(variable: str, default: Path) -> Path:
            value = os.getenv(variable)
            path = Path(value).expanduser() if value else default
            return (base_dir / path).resolve() if not path.is_absolute() else path.resolve()

        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_timeout = int(os.getenv("SMTP_TIMEOUT", "20"))
        except ValueError as exc:
            raise ConfigurationError("SMTP_PORT and SMTP_TIMEOUT must be integers.") from exc
        if not 1 <= smtp_port <= 65535:
            raise ConfigurationError("SMTP_PORT must be between 1 and 65535.")
        if smtp_timeout < 1:
            raise ConfigurationError("SMTP_TIMEOUT must be a positive integer.")

        return cls(
            base_dir=base_dir,
            database_path=configured_path(
                "REPORT_DATABASE_PATH", base_dir / "data" / "reports.db"
            ),
            reports_dir=configured_path("REPORTS_DIR", base_dir / "reports"),
            archive_dir=configured_path("ARCHIVE_DIR", base_dir / "archive"),
            logs_dir=configured_path("LOGS_DIR", base_dir / "logs"),
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=smtp_port,
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            smtp_sender=os.getenv("SMTP_SENDER") or None,
            smtp_use_ssl=_as_bool(os.getenv("SMTP_USE_SSL", "false")),
            smtp_use_tls=_as_bool(os.getenv("SMTP_USE_TLS", "true")),
            smtp_timeout=smtp_timeout,
        )

    def ensure_directories(self) -> None:
        """Create application-owned directories when needed."""
        for directory in (
            self.database_path.parent,
            self.reports_dir,
            self.archive_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        "SMTP_USE_SSL and SMTP_USE_TLS must be true or false."
    )


def configure_logging(settings: Settings | None = None) -> None:
    """Configure console and file logging without adding duplicate handlers."""
    settings = settings or Settings.from_env()
    settings.ensure_directories()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    log_path = (settings.logs_dir / "app.log").resolve()
    if not any(
        isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == log_path
        for handler in root_logger.handlers
    ):
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    if not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
