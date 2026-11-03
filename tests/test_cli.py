import pytest

from config import ConfigurationError, Settings
from main import build_parser, run_command


def test_cli_help_and_subcommands(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0
    assert "generate" in capsys.readouterr().out


def test_cli_init_import_generate_history(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        database_path=tmp_path / "data" / "test.db",
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "archive",
        logs_dir=tmp_path / "logs",
    )
    parser = build_parser()

    assert run_command(parser.parse_args(["init"]), settings) == 0
    assert run_command(
        parser.parse_args(["generate", "--format", "both"]), settings
    ) == 0
    assert run_command(parser.parse_args(["history"]), settings) == 0
    assert len(list((tmp_path / "archive").iterdir())) == 2


def test_cli_import_and_email_missing_configuration(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        database_path=tmp_path / "data" / "test.db",
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "archive",
        logs_dir=tmp_path / "logs",
    )
    parser = build_parser()
    sample = tmp_path / "input.csv"
    sample.write_text(
        "transaction_date,category,amount,description\n2025-01-01,Sales,12,Order\n",
        encoding="utf-8",
    )
    assert run_command(parser.parse_args(["import", "--file", str(sample)]), settings) == 0
    assert run_command(parser.parse_args(["generate", "--format", "pdf"]), settings) == 0
    with pytest.raises(ConfigurationError, match="Email is not configured"):
        run_command(
            parser.parse_args(["email", "--to", "user@example.com"]), settings
        )
