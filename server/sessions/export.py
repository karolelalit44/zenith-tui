from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from server.domain.events import Event
from server.domain.message import Message
from server.domain.session import Session


class SessionExporter:
    def export(
        self, session: Session, messages: list[Message], output_dir: str = "zenith_exports"
    ) -> str:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", session.title)[:50].strip()
        safe_title = re.sub(r"\s+", "_", safe_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.md"
        filepath = output_path / filename
        lines = self._build_markdown(session, messages)
        filepath.write_text("\n".join(lines), encoding="utf-8")
        return str(filepath)

    def export_to_string(self, session: Session, messages: list[Message]) -> str:
        return "\n".join(self._build_markdown(session, messages))

    def export_jsonl(
        self, session: Session, messages: list[Message], output_dir: str = "zenith_exports"
    ) -> str:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", session.title)[:50].strip()
        safe_title = re.sub(r"\s+", "_", safe_title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_title}_{timestamp}.jsonl"
        filepath = output_path / filename
        content = self.export_jsonl_string(session, messages)
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def export_jsonl_string(self, session: Session, messages: list[Message]) -> str:
        lines: list[str] = []
        created_str = (
            session.created_at.isoformat()
            if isinstance(session.created_at, datetime)
            else str(session.created_at)
        )
        updated_str = (
            session.updated_at.isoformat()
            if isinstance(session.updated_at, datetime)
            else str(session.updated_at)
        )
        session_header = {
            "type": "session",
            "id": session.id,
            "title": session.title,
            "mode": getattr(session.mode, "value", str(session.mode)),
            "created_at": created_str,
            "updated_at": updated_str,
            "model": session.model,
            "provider": session.provider,
            "total_tokens": session.total_tokens,
            "metadata": session.metadata,
        }
        lines.append(json.dumps(session_header))
        for msg in messages:
            msg_created = (
                msg.created_at.isoformat()
                if isinstance(msg.created_at, datetime)
                else str(msg.created_at)
            )
            msg_data = {
                "type": "message",
                "id": msg.id,
                "session_id": msg.session_id,
                "role": msg.role,
                "content": msg.content,
                "token_count": msg.token_count,
                "created_at": msg_created,
                "events": [
                    ev.to_dict() if hasattr(ev, "to_dict") else vars(ev) for ev in msg.events
                ]
                if msg.events
                else [],
            }
            lines.append(json.dumps(msg_data))
        return "\n".join(lines)

    def _build_markdown(self, session: Session, messages: list[Message]) -> list[str]:
        lines = [
            f"# {session.title}",
            "",
            f"**Mode:** {session.mode}",
            f"**Created:** {(session.created_at.isoformat() if isinstance(session.created_at, datetime) else session.created_at)}",
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
                    summaries.append(
                        f"**Tool result:** `{tool}` → `{path}` ({('ok' if success else 'failed')})"
                    )
                else:
                    summaries.append(
                        f"**Tool result:** `{tool}` ({('ok' if success else 'failed')})"
                    )
            elif kind == "warning":
                summaries.append(f"**Warning:** {data.get('message', '')}")
        return summaries
