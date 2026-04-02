from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import Config
from .drive_client import DriveClient, DriveFile
from .manifest import Manifest
from .openai_client import OpenAISummarizer
from .summarizer import render_markdown


@dataclass
class RunReport:
    processed: list[str]
    skipped: list[str]
    errors: list[str]


class SummaryService:
    def __init__(
        self,
        config: Config,
        drive: DriveClient,
        summarizer: OpenAISummarizer,
        manifest: Manifest,
    ):
        self._config = config
        self._drive = drive
        self._summarizer = summarizer
        self._manifest = manifest

    def run(self, *, dry_run: bool = False, force: bool = False, max_files: int | None = None) -> RunReport:
        self._manifest.load()
        processed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        transcripts = self._drive.list_transcripts(self._config.source_folder_id)
        candidates = [t for t in transcripts if self._is_supported_mime(t)]
        if max_files is not None:
            candidates = candidates[:max_files]

        for transcript in candidates:
            try:
                if not force and self._manifest.is_processed(transcript):
                    skipped.append(transcript.name)
                    continue

                summary_name = f"{transcript.name} - Summary.md" if self._config.summary_format == "markdown" else f"{transcript.name} - Summary"
                existing = self._drive.find_file_by_name(self._config.dest_folder_id, summary_name)
                if existing and not force:
                    self._manifest.mark_processed(transcript, existing.get("id", ""))
                    skipped.append(transcript.name)
                    continue

                if dry_run:
                    processed.append(transcript.name)
                    continue

                text = self._drive.export_text(transcript)
                summary = self._summarizer.summarize(text, transcript.name)
                markdown = render_markdown(summary)

                created = self._drive.upload_summary(
                    self._config.dest_folder_id,
                    summary_name,
                    markdown,
                    self._config.summary_format,
                )
                self._manifest.mark_processed(transcript, created.get("id", ""))
                processed.append(transcript.name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{transcript.name}: {exc}")

        if not dry_run:
            self._manifest.save()

        return RunReport(processed=processed, skipped=skipped, errors=errors)

    def _is_supported_mime(self, file: DriveFile) -> bool:
        return file.mime_type in self._config.transcript_mime_types
