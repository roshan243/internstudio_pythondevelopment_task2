"""Application settings loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "data" / "reports.db")))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(ROOT / "reports")))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = ROOT / OUTPUT_DIR
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").strip().lower() in {"1", "true", "yes"}
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes"}
SMTP_RETRY_COUNT = max(1, min(int(os.getenv("SMTP_RETRY_COUNT", "3")), 5))
