from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dateutil.parser import isoparse

from .drive_client import DriveFile


@dataclass
class ManifestEntry:
    summary_file_id: str
    processed_at: str
    source_modified_time: str | None
    source_name: str


class Manifest:
    def __init__(self, path: str):
        self.path = Path(path)
        self.items: dict[str, ManifestEntry] = {}

    def load(self) -> None:
        if not self.path.exists():
            self.items = {}
            return
        data = json.loads(self.path.read_text())
        items = data.get("items", {})
        self.items = {
            key: ManifestEntry(
                summary_file_id=value.get("summary_file_id", ""),
                processed_at=value.get("processed_at", ""),
                source_modified_time=value.get("source_modified_time"),
                source_name=value.get("source_name", ""),
            )
            for key, value in items.items()
        }

    def save(self) -> None:
        data = {
            "version": 1,
            "items": {
                key: {
                    "summary_file_id": entry.summary_file_id,
                    "processed_at": entry.processed_at,
                    "source_modified_time": entry.source_modified_time,
                    "source_name": entry.source_name,
                }
                for key, entry in self.items.items()
            },
        }
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))

    def mark_processed(self, file: DriveFile, summary_file_id: str) -> None:
        self.items[file.file_id] = ManifestEntry(
            summary_file_id=summary_file_id,
            processed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_modified_time=file.modified_time,
            source_name=file.name,
        )

    def is_processed(self, file: DriveFile) -> bool:
        entry = self.items.get(file.file_id)
        if not entry:
            return False
        if not entry.source_modified_time or not file.modified_time:
            return True
        try:
            prev = isoparse(entry.source_modified_time)
            current = isoparse(file.modified_time)
        except ValueError:
            return True
        return current <= prev
