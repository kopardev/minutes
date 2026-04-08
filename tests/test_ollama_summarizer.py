import json

from minutes.ollama_summarizer import OllamaSummarizer, _parse_json_text, _split_into_target_chunks


def test_parse_json_text_plain_json() -> None:
    data = {"title": "t", "overview": "o"}
    assert _parse_json_text(json.dumps(data)) == data


def test_parse_json_text_fenced_json() -> None:
    raw = "```json\n{\"title\": \"t\", \"overview\": \"o\"}\n```"
    assert _parse_json_text(raw) == {"title": "t", "overview": "o"}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_ollama_retries_with_600_second_timeout(monkeypatch) -> None:
    timeouts: list[int] = []

    def _fake_urlopen(_req, timeout=300):
        timeouts.append(timeout)
        if timeout == 300:
            raise TimeoutError("timed out")
        return _FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "overview": ["Overview"],
                            "key_findings": [],
                            "todos": [],
                            "risks": [],
                            "open_questions": [],
                        }
                    )
                }
            }
        )

    monkeypatch.setattr("minutes.ollama_summarizer.request.urlopen", _fake_urlopen)

    summarizer = OllamaSummarizer(model="test-model")
    summary = summarizer.summarize("Transcript body", "Meeting")

    assert timeouts == [300, 600]
    assert summary.title == "Meeting"
    assert summary.overview == ["Overview"]


def test_ollama_falls_back_to_10_chunks_after_second_timeout(monkeypatch) -> None:
    call_timeouts: list[int] = []
    call_count = {"value": 0}

    def _fake_urlopen(_req, timeout=300):
        call_timeouts.append(timeout)
        call_count["value"] += 1
        if call_count["value"] <= 2:
            raise TimeoutError("timed out")
        return _FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "overview": ["Overview"],
                            "key_findings": [],
                            "todos": [],
                            "risks": [],
                            "open_questions": [],
                        }
                    )
                }
            }
        )

    monkeypatch.setattr("minutes.ollama_summarizer.request.urlopen", _fake_urlopen)

    text = "abcdefghij" * 20
    summarizer = OllamaSummarizer(model="test-model")
    summary = summarizer.summarize(text, "Meeting")

    assert summary.title == "Meeting"
    assert len(_split_into_target_chunks(text, 10)) == 10
    assert call_timeouts[:2] == [300, 600]
    assert len(call_timeouts) == 13


def test_split_into_target_chunks_returns_requested_count() -> None:
    chunks = _split_into_target_chunks("abcdefghij" * 10, 10)
    assert len(chunks) == 10
    assert "".join(chunks) == "abcdefghij" * 10
