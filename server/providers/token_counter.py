from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MODEL_ENCODING_OVERRIDES: dict[str, str] = {
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "o1": "o200k_base",
    "o3": "o200k_base",
    "o3-mini": "o200k_base",
    "o4-mini": "o200k_base",
    "claude": "cl100k_base",
    "claude-3": "cl100k_base",
    "claude-3.5": "cl100k_base",
    "llama": "cl100k_base",
    "gemini": "cl100k_base",
    "mistral": "cl100k_base",
    "codellama": "cl100k_base",
}

_FRAMING_PER_MESSAGE = 4
_REPLY_PRIMING = 2


class TokenCounter:
    def __init__(self) -> None:
        self._encodings: dict[str, object] = {}
        self._available: bool = True
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            self._available = False
            logger.warning("tiktoken not installed; using heuristic fallback for token counting")

    def _resolve_encoding_name(self, model: str) -> str:
        model_lower = model.lower().strip()
        for prefix, enc in _MODEL_ENCODING_OVERRIDES.items():
            if model_lower.startswith(prefix):
                return enc
        if "cl100k" in model_lower or "gpt-4" in model_lower or "gpt-3" in model_lower:
            return "cl100k_base"
        if "o200k" in model_lower or "o1" in model_lower or "o3" in model_lower or "o4" in model_lower:
            return "o200k_base"
        return "cl100k_base"

    def _get_encoding(self, model: str) -> object:
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
            total += self.count(msg.get("content", ""), model)
            total += _FRAMING_PER_MESSAGE
        total += _REPLY_PRIMING
        return total

    def fallback_usage(self, prompt: str, completion: str, model: str) -> tuple[int, int]:
        """Fallback token count when provider returns zero/invalid usage."""
        inp = self.count(prompt, model) if prompt else 0
        out = self.count(completion, model) if completion else 0
        return inp, out

    @staticmethod
    def _count_heuristic(text: str) -> int:
        return max(1, len(text) // 4)
