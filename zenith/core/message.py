import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

from .events import Event


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str
    content: str = ""
    events: list[Event] = Field(default_factory=list)
    token_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
