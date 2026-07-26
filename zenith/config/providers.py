from pydantic import BaseModel, Field
from typing import Optional

from .env import optional_int, optional_float


class ProviderConfig(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = Field(
        default=optional_int("ZENITH_MAX_TOKENS", 16384), ge=1
    )
    temperature: float = Field(
        default=optional_float("ZENITH_TEMPERATURE", 0.7), ge=0.0, le=2.0
    )
    is_active: bool = True
    enable_thinking: bool = False
    reasoning_budget: Optional[int] = None
