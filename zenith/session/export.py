"""Session exporter — export conversations as markdown files."""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime
from typing import Any

from zenith.core.session import Session
from zenith.core.message import Message
from zenith.core.events import Event


class SessionExporter:
    """Export session conversations as readable markdown files."""

    def export(
        self,
        session: Session,
        messages: list[Message],
        output_dir: str = "zenith_exports",
    ) -> str:
        """Export a session to a markdown file. Returns the file path."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r'[^\w\s-]', '', session.title)[:50].strip()
        safe_title = re.sub(r'\s+', '_', safe_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.md"
        filepath = output_path / filename

        lines = self._build_markdown(session, messages)
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return str(filepath)

    def export_to_string(
        self,
        session: Session,
        messages: list[Message],
    ) -> str:
        """Export a session as a markdown string (no file write)."""
        return "\n".join(self._build_markdown(session, messages))

    def _build_markdown(
        self,
        session: Session,
        messages: list[Message],
    ) -> list[str]:
        """Build markdown lines for a session."""
        lines = [
            f"# {session.title}",
            "",
            f"**Mode:** {session.mode}",
            f"**Created:** {session.created_at.isoformat() if isinstance(session.created_at, datetime) else session.created_at}",
            f"**Exported:** {datetime.now().isoformat()}",
            "",
            "---",
            "",
        ]

        for msg in messages:
            role_label = msg.role.title()
            lines.append(f"## {role_label}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")

            # Summarize events if present
            if msg.events:
                event_summary = self._summarize_events(msg.events)
                if event_summary:
                    lines.append("<details>")
                    lines.append("<summary>Events</summary>")
                    lines.append("")
                    for item in event_summary:
                        lines.append(f"- {item}")
                    lines.append("")
                    lines.append("</details>")
                    lines.append("")

        return lines

    def _summarize_events(self, events: list[Event]) -> list[str]:
        """Create a human-readable summary of events."""
        summaries = []
        for event in events:
            kind = event.kind.value
            data = event.data

            if kind == "thinking":
                summaries.append(f"**Thinking:** {data.get('text', '')}")
            elif kind == "message":
                if not data.get("partial"):
                    text = data.get("text", "")
                    if text:
                        summaries.append(f"**Response:** {text[:200]}...")
            elif kind == "error":
                summaries.append(f"**Error:** {data.get('message', '')}")
            elif kind == "success":
                summaries.append(f"**Success:** {data.get('message', '')}")
            elif kind == "tool_call":
                tool = data.get("tool", "")
                summaries.append(f"**Tool call:** `{tool}`")
            elif kind == "tool_result":
                tool = data.get("tool", "")
                success = data.get("success", False)
                path = data.get("metadata", {}).get("path", "")
                if path:
                    summaries.append(f"**Tool result:** `{tool}` → `{path}` ({'ok' if success else 'failed'})")
                else:
                    summaries.append(f"**Tool result:** `{tool}` ({'ok' if success else 'failed'})")
            elif kind == "warning":
                summaries.append(f"**Warning:** {data.get('message', '')}")

        return summaries
