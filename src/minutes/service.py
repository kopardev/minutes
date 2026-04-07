from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
import logging
from typing import Iterable, Protocol

from .config import Config
from .drive_client import DriveClient, DriveFile
from .manifest import Manifest
from .summarizer import render_markdown


logger = logging.getLogger(__name__)


class Summarizer(Protocol):
    def summarize(self, transcript_text: str, title_hint: str): ...


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
        summarizer: Summarizer,
        manifest: Manifest,
    ):
        self._config = config
        self._drive = drive
        self._summarizer = summarizer
        self._manifest = manifest

    def run(self, *, dry_run: bool = False, force: bool = False, max_files: int | None = None) -> RunReport:
        logger.info("Loading manifest: %s", self._config.manifest_path)
        self._manifest.load()
        processed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        started = 0

        logger.info("Listing transcripts from source folder: %s", self._config.source_folder_id)
        transcripts = self._drive.list_transcripts(self._config.source_folder_id)
        candidates = [t for t in transcripts if self._is_supported_mime(t)]
        logger.info("Found %d supported candidates", len(candidates))
        if max_files is not None:
            logger.info("Will process up to %d new transcripts", max_files)

        for idx, transcript in enumerate(candidates, start=1):
            try:
                logger.info("[%d/%d] Starting: %s", idx, len(candidates), transcript.name)
                if not force and self._manifest.is_processed(transcript):
                    logger.info("[%d/%d] Skipping (already in manifest): %s", idx, len(candidates), transcript.name)
                    skipped.append(transcript.name)
                    continue

                timestamp = _timestamp_from_source(transcript)
                ext = ".md" if self._config.summary_format == "markdown" else ""
                summary_name = f"{timestamp}_{transcript.name}{ext}"
                existing = self._drive.find_file_by_name(self._config.dest_folder_id, summary_name)
                if existing and not force:
                    self._manifest.mark_processed(transcript, existing.get("id", ""))
                    logger.info("[%d/%d] Skipping (same summary exists): %s", idx, len(candidates), transcript.name)
                    skipped.append(transcript.name)
                    continue

                if max_files is not None and started >= max_files:
                    logger.info("Reached max_files=%d after %d new transcripts", max_files, started)
                    break

                started += 1

                if dry_run:
                    logger.info("[%d/%d] Dry run only (not summarizing/uploading): %s", idx, len(candidates), transcript.name)
                    processed.append(transcript.name)
                    continue

                logger.info("[%d/%d] Exporting transcript text", idx, len(candidates))
                text = self._drive.export_text(transcript)
                logger.info("[%d/%d] Generating summary via %s", idx, len(candidates), self._config.llm_provider)
                summary = self._summarizer.summarize(text, transcript.name)
                markdown = render_markdown(summary)

                logger.info("[%d/%d] Uploading summary: %s", idx, len(candidates), summary_name)
                created = self._drive.upload_summary(
                    self._config.dest_folder_id,
                    summary_name,
                    markdown,
                    self._config.summary_format,
                )
                self._manifest.mark_processed(transcript, created.get("id", ""))
                logger.info("[%d/%d] Completed: %s", idx, len(candidates), transcript.name)
                processed.append(transcript.name)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[%d/%d] Failed: %s", idx, len(candidates), transcript.name)
                errors.append(f"{transcript.name}: {exc}")

        if not dry_run:
            logger.info("Saving manifest: %s", self._config.manifest_path)
            self._manifest.save()

        logger.info("Run finished: processed=%d skipped=%d errors=%d", len(processed), len(skipped), len(errors))

        return RunReport(processed=processed, skipped=skipped, errors=errors)

    def _is_supported_mime(self, file: DriveFile) -> bool:
        return file.mime_type in self._config.transcript_mime_types


def _timestamp_from_source(transcript: DriveFile) -> str:
    """Build output filename timestamp from source file modified_time when possible.
    
    Converts UTC timestamps to local timezone before formatting.
    """
    value = (transcript.modified_time or "").strip()
    if not value:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Drive timestamps are RFC3339, often ending with 'Z' (UTC).
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt_utc = datetime.fromisoformat(normalized)
        # Convert from UTC to local timezone for the output timestamp.
        dt_local = dt_utc.astimezone()
        return dt_local.strftime("%Y%m%d_%H%M%S")
    except ValueError:
        logger.warning("Invalid source modified_time '%s'; falling back to current timestamp", value)
        return datetime.now().strftime("%Y%m%d_%H%M%S")
