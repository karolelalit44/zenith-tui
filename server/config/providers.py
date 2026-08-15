from pydantic import BaseModel

from server.config.constants import DEFAULT_LLM_MAX_TOKENS, DEFAULT_LLM_TEMPERATURE


class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int = DEFAULT_LLM_MAX_TOKENS
    temperature: float = DEFAULT_LLM_TEMPERATURE
    is_active: bool = True
    enable_thinking: bool = False
    reasoning_budget: int | None = None
