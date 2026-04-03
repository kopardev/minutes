from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ActionItem:
    owner: str
    task: str
    due_date: str | None


@dataclass(frozen=True)
class MeetingSummary:
    title: str
    overview: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    todos: list[ActionItem] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


# Schema shown to the LLM for concise executive output.
EXTRACTION_SCHEMA = {
    "overview": ["3-5 short bullets of what happened"],
    "key_findings": ["important update or decision"],
    "todos": [
        {"owner": "person name or empty string", "task": "what needs to be done", "due_date": "YYYY-MM-DD or null"}
    ],
    "risks": ["important risk/blocker"],
    "open_questions": ["unresolved question"],
}


def split_transcript(text: str, chunk_size: int = 10000, overlap: int = 500) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _strip_think(text: str) -> str:
    """Remove <think>…</think> blocks emitted by reasoning models (e.g. Qwen3)."""
    return _THINK_RE.sub("", text).strip()


def _json_from_text(text: str) -> dict[str, Any]:
    raw = _strip_think(text)
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return json.loads(raw)


def parse_llm_response(data: dict[str, Any], title_hint: str) -> MeetingSummary:
    """Convert raw LLM JSON dict into concise summary sections."""

    def to_text_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    overview = to_text_list(data.get("overview", []))
    key_findings = to_text_list(data.get("key_findings", []))
    risks = to_text_list(data.get("risks", []))
    open_questions = to_text_list(data.get("open_questions", []))

    # Backward compatibility for old dynamic-sections payloads.
    if not key_findings and isinstance(data.get("sections"), list):
        for section in data["sections"]:
            if not isinstance(section, dict):
                continue
            title = str(section.get("title", "")).strip().lower()
            items = to_text_list(section.get("items", []))
            if title == "todos":
                continue
            key_findings.extend(items)

    todos: list[ActionItem] = []
    for raw_todo in data.get("todos", []):
        if not isinstance(raw_todo, dict):
            continue
        task = str(raw_todo.get("task", "")).strip()
        if not task:
            continue
        owner = str(raw_todo.get("owner", "")).strip()
        due_raw = str(raw_todo.get("due_date", "")).strip()
        due_date = due_raw if due_raw and due_raw.lower() != "null" else None
        todos.append(ActionItem(owner=owner, task=task, due_date=due_date))

    return MeetingSummary(
        title=title_hint,
        overview=overview,
        key_findings=key_findings,
        todos=todos,
        risks=risks,
        open_questions=open_questions,
    )


class FakeSummarizer:
    def __init__(self, summary: MeetingSummary):
        self.summary = summary
        self.calls: list[tuple[str, str]] = []

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        self.calls.append((transcript_text, title_hint))
        return self.summary
