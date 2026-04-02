from __future__ import annotations

import json
from urllib import request

from .openai_client import MeetingSummary, _parse_action_items


class OllamaSummarizer:
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url.rstrip("/")

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        system = (
            "You are a precise meeting summarizer. "
            "Return only valid JSON with keys: title, overview, key_outcomes, decisions, "
            "action_items, risks, open_questions."
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

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self._base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(req, timeout=180) as response:  # noqa: S310
            raw = response.read().decode("utf-8")

        response_payload = json.loads(raw)
        model_text = str(response_payload.get("message", {}).get("content", "")).strip()
        data = _parse_json_text(model_text)

        return MeetingSummary(
            title=str(data.get("title", "")).strip() or title_hint,
            overview=str(data.get("overview", "")).strip(),
            key_outcomes=[str(x).strip() for x in data.get("key_outcomes", []) if str(x).strip()],
            decisions=[str(x).strip() for x in data.get("decisions", []) if str(x).strip()],
            action_items=_parse_action_items(data.get("action_items", []) or []),
            risks=[str(x).strip() for x in data.get("risks", []) if str(x).strip()],
            open_questions=[str(x).strip() for x in data.get("open_questions", []) if str(x).strip()],
        )


def _parse_json_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
