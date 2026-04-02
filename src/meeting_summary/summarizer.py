from __future__ import annotations

from .openai_client import MeetingSummary


def render_markdown(summary: MeetingSummary) -> str:
    lines: list[str] = []
    lines.append(f"# {summary.title}")
    lines.append("")
    lines.append("## Overview")
    lines.append(summary.overview or "(No overview provided.)")

    lines.append("")
    lines.append("## Key Outcomes")
    lines.extend(_render_list(summary.key_outcomes))

    lines.append("")
    lines.append("## Decisions")
    lines.extend(_render_list(summary.decisions))

    lines.append("")
    lines.append("## Action Items")
    if summary.action_items:
        for item in summary.action_items:
            owner = item.owner or "Unassigned"
            due = f" (Due: {item.due_date})" if item.due_date else ""
            lines.append(f"- {item.task} — {owner}{due}")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Risks")
    lines.extend(_render_list(summary.risks))

    lines.append("")
    lines.append("## Open Questions")
    lines.extend(_render_list(summary.open_questions))

    lines.append("")
    return "\n".join(lines)


def _render_list(items: list[str]) -> list[str]:
    if not items:
        return ["- None"]
    return [f"- {item}" for item in items]
