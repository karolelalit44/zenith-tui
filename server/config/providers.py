from pydantic import BaseModel


class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    is_active: bool = True
    enable_thinking: bool = False
    reasoning_budget: int | None = None
