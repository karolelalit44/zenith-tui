import uuid
from pydantic import BaseModel, Field
from datetime import datetime


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Session"
    mode: str = "build"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    workspace_root: str = "."
    is_active: bool = True
    metadata: dict = Field(default_factory=dict)
