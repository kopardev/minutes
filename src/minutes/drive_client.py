from __future__ import annotations

import html
import io
import logging
import os
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Callable
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
MARKDOWN_MIME = "text/markdown"
HTML_MIME = "text/html"
PDF_MIME = "application/pdf"
RETRYABLE_EXPORT_STATUSES = {500, 503}
MAX_EXPORT_RETRIES = 4
RETRYABLE_DRIVE_STATUSES = {429, 500, 502, 503, 504}
MAX_DRIVE_REQUEST_RETRIES = 4
RETRYABLE_DRIVE_EXCEPTIONS = (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout, ssl.SSLEOFError)


logger = logging.getLogger(__name__)


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
        self._docs_service = build("docs", "v1", credentials=creds, cache_discovery=False)

    def list_files(self, folder_id: str, query_extra: str = "") -> list[dict]:
        query = f"'{folder_id}' in parents and trashed = false"
        if query_extra:
            query = f"{query} and {query_extra}"
        files: list[dict] = []
        page_token = None
        while True:
            response = self._execute_drive_request(
                lambda: self._service.files().list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                    pageToken=page_token,
                ),
                description="Drive file listing",
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
        logger.info("Drive export start: name=%s mime=%s id=%s", file.name, file.mime_type, file.file_id)
        for attempt in range(1, MAX_EXPORT_RETRIES + 1):
            fh = io.BytesIO()
            request = self._build_export_request(file)
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            try:
                while not done:
                    _, done = downloader.next_chunk()
                text = _decode_transcript_bytes(fh.getvalue())
                logger.info("Drive export success: name=%s chars=%s", file.name, len(text))
                return text
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                is_retryable = status in RETRYABLE_EXPORT_STATUSES
                if (not is_retryable) or attempt == MAX_EXPORT_RETRIES:
                    raise

                backoff_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "Drive export failed for file '%s' (status=%s). Retrying in %ss (attempt %s/%s).",
                    file.name,
                    status,
                    backoff_seconds,
                    attempt,
                    MAX_EXPORT_RETRIES,
                )
                time.sleep(backoff_seconds)

        raise RuntimeError("Unreachable: export retry loop exited unexpectedly")

    def _build_export_request(self, file: DriveFile):
        if file.mime_type == GOOGLE_DOC_MIME:
            return self._service.files().export_media(fileId=file.file_id, mimeType="text/plain")
        return self._service.files().get_media(fileId=file.file_id)

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
        return self._execute_drive_request(
            lambda: self._service.files().create(body=file_metadata, media_body=media, fields="id, name"),
            description=f"Drive markdown upload for '{name}'",
        )

    def create_html_file(self, folder_id: str, name: str, markdown_content: str) -> dict:
        file_metadata = {
            "name": f"{name}.html",
            "parents": [folder_id],
            "mimeType": HTML_MIME,
        }
        html_content = _markdown_to_html(markdown_content)
        media = MediaIoBaseUpload(io.BytesIO(html_content.encode("utf-8")), mimetype=HTML_MIME, resumable=False)
        return self._execute_drive_request(
            lambda: self._service.files().create(body=file_metadata, media_body=media, fields="id, name"),
            description=f"Drive HTML upload for '{name}'",
        )

    def create_pdf_file(self, folder_id: str, name: str, markdown_content: str) -> dict:
        file_metadata = {
            "name": f"{name}.pdf",
            "parents": [folder_id],
            "mimeType": PDF_MIME,
        }
        logger.info("PDF render start: name=%s markdown_chars=%s", name, len(markdown_content))
        pdf_content = _markdown_to_pdf_bytes(markdown_content)
        logger.info("PDF render success: name=%s pdf_bytes=%s", name, len(pdf_content))
        media = MediaIoBaseUpload(io.BytesIO(pdf_content), mimetype=PDF_MIME, resumable=False)
        logger.info("Drive PDF upload start: name=%s folder=%s", name, folder_id)
        created = self._execute_drive_request(
            lambda: self._service.files().create(body=file_metadata, media_body=media, fields="id, name"),
            description=f"Drive PDF upload for '{name}'",
        )
        logger.info("Drive PDF upload success: id=%s name=%s", created.get("id", ""), created.get("name", ""))
        return created

    def create_google_doc(self, folder_id: str, name: str, content: str) -> dict:
        file_metadata = {
            "name": name,
            "parents": [folder_id],
            "mimeType": GOOGLE_DOC_MIME,
        }
        # Create an empty Google Doc, then insert styled content. This avoids
        # leaving raw markdown in the document body.
        created = self._execute_drive_request(
            lambda: self._service.files().create(body=file_metadata, fields="id, name"),
            description=f"Google Doc creation for '{name}'",
        )
        doc_id = created["id"]

        # Apply rich formatting so the Google Doc is easier to scan.
        try:
            self._apply_google_doc_formatting(doc_id, content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to apply Google Doc formatting for '%s': %s", name, exc)
            # Hard fallback: replace the empty doc with a plain-text populated
            # Google Doc so we never leave a blank output artifact.
            return self._recreate_google_doc_with_plain_text(folder_id, name, content, doc_id)

        return created

    def upload_summary(self, folder_id: str, name: str, content: str, summary_format: str) -> dict:
        logger.info("Upload routing: format=%s name=%s", summary_format, name)
        if summary_format == "gdoc":
            return self.create_google_doc(folder_id, name, content)
        if summary_format == "html":
            return self.create_html_file(folder_id, name, content)
        if summary_format == "pdf":
            return self.create_pdf_file(folder_id, name, content)
        return self.create_markdown_file(folder_id, name, content)

    def _apply_google_doc_formatting(self, document_id: str, markdown_text: str) -> None:
        text, requests = _markdown_to_gdoc_text_and_styles(markdown_text)
        if not text:
            return

        # Insert full content first, then apply heading and bullet styles.
        self._execute_drive_request(
            lambda: self._docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
            ),
            description=f"Google Doc text insert for '{document_id}'",
        )

        if requests:
            self._execute_drive_request(
                lambda: self._docs_service.documents().batchUpdate(documentId=document_id, body={"requests": requests}),
                description=f"Google Doc formatting update for '{document_id}'",
            )

    def _insert_plain_doc_text(self, document_id: str, text: str) -> None:
        plain = text if text.endswith("\n") else f"{text}\n"
        self._execute_drive_request(
            lambda: self._docs_service.documents().batchUpdate(
                documentId=document_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": plain}}]},
            ),
            description=f"Google Doc plain text insert for '{document_id}'",
        )

    def _recreate_google_doc_with_plain_text(self, folder_id: str, name: str, content: str, doc_id: str) -> dict:
        try:
            self._execute_drive_request(
                lambda: self._service.files().delete(fileId=doc_id),
                description=f"Google Doc delete for '{doc_id}'",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed deleting blank Google Doc '%s' (%s): %s", name, doc_id, exc)

        file_metadata = {
            "name": name,
            "parents": [folder_id],
            "mimeType": GOOGLE_DOC_MIME,
        }
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/plain", resumable=False)
        return self._execute_drive_request(
            lambda: self._service.files().create(body=file_metadata, media_body=media, fields="id, name"),
            description=f"Google Doc fallback creation for '{name}'",
        )

    def _execute_drive_request(self, request_factory: Callable[[], object], *, description: str):
        for attempt in range(1, MAX_DRIVE_REQUEST_RETRIES + 1):
            try:
                return request_factory().execute()
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                if status not in RETRYABLE_DRIVE_STATUSES or attempt == MAX_DRIVE_REQUEST_RETRIES:
                    raise
                backoff_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "%s failed with status=%s. Retrying in %ss (attempt %s/%s).",
                    description,
                    status,
                    backoff_seconds,
                    attempt,
                    MAX_DRIVE_REQUEST_RETRIES,
                )
                time.sleep(backoff_seconds)
            except RETRYABLE_DRIVE_EXCEPTIONS as exc:
                if attempt == MAX_DRIVE_REQUEST_RETRIES:
                    raise
                backoff_seconds = 2 ** (attempt - 1)
                logger.warning(
                    "%s failed with %s. Retrying in %ss (attempt %s/%s).",
                    description,
                    exc.__class__.__name__,
                    backoff_seconds,
                    attempt,
                    MAX_DRIVE_REQUEST_RETRIES,
                )
                time.sleep(backoff_seconds)


def _markdown_to_gdoc_text_and_styles(markdown_text: str) -> tuple[str, list[dict]]:
    """Convert markdown-like summary text into plain text + docs style requests."""
    lines = markdown_text.splitlines()
    if not lines:
        return "", []

    rendered_lines: list[str] = []
    requests: list[dict] = []
    cursor = 1

    for line in lines:
        kind = "normal"
        stripped = line
        if line.startswith("# "):
            kind = "h1"
            stripped = line[2:].strip()
        elif line.startswith("## "):
            kind = "h2"
            stripped = line[3:].strip()
        elif line.startswith("- "):
            kind = "bullet"
            stripped = line[2:].strip()

        rendered_lines.append(stripped)
        para_end = cursor + len(stripped) + 1  # include trailing newline

        if kind == "h1":
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": cursor, "endIndex": para_end},
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_1",
                            "spaceBelow": {"magnitude": 12, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceBelow",
                    }
                }
            )
        elif kind == "h2":
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": cursor, "endIndex": para_end},
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_2",
                            "spaceAbove": {"magnitude": 10, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
        elif kind == "bullet" and stripped:
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": cursor, "endIndex": para_end},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                }
            )

        cursor = para_end

    text = "\n".join(rendered_lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text, requests


def _markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            continue

        if stripped.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            continue

        if stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
            continue

        if in_list:
            parts.append("</ul>")
            in_list = False
        parts.append(f"<p>{html.escape(stripped)}</p>")

    if in_list:
        parts.append("</ul>")

    body = "\n".join(parts)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "  <title>Meeting Summary</title>\n"
        "  <style>\n"
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 32px auto; max-width: 860px; line-height: 1.55; color: #1f2937; padding: 0 18px; }\n"
        "    h1 { font-size: 30px; margin: 0 0 18px; color: #0f172a; }\n"
        "    h2 { font-size: 19px; margin: 24px 0 8px; color: #0b3b8c; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }\n"
        "    p { margin: 10px 0; }\n"
        "    ul { margin: 8px 0 16px 22px; padding: 0; }\n"
        "    li { margin: 6px 0; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError("PDF output requires 'reportlab'. Install it with: pip install reportlab") from exc

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    page_width, page_height = LETTER

    left_margin = 0.8 * inch
    top_margin = page_height - 0.8 * inch
    bottom_margin = 0.8 * inch
    max_width = page_width - (2 * left_margin)

    y = top_margin

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            y -= 8
            if y < bottom_margin:
                pdf.showPage()
                y = top_margin
            continue

        if line.startswith("# "):
            font_name = "Helvetica-Bold"
            font_size = 16
            text = line[2:].strip()
            line_height = 20
        elif line.startswith("## "):
            font_name = "Helvetica-Bold"
            font_size = 13
            text = line[3:].strip()
            line_height = 17
        elif line.startswith("- "):
            font_name = "Helvetica"
            font_size = 11
            text = f"- {line[2:].strip()}"
            line_height = 15
        else:
            font_name = "Helvetica"
            font_size = 11
            text = line
            line_height = 15

        wrapped = _wrap_pdf_text(text, font_name, font_size, max_width, pdfmetrics)
        for segment in wrapped:
            if y < bottom_margin:
                pdf.showPage()
                y = top_margin
            pdf.setFont(font_name, font_size)
            pdf.drawString(left_margin, y, segment)
            y -= line_height

    pdf.save()
    return buffer.getvalue()


def _wrap_pdf_text(text: str, font_name: str, font_size: int, max_width: float, pdfmetrics_module) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    wrapped: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        width = pdfmetrics_module.stringWidth(candidate, font_name, font_size)
        if width <= max_width:
            current = candidate
            continue
        wrapped.append(current)
        current = word

    wrapped.append(current)
    return wrapped


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
