from pydantic import BaseModel, Field
from typing import Optional


class ProviderConfig(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4"
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    is_active: bool = True
