from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request

from .summary_schema import (
    EXTRACTION_SCHEMA,
    MeetingSummary,
    _json_from_text,
    parse_llm_response,
    split_transcript,
)


logger = logging.getLogger(__name__)


class OllamaSummarizer:
    def __init__(self, model: str, base_url: str = "http://localhost:11434", use_chunks: bool = False):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._use_chunks = use_chunks

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        source_text = transcript_text.strip()
        if not source_text:
            return MeetingSummary(title=title_hint, overview=["Transcript was empty."])

        if self._use_chunks:
            chunks = split_transcript(source_text)
            data = self._extract_from_chunks(chunks, title_hint)
            return parse_llm_response(data, title_hint)

        logger.info("Ollama: 1 chunk(s) to process for '%s'", title_hint)
        try:
            logger.info("Ollama: chunk 1/1 sending to API")
            data = self._extract(source_text, title_hint, 1, 1)
            logger.info("Ollama: chunk 1/1 received")
        except TimeoutError:
            logger.warning(
                "Ollama: single-pass request for '%s' timed out after 300s and 600s; retrying with 10 chunks",
                title_hint,
            )
            chunks = _split_into_target_chunks(source_text, 10)
            data = self._extract_from_chunks(chunks, title_hint)

        return parse_llm_response(data, title_hint)

    def _extract_from_chunks(self, chunks: list[str], title_hint: str) -> dict[str, Any]:
        logger.info("Ollama: %s chunk(s) to process for '%s'", len(chunks), title_hint)

        if len(chunks) == 1:
            logger.info("Ollama: chunk 1/1 sending to API")
            data = self._extract(chunks[0], title_hint, 1, 1)
            logger.info("Ollama: chunk 1/1 received")
            return data

        # Collect partial extractions per chunk, then consolidate in one final call.
        partials: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            logger.info("Ollama: chunk %s/%s sending to API", index, len(chunks))
            partial = self._chat_json(
                self._system_prompt(),
                self._user_payload(chunk, title_hint, index, len(chunks)),
            )
            logger.info("Ollama: chunk %s/%s received", index, len(chunks))
            partials.append(json.dumps(partial))
        combined = "\n\n".join(partials)
        logger.info("Ollama: consolidating %s chunk summaries", len(chunks))
        data = self._extract(combined, title_hint, 1, 1)
        logger.info("Ollama: final consolidated response received")
        return data

    def _extract(self, text: str, title_hint: str, chunk_index: int, total_chunks: int) -> dict[str, Any]:
        return self._chat_json(
            self._system_prompt(),
            self._user_payload(text, title_hint, chunk_index, total_chunks),
        )

    @staticmethod
    def _system_prompt() -> str:
        schema_text = json.dumps(EXTRACTION_SCHEMA)
        return (
            "/no_think\n"
            "You are an expert technical bioinformatics research project manager producing high-density executive summaries from meeting transcripts.\n"
            "Your job is to extract only actionable, decision-oriented information for stakeholders.\n\n"
            "Core rules:\n"
            "- Be concise and information-dense.\n"
            "- Use in-depth domain knowledge everywhere.\n"
            "- Ignore filler, pleasantries, repetition, and off-topic discussion.\n"
            "- Prioritize decisions, milestones, blockers, risks, dependencies, and explicit action items.\n"
            "- Do not invent facts. If a detail is not explicitly stated, use null or omit it.\n"
            "- Return ONLY valid JSON. No prose, no markdown, no code fences.\n\n"
            f"Output schema: {schema_text}\n"
            "Section rules:\n"
            "- overview: 3 to 5 bullets capturing strategic context and meeting outcome.\n"
            "- key_findings: up to 10 bullets, focused on decisions made, milestones reached, or important conclusions.\n"
            "- todos: include only explicit action items with named owners when stated; split one action per owner/task pair.\n"
            "- risks: include technical, staffing, timeline, dependency, or scope risks.\n"
            "- open_questions: include unresolved items that need stakeholder input or follow-up.\n\n"
            "Formatting rules:\n"
            "- Each array item must be a plain string, except todos which must be objects.\n"
            "- Use short, direct phrasing.\n"
            "- Prefer concrete nouns and verbs.\n"
            "- Keep wording consistent across entries.\n"
            "- If no todos are found, return \"todos\": [].\n"
            "- If no items exist for any other section, return an empty array."
        )

    @staticmethod
    def _user_payload(text: str, title_hint: str, chunk_index: int, total_chunks: int) -> dict[str, Any]:
        return {
            "meeting_title": title_hint,
            "chunk": f"{chunk_index} of {total_chunks}",
            "output_schema": EXTRACTION_SCHEMA,
            "transcript": text,
        }

    def _chat_json(self, system: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload)},
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

        raw = self._post_with_timeout_retries(req)
        logger.info("Ollama: raw JSON response received (%s chars)", len(raw))

        response_payload = json.loads(raw)
        model_text = str(response_payload.get("message", {}).get("content", "")).strip()
        logger.info("Ollama: extracted model content (%s chars)", len(model_text))
        return _json_from_text(model_text)

    def _post_with_timeout_retries(self, req: request.Request) -> str:
        last_exc: TimeoutError | None = None
        for timeout in (300, 600):
            try:
                with request.urlopen(req, timeout=timeout) as response:  # noqa: S310
                    return response.read().decode("utf-8")
            except TimeoutError as exc:
                last_exc = exc
                if timeout == 300:
                    logger.warning("Ollama request timed out after 300s; retrying once with 600s")
                else:
                    logger.error("Ollama request timed out after 600s")
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unreachable timeout retry state")


def _split_into_target_chunks(text: str, target_chunks: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunk_count = max(1, min(target_chunks, len(text)))
    base_size, remainder = divmod(len(text), chunk_count)
    chunks: list[str] = []
    start = 0
    for index in range(chunk_count):
        size = base_size + (1 if index < remainder else 0)
        end = start + size
        chunks.append(text[start:end])
        start = end
    return chunks


def _parse_json_text(text: str) -> dict:
    """Backward-compatible alias used by tests."""
    return _json_from_text(text)
