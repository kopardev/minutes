from minutes.config import Config
from minutes.drive_client import DriveFile, FakeDriveClient
from minutes.manifest import Manifest
from minutes.summary_schema import ActionItem, FakeSummarizer, MeetingSummary
from minutes.service import SummaryService


def test_service_dry_run(tmp_path):
    config = Config(
        source_folder_id="source",
        dest_folder_id="dest",
        manifest_path=str(tmp_path / "manifest.json"),
        summary_format="markdown",
        openai_model="gpt-5",
        transcript_mime_types=["text/plain"],
    )

    transcript = DriveFile(file_id="t1", name="Meeting 1", mime_type="text/plain", modified_time="2024-01-01T00:00:00Z")
    drive = FakeDriveClient([transcript])
    drive.exports["t1"] = "Transcript text"

    summary = MeetingSummary(
        title="Meeting 1",
        overview=["Overview"],
        key_findings=["Finding"],
        todos=[ActionItem(owner="", task="Do thing", due_date=None)],
    )
    summarizer = FakeSummarizer(summary)
    manifest = Manifest(config.manifest_path)

    service = SummaryService(config, drive, summarizer, manifest)
    report = service.run(dry_run=True)

    assert report.processed == ["Meeting 1"]
    assert drive.created == []
    assert summarizer.calls == []  # dry-run should not call summarizer


def test_service_processes_and_marks_manifest(tmp_path):
    config = Config(
        source_folder_id="source",
        dest_folder_id="dest",
        manifest_path=str(tmp_path / "manifest.json"),
        summary_format="markdown",
        openai_model="gpt-5",
        transcript_mime_types=["text/plain"],
    )

    transcript = DriveFile(file_id="t1", name="Meeting 1", mime_type="text/plain", modified_time="2024-01-01T00:00:00Z")
    drive = FakeDriveClient([transcript])
    drive.exports["t1"] = "Transcript text"

    summary = MeetingSummary(
        title="Meeting 1",
        overview=["Overview"],
        key_findings=["Finding"],
        todos=[ActionItem(owner="", task="Do thing", due_date=None)],
    )
    summarizer = FakeSummarizer(summary)
    manifest = Manifest(config.manifest_path)

    service = SummaryService(config, drive, summarizer, manifest)
    report = service.run()

    assert report.processed == ["Meeting 1"]
    assert len(drive.created) == 1
    # Suffix should use source modified_time (2024-01-01T00:00:00Z).
    assert drive.created[0][1] == "Meeting 1 - Summary_20240101_000000.md"

    manifest2 = Manifest(config.manifest_path)
    manifest2.load()
    assert "t1" in manifest2.items
