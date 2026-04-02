from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class ActionItem:
    owner: str
    task: str
    due_date: str | None


@dataclass(frozen=True)
class MeetingSummary:
    title: str
    overview: str
    key_outcomes: list[str]
    decisions: list[str]
    action_items: list[ActionItem]
    risks: list[str]
    open_questions: list[str]


def _parse_action_items(raw: list[dict[str, Any]]) -> list[ActionItem]:
    items: list[ActionItem] = []
    for item in raw:
        items.append(
            ActionItem(
                owner=str(item.get("owner", "")).strip(),
                task=str(item.get("task", "")).strip(),
                due_date=(str(item.get("due_date", "")).strip() or None),
            )
        )
    return items


class OpenAISummarizer:
    def __init__(self, model: str):
        self._client = OpenAI()
        self._model = model

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        system = (
            "You are a precise meeting summarizer. Produce a concise JSON object with the required fields."
        )
        user = {
            "title_hint": title_hint,
            "transcript": transcript_text,
            "instructions": {
                "style": "Concise, factual, bullet-like phrases. Focus on outcomes and action items.",
                "fields": [
                    "title",
                    "overview",
                    "key_outcomes",
                    "decisions",
                    "action_items",
                    "risks",
                    "open_questions",
                ],
                "action_item_schema": {"owner": "", "task": "", "due_date": ""},
            },
        }

        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        )

        text = response.output_text
        data = json.loads(text)
        return MeetingSummary(
            title=str(data.get("title", "")).strip() or title_hint,
            overview=str(data.get("overview", "")).strip(),
            key_outcomes=[str(x).strip() for x in data.get("key_outcomes", []) if str(x).strip()],
            decisions=[str(x).strip() for x in data.get("decisions", []) if str(x).strip()],
            action_items=_parse_action_items(data.get("action_items", []) or []),
            risks=[str(x).strip() for x in data.get("risks", []) if str(x).strip()],
            open_questions=[str(x).strip() for x in data.get("open_questions", []) if str(x).strip()],
        )


class FakeSummarizer:
    def __init__(self, summary: MeetingSummary):
        self.summary = summary
        self.calls: list[tuple[str, str]] = []

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        self.calls.append((transcript_text, title_hint))
        return self.summary
