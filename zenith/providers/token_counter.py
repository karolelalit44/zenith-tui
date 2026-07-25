"""Token counting with tiktoken (with fallback for missing models)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TokenCounter:
    """Count tokens using tiktoken with automatic encoding lookup and fallback."""

    def __init__(self) -> None:
        self._encodings: dict[str, object] = {}
        self._available: bool = True
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            self._available = False
            logger.warning("tiktoken not installed; using heuristic fallback for token counting")

    def _get_encoding(self, model: str) -> object:
        if not self._available:
            return None  # type: ignore[return-value]

        if model not in self._encodings:
            try:
                import tiktoken

                self._encodings[model] = tiktoken.encoding_for_model(model)
            except (KeyError, Exception):
                try:
                    import tiktoken

                    self._encodings[model] = tiktoken.get_encoding("cl100k_base")
                except Exception:
                    logger.debug("Failed to load tiktoken encoding for model %s", model)
                    self._available = False
                    return None  # type: ignore[return-value]
        return self._encodings[model]

    def count(self, text: str, model: str = "cl100k_base") -> int:
        """Count tokens in a text string."""
        if not self._available:
            return self._count_heuristic(text)

        enc = self._get_encoding(model)
        if enc is None:
            return self._count_heuristic(text)

        try:
            return len(enc.encode(text))  # type: ignore[union-attr]
        except Exception:
            return self._count_heuristic(text)

    def count_messages(self, messages: list[dict], model: str = "cl100k_base") -> int:
        """Count tokens across a list of chat messages (with message framing)."""
        total = 0
        for msg in messages:
            total += self.count(msg.get("content", ""), model)
            total += 4  # message framing tokens (<|start|>, role, \n, <|end|>)
        total += 2  # reply priming tokens (<|start|>assistant\n)
        return total

    @staticmethod
    def _count_heuristic(text: str) -> int:
        """Heuristic token count: ~4 chars per token for English text."""
        return max(1, len(text) // 4)
