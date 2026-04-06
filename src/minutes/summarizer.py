from __future__ import annotations

from .summary_schema import MeetingSummary


def render_markdown(summary: MeetingSummary) -> str:
    lines: list[str] = []
    lines.append(f"# {summary.title}")
    lines.append("")
    lines.append("## Overview")
    lines.extend(_render_list(summary.overview))

    lines.append("")
    lines.append("## Key Findings")
    lines.extend(_render_list(summary.key_findings))

    lines.append("")
    lines.append("## Todos")
    if summary.todos:
        for item in summary.todos:
            owner = f" — {item.owner}" if item.owner else ""
            due = f" (Due: {item.due_date})" if item.due_date else ""
            lines.append(f"- {item.task}{owner}{due}")
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
