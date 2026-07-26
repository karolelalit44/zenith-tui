from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseProvider(ABC):
    def __init__(self, name: str, model: str, max_tokens: int = 4096, temperature: float = 0.7):
        self.name = name
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        ...

    @abstractmethod
    async def stream(self, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def validate(self) -> bool:
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        ...
