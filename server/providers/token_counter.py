from __future__ import annotations

import json
import logging
from typing import Any

from server.config.constants import CHARS_PER_TOKEN, SUMMARY_FRAMING_TOKENS

logger = logging.getLogger(__name__)
_REPLY_PRIMING = 2


def _encoding_name_for_model(model: str) -> str | None:
    try:
        from server.storage import load_catalog

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

    def count_message(self, msg: Any, model: str = "cl100k_base") -> int:
        """Tokens for one wire message: content, serialized tool calls, framing.

        ``tool_calls`` carries JSON arguments the provider bills as input, and
        for the mutating tools that is the entire payload (a whole file, a
        multi-file patch). Counting only ``content`` therefore under-reports
        occupancy by the size of every write the agent has made.

        Private bookkeeping keys the loop attaches to message dicts (``digest``,
        ``tool_name``, ``salvage_digest``, ``time``, ``is_digested``) are
        harness metadata and never reach the provider, so they are not counted.
        """
        if not isinstance(msg, dict):
            logger.warning("count_message skipping non-dict message: %s", type(msg).__name__)
            return 0
        total = self.count(_content_text(msg.get("content")), model)
        calls = msg.get("tool_calls")
        if isinstance(calls, list) and calls:
            try:
                total += self.count(json.dumps(calls, separators=(",", ":"), default=str), model)
            except (TypeError, ValueError):
                total += self.count(str(calls), model)
        return total + SUMMARY_FRAMING_TOKENS

    def count_messages(self, messages: list[dict], model: str = "cl100k_base") -> int:
        total = 0
        for msg in messages:
            total += self.count_message(msg, model)
        return total + _REPLY_PRIMING

    @staticmethod
    def _count_heuristic(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN)


def _content_text(content: Any) -> str:
    """Flatten wire ``content`` to the text the provider actually bills.

    Providers accept content as either a plain string or a list of typed parts.
    The list form must not be measured via ``str()``: its JSON scaffolding and
    part-type keys are not billed as the corresponding prose tokens would be,
    and it inflates the count on exactly the message shape that is already the
    largest (a long tool result). Passing the list straight to the encoder is
    worse still — it raises, and the heuristic fallback then divides the *part
    count* by the chars-per-token ratio, reporting a 4 000-character result as
    a handful of tokens.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "output_text"):
                    value = item.get(key)
                    if isinstance(value, str):
                        parts.append(value)
                        break
        return "\n".join(parts)
    return str(content)
