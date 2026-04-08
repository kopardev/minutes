from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from minutes.drive_client import DriveClient, DriveFile
from minutes.drive_client import _decode_transcript_bytes, _markdown_to_gdoc_text_and_styles, _markdown_to_html
from minutes.drive_client import _markdown_to_pdf_bytes


def test_decode_transcript_bytes_utf8() -> None:
    text = "Hello world"
    assert _decode_transcript_bytes(text.encode("utf-8")) == text


def test_decode_transcript_bytes_utf16_with_bom() -> None:
    text = "Seqinfomics transcript"
    assert _decode_transcript_bytes(text.encode("utf-16")) == text


def test_decode_transcript_bytes_invalid_utf8_fallback() -> None:
    raw = b"\xff\xfeH\x00i\x00"
    assert _decode_transcript_bytes(raw) == "Hi"


def _make_http_error(status: int) -> HttpError:
    return HttpError(
        resp=SimpleNamespace(status=status, reason="test-reason"),
        content=b"{}",
        uri="https://example.test",
    )


def test_export_text_retries_on_500_then_succeeds(monkeypatch) -> None:
    class FakeFiles:
        def get_media(self, fileId):  # noqa: N803
            return object()

    class FakeService:
        def files(self):
            return FakeFiles()

    class FakeDownloader:
        calls = 0

        def __init__(self, fh, request):
            self._fh = fh

        def next_chunk(self):
            FakeDownloader.calls += 1
            if FakeDownloader.calls == 1:
                raise _make_http_error(500)
            self._fh.write(b"retry success")
            return None, True

    sleeps: list[int] = []

    monkeypatch.setattr("minutes.drive_client.MediaIoBaseDownload", FakeDownloader)
    monkeypatch.setattr("minutes.drive_client.time.sleep", lambda seconds: sleeps.append(seconds))

    client = object.__new__(DriveClient)
    client._service = FakeService()

    file = DriveFile(file_id="f1", name="Retry Doc", mime_type="text/plain", modified_time=None)
    text = client.export_text(file)

    assert text == "retry success"
    assert FakeDownloader.calls == 2
    assert sleeps == [1]


def test_export_text_does_not_retry_non_retryable(monkeypatch) -> None:
    class FakeFiles:
        def get_media(self, fileId):  # noqa: N803
            return object()

    class FakeService:
        def files(self):
            return FakeFiles()

    class FakeDownloader:
        calls = 0

        def __init__(self, fh, request):
            self._fh = fh

        def next_chunk(self):
            FakeDownloader.calls += 1
            raise _make_http_error(404)

    monkeypatch.setattr("minutes.drive_client.MediaIoBaseDownload", FakeDownloader)

    client = object.__new__(DriveClient)
    client._service = FakeService()
    file = DriveFile(file_id="f2", name="Missing Doc", mime_type="text/plain", modified_time=None)

    with pytest.raises(HttpError):
        client.export_text(file)

    assert FakeDownloader.calls == 1


def test_list_files_retries_on_broken_pipe(monkeypatch) -> None:
    class FakeExecute:
        calls = 0

        def execute(self):
            FakeExecute.calls += 1
            if FakeExecute.calls == 1:
                raise BrokenPipeError(32, "Broken pipe")
            return {"files": [{"id": "1", "name": "doc", "mimeType": "text/plain", "modifiedTime": None}]}

    class FakeFiles:
        def list(self, **kwargs):
            return FakeExecute()

    class FakeService:
        def files(self):
            return FakeFiles()

    sleeps: list[int] = []
    monkeypatch.setattr("minutes.drive_client.time.sleep", lambda seconds: sleeps.append(seconds))

    client = object.__new__(DriveClient)
    client._service = FakeService()

    out = client.list_files("folder")

    assert out[0]["id"] == "1"
    assert FakeExecute.calls == 2
    assert sleeps == [1]


def test_create_pdf_file_retries_on_broken_pipe(monkeypatch) -> None:
    class FakeExecute:
        calls = 0

        def execute(self):
            FakeExecute.calls += 1
            if FakeExecute.calls == 1:
                raise BrokenPipeError(32, "Broken pipe")
            return {"id": "pdf-1", "name": "summary.pdf"}

    class FakeFiles:
        def create(self, **kwargs):
            return FakeExecute()

    class FakeService:
        def files(self):
            return FakeFiles()

    sleeps: list[int] = []
    monkeypatch.setattr("minutes.drive_client.time.sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr("minutes.drive_client._markdown_to_pdf_bytes", lambda _content: b"pdf")

    client = object.__new__(DriveClient)
    client._service = FakeService()

    out = client.create_pdf_file("folder", "summary", "# Title")

    assert out["id"] == "pdf-1"
    assert FakeExecute.calls == 2
    assert sleeps == [1]


def test_markdown_to_gdoc_converts_headings_and_bullets() -> None:
    markdown = "# Title\n\n## Overview\n- A\n- B"
    text, requests = _markdown_to_gdoc_text_and_styles(markdown)

    assert "#" not in text
    assert "- " not in text
    assert text.startswith("Title\n")
    assert any("updateParagraphStyle" in req for req in requests)
    assert any("createParagraphBullets" in req for req in requests)


def test_markdown_to_html_converts_structure() -> None:
    markdown = "# Title\n\n## Overview\n- A\n- B\n\nPlain"
    rendered = _markdown_to_html(markdown)

    assert "<h1>Title</h1>" in rendered
    assert "<h2>Overview</h2>" in rendered
    assert "<li>A</li>" in rendered
    assert "<li>B</li>" in rendered
    assert "<p>Plain</p>" in rendered


def test_markdown_to_html_escapes_html_chars() -> None:
    markdown = "# <Unsafe>\n- 1 < 2"
    rendered = _markdown_to_html(markdown)

    assert "&lt;Unsafe&gt;" in rendered
    assert "1 &lt; 2" in rendered


def test_upload_summary_pdf_routes_to_pdf_creator(monkeypatch) -> None:
    client = object.__new__(DriveClient)

    called: dict[str, str] = {}

    def _fake_create_pdf(folder_id: str, name: str, markdown_content: str) -> dict:
        called["folder_id"] = folder_id
        called["name"] = name
        called["content"] = markdown_content
        return {"id": "pdf-1", "name": f"{name}.pdf"}

    monkeypatch.setattr(client, "create_pdf_file", _fake_create_pdf)

    out = client.upload_summary("folder", "summary-name", "# T", "pdf")

    assert out["id"] == "pdf-1"
    assert called["folder_id"] == "folder"
    assert called["name"] == "summary-name"
    assert called["content"] == "# T"


def test_markdown_to_pdf_generates_pdf_bytes() -> None:
    pytest.importorskip("reportlab")
    raw = _markdown_to_pdf_bytes("# Title\n\n## Overview\n- Item")
    assert raw.startswith(b"%PDF")
    assert len(raw) > 100
