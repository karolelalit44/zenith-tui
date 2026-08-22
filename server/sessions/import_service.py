from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from server.domain.domain import ScenarioMode, SessionState
from server.domain.events import Event, EventKind
from server.domain.message import Message
from server.domain.session import Session
from server.persistence.repositories.sessions import MessageRepository, SessionRepository


class SessionImporter:
    def __init__(self, session_repo: SessionRepository, message_repo: MessageRepository):
        self.session_repo = session_repo
        self.message_repo = message_repo

    async def import_from_jsonl(self, file_path: str | Path) -> tuple[Session, list[Message]]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"JSONL import file not found: {file_path}")

        lines = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        if not lines:
            raise ValueError(f"Empty JSONL file: {file_path}")

        session_obj: Session | None = None
        messages: list[Message] = []

        for line_idx, line in enumerate(lines, 1):
            try:
                record = json.loads(line)
            except Exception as e:
                raise ValueError(f"Invalid JSON at line {line_idx}: {e}") from e

            rec_type = record.get("type")
            if rec_type == "session":
                created_at = (
                    datetime.fromisoformat(record["created_at"])
                    if "created_at" in record
                    else datetime.now()
                )
                updated_at = (
                    datetime.fromisoformat(record["updated_at"])
                    if "updated_at" in record
                    else datetime.now()
                )
                mode_val = record.get("mode", "build")
                try:
                    mode = ScenarioMode(mode_val)
                except ValueError:
                    mode = ScenarioMode.BUILD

                session_obj = Session(
                    id=record["id"],
                    title=record.get("title", "Imported Session"),
                    mode=mode,
                    state=SessionState.CREATED,
                    created_at=created_at,
                    updated_at=updated_at,
                    model=record.get("model"),
                    provider=record.get("provider"),
                    total_tokens=record.get("total_tokens", 0),
                    metadata=record.get("metadata", {}),
                )
            elif rec_type == "message":
                if session_obj is None:
                    raise ValueError("Message record found before session header in JSONL")

                events = []
                for ev_dict in record.get("events", []):
                    kind_str = ev_dict.get("kind", "message")
                    try:
                        kind = EventKind(kind_str)
                    except ValueError:
                        kind = EventKind.MESSAGE
                    events.append(
                        Event(
                            kind=kind,
                            data=ev_dict.get("data", {}),
                            session_id=session_obj.id,
                        )
                    )

                created_at = (
                    datetime.fromisoformat(record["created_at"])
                    if "created_at" in record
                    else datetime.now()
                )
                messages.append(
                    Message(
                        id=record.get("id"),
                        session_id=session_obj.id,
                        role=record.get("role", "user"),
                        content=record.get("content", ""),
                        events=events,
                        token_count=record.get("token_count", 0),
                        created_at=created_at,
                    )
                )

        if session_obj is None:
            raise ValueError("No session record found in JSONL file")

        # Persist session and messages into database. Re-importing an export of
        # the same session must not duplicate its messages: skip records whose
        # ids are already persisted (and duplicates within the file itself).
        existing = await self.session_repo.get(session_obj.id)
        if existing is None:
            await self.session_repo.create(session_obj)

        existing_ids: set[str] = set()
        if existing is not None:
            try:
                existing_msgs = await self.message_repo.get_by_session(existing.id)
                existing_ids = {m.id for m in existing_msgs}
            except Exception:
                existing_ids = set()

        imported: list[Message] = []
        seen_in_file: set[str] = set()
        for msg in messages:
            if msg.id is not None:
                if msg.id in existing_ids or msg.id in seen_in_file:
                    continue
                seen_in_file.add(msg.id)
            await self.message_repo.append(msg)
            imported.append(msg)

        return session_obj, imported
