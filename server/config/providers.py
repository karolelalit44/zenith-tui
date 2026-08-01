
from pydantic import BaseModel, Field

from .env import optional_float, optional_int


class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int = Field(
        default=optional_int("ZENITH_MAX_TOKENS", 16384), ge=1
    )
    temperature: float = Field(
        default=optional_float("ZENITH_TEMPERATURE", 0.7), ge=0.0, le=2.0
    )
    is_active: bool = True
    enable_thinking: bool = False
    reasoning_budget: int | None = None
