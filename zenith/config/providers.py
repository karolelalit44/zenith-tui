from pydantic import BaseModel, Field
from typing import Optional

from .env import require_int, require_float


class ProviderConfig(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = Field(
        default=require_int("ZENITH_MAX_TOKENS"), ge=1
    )
    temperature: float = Field(
        default=require_float("ZENITH_TEMPERATURE"), ge=0.0, le=2.0
    )
    is_active: bool = True
    enable_thinking: bool = False
    reasoning_budget: Optional[int] = None
