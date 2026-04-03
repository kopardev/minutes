from meeting_summary.summary_schema import MeetingSummary, parse_llm_response, split_transcript
from meeting_summary.summarizer import render_markdown


def test_split_transcript_single_chunk() -> None:
    text = "short transcript"
    chunks = split_transcript(text, chunk_size=100)
    assert chunks == ["short transcript"]


def test_split_transcript_multiple_chunks_with_overlap() -> None:
    text = "A" * 250
    chunks = split_transcript(text, chunk_size=100, overlap=10)
    assert len(chunks) == 3
    assert len(chunks[0]) == 100
    assert len(chunks[1]) == 100
    assert len(chunks[2]) == 70


def test_parse_llm_response_concise_fields() -> None:
    data = {
        "overview": ["Weekly project sync."],
        "key_findings": [
            "Will use vCenter instead of port forwarding",
            "Onboarding checklist being created",
        ],
        "todos": [
            {"owner": "Vishal", "task": "Create intern onboarding checklist", "due_date": None},
        ],
        "risks": ["Access restrictions may delay setup"],
        "open_questions": ["When does intern onboarding start?"],
    }
    summary = parse_llm_response(data, "Project progress")
    assert "Weekly project sync." in summary.overview
    assert any("vCenter" in x for x in summary.key_findings)
    assert len(summary.todos) == 1
    assert summary.risks == ["Access restrictions may delay setup"]
    assert summary.open_questions == ["When does intern onboarding start?"]


def test_render_markdown_with_concise_sections() -> None:
    summary = MeetingSummary(
        title="Deep Dive",
        overview=["Comprehensive extraction."],
        key_findings=["Migration script completed"],
        risks=["Release might slip if review is delayed"],
        open_questions=["Who approves deployment?"],
    )
    markdown = render_markdown(summary)
    assert "## Key Findings" in markdown
    assert "- Migration script completed" in markdown
    assert "## Todos" in markdown
    assert "## Risks" in markdown
    assert "## Open Questions" in markdown
