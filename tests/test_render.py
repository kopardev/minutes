from meeting_summary.summary_schema import ActionItem, MeetingSummary
from meeting_summary.summarizer import render_markdown


def test_render_markdown():
    summary = MeetingSummary(
        title="Weekly Sync",
        overview=["Discussed project status."],
        key_findings=["Ship by Friday"],
        todos=[ActionItem(owner="Alex", task="Update roadmap", due_date="2024-10-01")],
    )

    markdown = render_markdown(summary)
    assert "# Weekly Sync" in markdown
    assert "## Key Findings" in markdown
    assert "## Todos" in markdown
    assert "- Update roadmap — Alex (Due: 2024-10-01)" in markdown
