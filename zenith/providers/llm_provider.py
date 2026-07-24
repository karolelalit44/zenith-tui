import logging
from typing import AsyncIterator

from .base import BaseProvider
from .adapters import get_adapter
from zenith.core.errors import ProviderError

logger = logging.getLogger(__name__)


class LLMProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        model: str = "gpt-4",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        enable_thinking: bool = False,
        reasoning_budget: int | None = None,
    ):
        super().__init__(name, model, max_tokens, temperature)
        self.api_key = api_key.strip() if api_key else None
        self.base_url = base_url.strip() if base_url else None
        self.enable_thinking = enable_thinking
        self.reasoning_budget = reasoning_budget

    def _build_adapter(self):
        adapter_cls = get_adapter(self.name)

        extra_headers = None
        if self.name == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://github.com/anomalyco/zenith",
                "X-Title": "Zenith AI Coding Assistant",
            }

        base = self.base_url
        if not base and self.name == "nvidia":
            base = "https://integrate.api.nvidia.com/v1"

        if adapter_cls.__name__ == "NVIDIAAdapter":
            return adapter_cls(
                model=self.model,
                api_key=self.api_key,
                base_url=base,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                enable_thinking=self.enable_thinking,
                reasoning_budget=self.reasoning_budget,
            )

        return adapter_cls(
            model=self.model,
            api_key=self.api_key,
            base_url=base,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            extra_headers=extra_headers,
        )

    async def complete(self, messages: list[dict]) -> str:
        try:
            adapter = self._build_adapter()
            return await adapter.complete(messages)
        except ImportError as e:
            if "litellm" in str(e):
                raise ProviderError(
                    "litellm not installed. Run: pip install 'zenith[llm]'",
                    provider=self.name,
                    recoverable=False,
                ) from e
            raise ProviderError(str(e), provider=self.name) from e
        except Exception as e:
            raise ProviderError(str(e), provider=self.name) from e

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            adapter = self._build_adapter()
            async for chunk in adapter.stream(messages):
                if chunk.content:
                    yield chunk.content
        except ImportError as e:
            if "litellm" in str(e):
                raise ProviderError(
                    "litellm not installed. Run: pip install 'zenith[llm]'",
                    provider=self.name,
                    recoverable=False,
                ) from e
            raise ProviderError(str(e), provider=self.name) from e
        except Exception as e:
            raise ProviderError(str(e), provider=self.name) from e

    async def validate(self) -> bool:
        try:
            await self.complete([{"role": "user", "content": "Say OK"}])
            return True
        except Exception as e:
            logger.warning("Provider '%s' validate() failed: %s", self.name, e)
            return False

    async def list_models(self) -> list[str]:
        import sqlite3
        from pathlib import Path
        db_path = "zenith.db"
        try:
            if Path(db_path).exists():
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM provider_models WHERE provider_id = ?", (self.name,))
                rows = cursor.fetchall()
                conn.close()
                if rows:
                    return [r[0] for r in rows]
        except Exception as e:
            logger.warning("Could not list models from DB for provider '%s': %s", self.name, e)
        return [self.model]
