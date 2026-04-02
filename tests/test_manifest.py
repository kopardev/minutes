from datetime import datetime, timedelta, timezone

from meeting_summary.drive_client import DriveFile
from meeting_summary.manifest import Manifest


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_manifest_roundtrip(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest(str(path))
    file = DriveFile(file_id="1", name="Test", mime_type="text/plain", modified_time=iso(datetime.now(timezone.utc)))

    manifest.mark_processed(file, "summary-1")
    manifest.save()

    reloaded = Manifest(str(path))
    reloaded.load()

    assert "1" in reloaded.items
    assert reloaded.items["1"].summary_file_id == "summary-1"


def test_is_processed_respects_modified_time(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = Manifest(str(path))

    earlier = datetime.now(timezone.utc) - timedelta(days=1)
    later = datetime.now(timezone.utc)

    file = DriveFile(file_id="1", name="Test", mime_type="text/plain", modified_time=iso(earlier))
    manifest.mark_processed(file, "summary-1")

    updated = DriveFile(file_id="1", name="Test", mime_type="text/plain", modified_time=iso(later))

    assert manifest.is_processed(file) is True
    assert manifest.is_processed(updated) is False
