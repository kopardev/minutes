from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI
from .summary_schema import (
    EXTRACTION_SCHEMA,
    MeetingSummary,
    _json_from_text,
    parse_llm_response,
    split_transcript,
)


logger = logging.getLogger(__name__)


class OpenAISummarizer:
    def __init__(self, model: str, use_chunks: bool = False):
        self._client = OpenAI()
        self._model = model
        self._use_chunks = use_chunks

    def summarize(self, transcript_text: str, title_hint: str) -> MeetingSummary:
        source_text = transcript_text.strip()
        if not source_text:
            return MeetingSummary(title=title_hint, overview=["Transcript was empty."])

        chunks = split_transcript(source_text) if self._use_chunks else [source_text]

        logger.info("OpenAI: %s chunk(s) to process for '%s'", len(chunks), title_hint)

        schema_text = json.dumps(EXTRACTION_SCHEMA)
        system = (
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

        if len(chunks) == 1:
            logger.info("OpenAI: chunk 1/1 sending to API")
            user_content = json.dumps({
                "meeting_title": title_hint,
                "output_schema": EXTRACTION_SCHEMA,
                "transcript": chunks[0],
            })
        else:
            partials: list[str] = []
            for index, chunk in enumerate(chunks, start=1):
                logger.info("OpenAI: chunk %s/%s sending to API", index, len(chunks))
                resp = self._client.responses.create(
                    model=self._model,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps({
                            "meeting_title": title_hint,
                            "chunk": f"{index} of {len(chunks)}",
                            "output_schema": EXTRACTION_SCHEMA,
                            "transcript": chunk,
                        })},
                    ],
                )
                logger.info("OpenAI: chunk %s/%s received", index, len(chunks))
                partials.append(resp.output_text)
            logger.info("OpenAI: consolidating %s chunk summaries", len(chunks))
            user_content = json.dumps({
                "meeting_title": title_hint,
                "output_schema": EXTRACTION_SCHEMA,
                "transcript": "\n\n".join(partials),
            })

        logger.info("OpenAI: sending final extraction request")
        response = self._client.responses.create(
            model=self._model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        logger.info("OpenAI: final extraction response received")
        data = _json_from_text(response.output_text)
        return parse_llm_response(data, title_hint)


