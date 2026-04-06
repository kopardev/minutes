import json

from minutes.ollama_summarizer import _parse_json_text


def test_parse_json_text_plain_json() -> None:
    data = {"title": "t", "overview": "o"}
    assert _parse_json_text(json.dumps(data)) == data


def test_parse_json_text_fenced_json() -> None:
    raw = "```json\n{\"title\": \"t\", \"overview\": \"o\"}\n```"
    assert _parse_json_text(raw) == {"title": "t", "overview": "o"}
