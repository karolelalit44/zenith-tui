from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from server.config.constants import CHARS_PER_TOKEN, SUMMARY_FRAMING_TOKENS

logger = logging.getLogger(__name__)
_REPLY_PRIMING = 2


@dataclass(frozen=True, slots=True)
class UsageAnchor:
    """Provider-reported occupancy of a prefix of the current message list.

    ``tokens`` is the provider's own count for the request whose message list
    ended at ``index``. Messages at or after ``index`` were not part of that
    request, so they must be estimated rather than folded into the anchor.

    ``aux_tokens`` records the tool-schema budget as it stood for that request,
    because the provider's count already includes it. Only the *increase* since
    the anchor is added on top; adding the current value again would bill the
    same schemas to the window twice.

    Cumulative per-turn usage is deliberately not an anchor: it bills every step
    of a turn against one number and describes no single message list.
    """

    index: int
    tokens: int
    aux_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ContextUsage:
    """Occupancy of one composed message list, plus where the number came from."""

    tokens: int
    source: Literal["provider", "estimated"]
    anchor_index: int | None = None


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

    def measure_messages(
        self,
        messages: list[dict],
        model: str = "cl100k_base",
        *,
        anchor: UsageAnchor | None = None,
        aux_tokens: int = 0,
    ) -> ContextUsage:
        """Occupancy of ``messages``, anchored on the provider when one exists.

        With an anchor, the provider's number is authoritative for the prefix it
        described and only the tail after it is estimated. Without one, the
        whole list is estimated. ``aux_tokens`` covers the request parts that are
        not messages at all — the tool-schema block — and is added in both cases
        so occupancy never reports a small number just because no step has
        completed yet. Under an anchor only its increase over the anchored value
        is added, since the anchored count already paid for what it contained.
        """
        aux = max(0, int(aux_tokens))
        if anchor is not None and anchor.tokens > 0 and 0 <= anchor.index <= len(messages):
            tail = sum(self.count_message(m, model) for m in messages[anchor.index :])
            return ContextUsage(
                tokens=anchor.tokens + tail + max(0, aux - anchor.aux_tokens),
                source="provider",
                anchor_index=anchor.index,
            )
        return ContextUsage(
            tokens=self.count_messages(messages, model) + aux,
            source="estimated",
            anchor_index=None,
        )

    @staticmethod
    def _count_heuristic(text: str) -> int:
        return max(1, len(text) // CHARS_PER_TOKEN)


def _content_text(content: Any) -> str:
    """Flatten wire ``content`` to the text the provider actually bills.

    Providers accept content as either a plain string or a list of typed parts.
    The list form must not be measured via ``str()``: its JSON scaffolding and
    part-type keys are not billed as the corresponding prose tokens would be,
    and it inflates the count on exactly the message shape that is already the
    largest (a long tool result).
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
