from archive_manager import archive_report, list_archived_reports


def test_archive_keeps_history_without_overwriting(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"first")
    archive = tmp_path / "archive"

    first = archive_report(source, archive)
    source.write_bytes(b"second")
    second = archive_report(source, archive)

    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert second.name == "report_1.pdf"
    assert len(list_archived_reports(archive)) == 2
