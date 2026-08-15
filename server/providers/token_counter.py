from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
_FRAMING_PER_MESSAGE = 4
_REPLY_PRIMING = 2


def _encoding_name_for_model(model: str) -> str | None:
    try:
        from server.persistence.repositories import load_catalog

        catalog = load_catalog()
        for prov in catalog.get("providers", {}).values():
            for m in prov.get("models", []):
                if m.get("id") == model:
                    tokenizer = m.get("tokenizer") or ""
                    return tokenizer or None
    except Exception:
        logger.debug("Failed to resolve tokenizer from catalog for %s", model)
    return None


class TokenCounter:
    def __init__(self) -> None:
        self._encodings: dict[str, Any] = {}
        self._available: bool = True
        try:
            from importlib.util import find_spec

            if not find_spec("tiktoken"):
                self._available = False
        except ImportError:
            self._available = False
            logger.warning("tiktoken not installed; using heuristic fallback for token counting")

    def _resolve_encoding_name(self, model: str) -> str:
        return _encoding_name_for_model(model) or "cl100k_base"

    def _get_encoding(self, model: str) -> Any:
        if not self._available:
            return None
        if model not in self._encodings:
            enc_name = self._resolve_encoding_name(model)
            try:
                import tiktoken

                self._encodings[model] = tiktoken.get_encoding(enc_name)
            except Exception:
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
                        return None
        return self._encodings[model]

    def count(self, text: str, model: str = "cl100k_base") -> int:
        if not text:
            return 0
        if not self._available:
            return self._count_heuristic(text)
        enc = self._get_encoding(model)
        if enc is None:
            return self._count_heuristic(text)
        try:
            return len(enc.encode(text))
        except Exception:
            return self._count_heuristic(text)

    def count_messages(self, messages: list[dict], model: str = "cl100k_base") -> int:
        total = 0
        for msg in messages:
            if not isinstance(msg, dict):
                logger.warning("count_messages skipping non-dict message: %s", type(msg).__name__)
                continue
            total += self.count(msg.get("content", ""), model)
            total += _FRAMING_PER_MESSAGE
        total += _REPLY_PRIMING
        return total

    @staticmethod
    def _count_heuristic(text: str) -> int:
        return max(1, len(text) // 4)
