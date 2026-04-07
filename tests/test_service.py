from minutes.config import Config
from minutes.drive_client import DriveFile, FakeDriveClient
from minutes.manifest import Manifest
from minutes.summary_schema import ActionItem, FakeSummarizer, MeetingSummary
from minutes.service import SummaryService, _timestamp_from_source


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
    # Filename should use the same local-time prefix derived from the source timestamp.
    expected_name = f"{_timestamp_from_source(transcript)}_Meeting 1.md"
    assert drive.created[0][1] == expected_name

    manifest2 = Manifest(config.manifest_path)
    manifest2.load()
    assert "t1" in manifest2.items


def test_service_max_files_ignores_already_processed_items(tmp_path):
    config = Config(
        source_folder_id="source",
        dest_folder_id="dest",
        manifest_path=str(tmp_path / "manifest.json"),
        summary_format="markdown",
        openai_model="gpt-5",
        transcript_mime_types=["text/plain"],
    )

    transcripts = [
        DriveFile(file_id="t1", name="Meeting 1", mime_type="text/plain", modified_time="2024-01-01T00:00:00Z"),
        DriveFile(file_id="t2", name="Meeting 2", mime_type="text/plain", modified_time="2024-01-02T00:00:00Z"),
        DriveFile(file_id="t3", name="Meeting 3", mime_type="text/plain", modified_time="2024-01-03T00:00:00Z"),
    ]
    drive = FakeDriveClient(transcripts)
    drive.exports["t2"] = "Transcript text 2"
    drive.exports["t3"] = "Transcript text 3"

    summary = MeetingSummary(
        title="Meeting",
        overview=["Overview"],
        key_findings=["Finding"],
        todos=[ActionItem(owner="", task="Do thing", due_date=None)],
    )
    summarizer = FakeSummarizer(summary)
    manifest = Manifest(config.manifest_path)
    manifest.mark_processed(transcripts[0], "summary-1")
    manifest.save()

    service = SummaryService(config, drive, summarizer, manifest)
    report = service.run(max_files=1)

    assert report.processed == ["Meeting 2"]
    assert report.skipped == ["Meeting 1"]
    assert len(drive.created) == 1
    expected_name = f"{_timestamp_from_source(transcripts[1])}_Meeting 2.md"
    assert drive.created[0][1] == expected_name
