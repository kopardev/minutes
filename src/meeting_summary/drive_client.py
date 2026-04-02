from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
MARKDOWN_MIME = "text/markdown"


def _decode_transcript_bytes(data: bytes) -> str:
    # Many exported transcript files are UTF-16 with BOM. Try common encodings
    # first, then fallback to replacement so one odd byte does not fail a run.
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class DriveFile:
    file_id: str
    name: str
    mime_type: str
    modified_time: str | None


class DriveClient:
    def __init__(self, credentials_path: str | None = None, token_path: str | None = None):
        scopes = ["https://www.googleapis.com/auth/drive"]

        creds = None
        if token_path and os.path.exists(token_path):
            creds = UserCredentials.from_authorized_user_file(token_path, scopes=scopes)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
        elif credentials_path:
            creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=scopes)

        if creds is None:
            raise ValueError("Provide either token_path (OAuth token.json) or credentials_path (service account JSON)")

        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def list_files(self, folder_id: str, query_extra: str = "") -> list[dict]:
        query = f"'{folder_id}' in parents and trashed = false"
        if query_extra:
            query = f"{query} and {query_extra}"
        files: list[dict] = []
        page_token = None
        while True:
            response = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                    pageToken=page_token,
                )
                .execute()
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return files

    def list_transcripts(self, folder_id: str) -> list[DriveFile]:
        files = self.list_files(folder_id)
        return [
            DriveFile(
                file_id=f["id"],
                name=f.get("name", ""),
                mime_type=f.get("mimeType", ""),
                modified_time=f.get("modifiedTime"),
            )
            for f in files
        ]

    def export_text(self, file: DriveFile) -> str:
        if file.mime_type == GOOGLE_DOC_MIME:
            request = self._service.files().export_media(fileId=file.file_id, mimeType="text/plain")
        else:
            request = self._service.files().get_media(fileId=file.file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return _decode_transcript_bytes(fh.getvalue())

    def find_file_by_name(self, folder_id: str, name: str) -> dict | None:
        query_extra = f"name = '{name.replace("'", "\\'")}'"
        files = self.list_files(folder_id, query_extra=query_extra)
        return files[0] if files else None

    def create_markdown_file(self, folder_id: str, name: str, content: str) -> dict:
        file_metadata = {
            "name": name,
            "parents": [folder_id],
            "mimeType": MARKDOWN_MIME,
        }
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=MARKDOWN_MIME, resumable=False)
        return self._service.files().create(body=file_metadata, media_body=media, fields="id, name").execute()

    def create_google_doc(self, folder_id: str, name: str, content: str) -> dict:
        file_metadata = {
            "name": name,
            "parents": [folder_id],
            "mimeType": GOOGLE_DOC_MIME,
        }
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain", resumable=False)
        return self._service.files().create(body=file_metadata, media_body=media, fields="id, name").execute()

    def upload_summary(self, folder_id: str, name: str, content: str, summary_format: str) -> dict:
        if summary_format == "gdoc":
            return self.create_google_doc(folder_id, name, content)
        return self.create_markdown_file(folder_id, name, content)


class FakeDriveClient:
    """Test double for DriveClient."""

    def __init__(self, transcripts: Iterable[DriveFile]):
        self.transcripts = list(transcripts)
        self.exports: dict[str, str] = {}
        self.created: list[tuple[str, str, str, str]] = []
        self.existing: dict[tuple[str, str], dict] = {}

    def list_transcripts(self, folder_id: str) -> list[DriveFile]:
        return list(self.transcripts)

    def export_text(self, file: DriveFile) -> str:
        return self.exports[file.file_id]

    def find_file_by_name(self, folder_id: str, name: str) -> dict | None:
        return self.existing.get((folder_id, name))

    def upload_summary(self, folder_id: str, name: str, content: str, summary_format: str) -> dict:
        self.created.append((folder_id, name, content, summary_format))
        return {"id": f"created-{len(self.created)}", "name": name}
