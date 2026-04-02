from meeting_summary.openai_client import ActionItem, MeetingSummary
from meeting_summary.summarizer import render_markdown


def test_render_markdown():
    summary = MeetingSummary(
        title="Weekly Sync",
        overview="Discussed project status.",
        key_outcomes=["Aligned on priorities"],
        decisions=["Ship by Friday"],
        action_items=[ActionItem(owner="Alex", task="Update roadmap", due_date="2024-10-01")],
        risks=["Timeline tight"],
        open_questions=["Need final approval?"],
    )

    markdown = render_markdown(summary)
    assert "# Weekly Sync" in markdown
    assert "## Action Items" in markdown
    assert "- Update roadmap — Alex (Due: 2024-10-01)" in markdown
