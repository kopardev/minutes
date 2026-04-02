from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Config:
    source_folder_id: str
    dest_folder_id: str
    manifest_path: str
    summary_format: str
    openai_model: str
    transcript_mime_types: Sequence[str]


DEFAULT_TRANSCRIPT_MIME_TYPES = [
    "application/vnd.google-apps.document",
    "text/plain",
]


def _split_csv(value: str | None, default: Sequence[str]) -> list[str]:
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def load_config(
    *,
    source_folder_id: str | None = None,
    dest_folder_id: str | None = None,
    manifest_path: str | None = None,
    summary_format: str | None = None,
    openai_model: str | None = None,
    transcript_mime_types: str | None = None,
) -> Config:
    source = source_folder_id or os.getenv("TRANSCRIPTS_FOLDER_ID", "")
    dest = dest_folder_id or os.getenv("SUMMARIES_FOLDER_ID", "")
    if not source or not dest:
        missing = []
        if not source:
            missing.append("TRANSCRIPTS_FOLDER_ID")
        if not dest:
            missing.append("SUMMARIES_FOLDER_ID")
        raise ValueError(f"Missing required config: {', '.join(missing)}")

    manifest = manifest_path or os.getenv("MANIFEST_PATH", "manifest.json")
    fmt = (summary_format or os.getenv("SUMMARY_FORMAT", "markdown")).lower()
    model = openai_model or os.getenv("OPENAI_MODEL", "gpt-5")
    mime_types = _split_csv(transcript_mime_types or os.getenv("TRANSCRIPT_MIME_TYPES"), DEFAULT_TRANSCRIPT_MIME_TYPES)

    return Config(
        source_folder_id=source,
        dest_folder_id=dest,
        manifest_path=manifest,
        summary_format=fmt,
        openai_model=model,
        transcript_mime_types=mime_types,
    )
