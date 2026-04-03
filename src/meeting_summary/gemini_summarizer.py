from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError

from .summary_schema import EXTRACTION_SCHEMA, MeetingSummary, _json_from_text, parse_llm_response, split_transcript


logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUSES = {429, 500, 503}
MAX_GEMINI_RETRIES = 5


class GeminiSummarizer:
    def __init__(self, model: str, use_chunks: bool = False):
        self._model = model
        self._use_chunks = use_chunks
        self._api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not self._api_key:
            raise ValueError("Set GEMINI_API_KEY to use Gemini provider")

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        source_text = transcript_text.strip()
        if not source_text:
            return MeetingSummary(title=title_hint, overview=["Transcript was empty."])

        chunks = split_transcript(source_text) if self._use_chunks else [source_text]
        logger.info("Gemini: %s chunk(s) to process for '%s'", len(chunks), title_hint)

        if len(chunks) == 1:
            logger.info("Gemini: chunk 1/1 sending to API")
            data = self._generate_json(chunks[0], title_hint, 1, 1)
            logger.info("Gemini: chunk 1/1 received")
        else:
            partials: list[str] = []
            for index, chunk in enumerate(chunks, start=1):
                logger.info("Gemini: chunk %s/%s sending to API", index, len(chunks))
                part = self._generate_json(chunk, title_hint, index, len(chunks))
                logger.info("Gemini: chunk %s/%s received", index, len(chunks))
                partials.append(json.dumps(part))

            logger.info("Gemini: consolidating %s chunk summaries", len(chunks))
            combined = "\n\n".join(partials)
            data = self._generate_json(combined, title_hint, 1, 1)
            logger.info("Gemini: final consolidated response received")

        return parse_llm_response(data, title_hint)

    def _generate_json(self, text: str, title_hint: str, chunk_index: int, total_chunks: int) -> dict[str, Any]:
        prompt = self._build_prompt(text, title_hint, chunk_index, total_chunks)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        model_path = parse.quote(self._model, safe="")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent?key={self._api_key}"
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")

        raw = self._request_with_retry(req)

        data = json.loads(raw)
        text_out = _extract_gemini_text(data)
        return _json_from_text(text_out)

    def _request_with_retry(self, req: request.Request) -> str:
        for attempt in range(1, MAX_GEMINI_RETRIES + 1):
            try:
                with request.urlopen(req, timeout=300) as response:  # noqa: S310
                    return response.read().decode("utf-8")
            except HTTPError as exc:
                if (exc.code not in RETRYABLE_HTTP_STATUSES) or attempt == MAX_GEMINI_RETRIES:
                    raise

                delay = _compute_backoff_seconds(exc, attempt)
                logger.warning(
                    "Gemini request failed with HTTP %s. Retrying in %ss (attempt %s/%s).",
                    exc.code,
                    delay,
                    attempt,
                    MAX_GEMINI_RETRIES,
                )
                time.sleep(delay)
            except URLError:
                if attempt == MAX_GEMINI_RETRIES:
                    raise

                delay = 2 ** (attempt - 1)
                logger.warning(
                    "Gemini network error. Retrying in %ss (attempt %s/%s).",
                    delay,
                    attempt,
                    MAX_GEMINI_RETRIES,
                )
                time.sleep(delay)

        raise RuntimeError("Unreachable: Gemini retry loop exited unexpectedly")

    @staticmethod
    def _build_prompt(text: str, title_hint: str, chunk_index: int, total_chunks: int) -> str:
        schema_text = json.dumps(EXTRACTION_SCHEMA)
        return (
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
            "- If no items exist for any other section, return an empty array.\n\n"
            f"Meeting title: {title_hint}\n"
            f"Chunk: {chunk_index} of {total_chunks}\n"
            "Transcript:\n"
            f"{text}"
        )


def _extract_gemini_text(response_payload: dict[str, Any]) -> str:
    candidates = response_payload.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini response has no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("Gemini response has no content parts")

    text = str(parts[0].get("text", "")).strip()
    if not text:
        raise ValueError("Gemini response text is empty")
    return text


def _compute_backoff_seconds(exc: HTTPError, attempt: int) -> int:
    retry_after = _parse_retry_after_header(exc)
    if retry_after is not None:
        return retry_after
    return 2 ** (attempt - 1)


def _parse_retry_after_header(exc: HTTPError) -> int | None:
    headers = getattr(exc, "headers", None)
    if not headers:
        return None

    value = headers.get("Retry-After")
    if not value:
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
