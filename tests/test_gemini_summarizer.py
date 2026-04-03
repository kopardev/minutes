import io

import pytest
from urllib.error import HTTPError
from urllib.request import Request

from meeting_summary.gemini_summarizer import (
    GeminiSummarizer,
    _compute_backoff_seconds,
    _extract_gemini_text,
    _parse_retry_after_header,
)


def test_extract_gemini_text_happy_path() -> None:
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": '{"overview": ["ok"], "key_findings": [], "todos": [], "risks": [], "open_questions": []}'}
                    ]
                }
            }
        ]
    }
    text = _extract_gemini_text(payload)
    assert text.startswith("{")


def test_extract_gemini_text_missing_candidates() -> None:
    with pytest.raises(ValueError, match="no candidates"):
        _extract_gemini_text({})


def test_parse_retry_after_header_int() -> None:
    exc = HTTPError(
        url="https://example.com",
        code=429,
        msg="Too Many Requests",
        hdrs={"Retry-After": "7"},
        fp=io.BytesIO(b"{}"),
    )
    assert _parse_retry_after_header(exc) == 7


def test_compute_backoff_uses_exponential_when_no_retry_after() -> None:
    exc = HTTPError(
        url="https://example.com",
        code=429,
        msg="Too Many Requests",
        hdrs={},
        fp=io.BytesIO(b"{}"),
    )
    assert _compute_backoff_seconds(exc, attempt=1) == 1
    assert _compute_backoff_seconds(exc, attempt=3) == 4


def test_request_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    summarizer = GeminiSummarizer(model="gemini-2.0-flash")

    calls = {"count": 0}

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self) -> bytes:
            return (
                b'{"candidates":[{"content":{"parts":[{"text":"{\\"overview\\":[],\\"key_findings\\":[],\\"todos\\":[],\\"risks\\":[],\\"open_questions\\":[]}"}]}}]}'
            )

    def _fake_urlopen(_req, timeout=300):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(
                url="https://example.com",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "1"},
                fp=io.BytesIO(b"{}"),
            )
        return _FakeResponse()

    sleeps: list[int] = []

    monkeypatch.setattr("meeting_summary.gemini_summarizer.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("meeting_summary.gemini_summarizer.time.sleep", lambda s: sleeps.append(s))

    out = summarizer._request_with_retry(req=Request(url="https://example.com"))

    assert calls["count"] == 2
    assert sleeps == [1]
    assert "candidates" in out
