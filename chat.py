"""Interactive CLI chat loop over an OpenAI-compatible endpoint.

The conversation history is kept in memory for the lifetime of the process and
re-sent to the model on every turn. The provider connection is established once
and the message list only ever grows (or is explicitly cleared) — the context is
**not** reloaded or restarted between turns, so the model always sees the full
dialogue.

Configuration (environment, loaded from a local ``.env`` when present):
    OPENAI_API_KEY       API key for the endpoint (most services require this).
    OPENAI_BASE_URL      OpenAI-compatible endpoint base URL, e.g.
                         ``http://localhost:8000/v1``. Alias: ``OPENAI_API_BASE``.
                         When unset the default is ``http://localhost:8000/v1``
                         (override with ``--base-url`` / env).
    OPENAI_MODEL         Model name, e.g. ``gpt-4o-mini``.
    OPENAI_MAX_TOKENS    Max output tokens per turn (default 4096).
    OPENAI_TEMPERATURE   Sampling temperature (default 0.7).
    OPENAI_TOP_P         Nucleus sampling bound (default 1.0).
    OPENAI_STREAM        Stream tokens when true (default true).
    CHAT_SYSTEM_PROMPT   Optional system prompt prepended to every conversation.

Run:
    python chat.py
    python chat.py --base-url http://localhost:8000/v1 --model gpt-4o-mini
    python chat.py --once "Hello, how are you?"
"""

from __future__ import annotations

import argparse
import logging
import os

try:  # GNU readline is Unix-only; Windows hosts may lack it entirely.
    import readline
except ImportError:  # pragma: no cover - platform dependent
    readline = None  # type: ignore[assignment]
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

# litellm is the LLM abstraction already used by the rest of this codebase
# (see server/providers/llm_provider.py). It speaks OpenAI-compatible endpoints
# natively through ``api_base`` with the ``openai/`` model prefix.
import litellm
from dotenv import load_dotenv

# Load a local .env (project convention; matches server/config/env.py).
load_dotenv()

logger = logging.getLogger("chat")

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 1.0

# litellm routes OpenAI-compatible endpoints when the model is prefixed with
# ``openai/`` and an ``api_base`` is supplied (see LLMProvider._build_completion_kwargs).
_OPENAI_PREFIX = "openai/"


@dataclass
class ChatConfig:
    """Resolved, immutable-in-practice configuration for a chat session."""

    api_key: str | None
    base_url: str
    model: str
    max_tokens: int
    temperature: float
    top_p: float
    stream: bool
    system_prompt: str

    @property
    def litellm_model(self) -> str:
        """Model name formatted for litellm's OpenAI-compatible routing.

        When a custom base URL is configured the model must be prefixed with
        ``openai/`` so litellm targets the openai provider against that
        endpoint. A model that already carries a provider prefix (e.g.
        ``openai/gpt-4o`` or ``ollama/...``) is left untouched.
        """
        if self.base_url and not self.model.startswith(("openai/", "ollama/", "http")):
            return f"{_OPENAI_PREFIX}{self.model}"
        return self.model

    @property
    def completion_kwargs(self) -> dict:
        kwargs: dict = {
            "model": self.litellm_model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs


@dataclass
class ChatSession:
    """Stateful chat session that holds the entire message history in memory.

    The ``messages`` list is never rebuilt from disk between turns — it only
    grows as the user and assistant exchange turns. This is what makes the
    loop "without reload": the model's context window is refreshed on each
    request using the same in-memory transcript, rather than re-opening a new
    conversation or re-loading any state from an external store.
    """

    config: ChatConfig
    messages: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.config.system_prompt:
            self.messages.append({"role": "system", "content": self.config.system_prompt})

    def reset(self) -> None:
        """Drop the transcript (keeps the session/connection alive, no reload)."""
        self.messages.clear()
        if self.config.system_prompt:
            self.messages.append({"role": "system", "content": self.config.system_prompt})

    def _stream_tokens(self, payload: dict[str, object]) -> Iterator[str]:
        """Yield assistant content deltas from a streamed litellm response.

        Each yielded value is a string fragment of the assistant message. The
        final ``[DONE]`` sentinel is emitted once the stream closes; callers
        use it to know the full response is complete. Non-recoverable errors
        are re-raised so the interactive loop can report them and continue.
        """
        response = litellm.completion(stream=True, **payload)  # type: ignore[arg-type]
        for chunk in response:
            try:
                choice = chunk.choices[0]
            except (IndexError, AttributeError):
                continue
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                yield content
            # Reasoning content (DeepSeek / o1-style) is surfaced too so the
            # user sees the model's chain-of-thought when available.
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield reasoning
            if getattr(choice, "finish_reason", None):
                break
        yield "[DONE]"

    def send(self, user_text: str) -> str:
        """Send a user turn and return the full assistant reply (non-streaming)."""
        self.messages.append({"role": "user", "content": user_text})
        payload: dict[str, object] = {
            "messages": self.messages,
            **self.config.completion_kwargs,
        }
        response = litellm.completion(**payload)  # type: ignore[arg-type]
        content: str = ""
        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError):
            content = ""
        self.messages.append({"role": "assistant", "content": content})
        return content

    def send_streaming(self, user_text: str) -> Iterator[str]:
        """Send a user turn, yielding assistant content as it streams.

        Yields string fragments of the assistant message, then ``[DONE]``.
        The user turn + assistant turn are appended to the in-memory history
        only once the stream has finished (so a torn-down request never
        leaves a half-appended, reloaded transcript behind).
        """
        self.messages.append({"role": "user", "content": user_text})
        payload: dict[str, object] = {
            "messages": self.messages,
            "stream": True,
            **self.config.completion_kwargs,
        }
        if self.config.stream:
            full_response = ""
            for fragment in self._stream_tokens(payload):
                if fragment == "[DONE]":
                    break
                full_response += fragment
                yield fragment
            self.messages.append({"role": "assistant", "content": full_response})
        else:
            for fragment in self._send_non_streaming_inline(payload):
                yield fragment

    def _send_non_streaming_inline(self, payload: dict[str, object]) -> Iterator[str]:
        """Non-streaming fallback used when streaming is disabled."""
        response = litellm.completion(**payload)  # type: ignore[arg-type]
        content = ""
        try:
            content = response.choices[0].message.content or ""
        except (IndexError, AttributeError):
            content = ""
        yield from content
        self.messages.append({"role": "assistant", "content": content})


def _resolve_env(override: str | None, env_key: str) -> str | None:
    """Pick the first non-empty value from an explicit override or the env."""
    if override:
        return override.strip()
    value = os.environ.get(env_key, "").strip()
    return value or None


def build_config(args: argparse.Namespace) -> ChatConfig:
    """Build a ChatConfig from CLI args, falling back to environment vars."""
    # OPENAI_API_BASE is the legacy alias still honoured by many tools.
    base_url = (
        _resolve_env(args.base_url, "OPENAI_BASE_URL")
        or _resolve_env(args.base_url, "OPENAI_API_BASE")
        or DEFAULT_BASE_URL
    )
    model = _resolve_env(args.model, "OPENAI_MODEL") or DEFAULT_MODEL
    api_key = _resolve_env(args.api_key, "OPENAI_API_KEY")

    def _env_int(key: str, default: int) -> int:
        raw = os.environ.get(key, "").strip()
        try:
            return int(raw) if raw else default
        except ValueError:
            return default

    def _env_float(key: str, default: float) -> float:
        raw = os.environ.get(key, "").strip()
        try:
            return float(raw) if raw else default
        except ValueError:
            return default

    stream = (
        args.stream
        if args.stream is not None
        else os.environ.get("OPENAI_STREAM", "true").strip().lower() in ("1", "true", "yes")
    )

    return ChatConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=args.max_tokens or _env_int("OPENAI_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        temperature=args.temperature
        if args.temperature is not None
        else _env_float("OPENAI_TEMPERATURE", DEFAULT_TEMPERATURE),
        top_p=args.top_p if args.top_p is not None else _env_float("OPENAI_TOP_P", DEFAULT_TOP_P),
        stream=stream,
        system_prompt=args.system_prompt or os.environ.get("CHAT_SYSTEM_PROMPT", ""),
    )


def _print_system(text: str, file: object = sys.stdout) -> None:
    """Write non-assistant text so it doesn't bleed into the streamed reply."""
    print(text, file=file, flush=True)


def _print_banner(cfg: ChatConfig) -> None:
    _print_system("=" * 64)
    _print_system(" Zenith chat — OpenAI-compatible endpoint")
    _print_system("-" * 64)
    _print_system(f"  endpoint : {cfg.base_url}")
    _print_system(f"  model    : {cfg.litellm_model}")
    _print_system(f"  stream   : {cfg.stream}")
    _print_system(
        f"  max_tokens: {cfg.max_tokens}  temperature: {cfg.temperature}  top_p: {cfg.top_p}"
    )
    _print_system("  history  : kept in-memory (no reload between turns)")
    _print_system("=" * 64)
    _print_system(
        "Type your message and press Enter. Commands: /help  /clear  /model <name>  /quit"
    )
    _print_system("")


def _print_help() -> None:
    _print_system(
        "Commands:\n"
        "  /help            Show this help.\n"
        "  /clear           Clear conversation history (connection stays open).\n"
        "  /model <name>    Switch the model for this session and future turns.\n"
        "  /quit, /exit, /q Quit the chat.\n"
        "Ctrl-C / Ctrl-D    Also quit."
    )


def _interactive_loop(session: ChatSession) -> None:
    """Read user input and stream replies until the user exits.

    The single ``ChatSession`` (and its in-memory transcript) lives for the
    whole loop, so context is never reloaded between turns — it's only ever
    appended to or, on ``/clear``, reset in place.
    """
    while True:
        try:
            line = input("▸ ")
        except (EOFError, KeyboardInterrupt):
            _print_system("\n[bye]")
            break
        if not line:
            continue
        stripped = line.strip()

        if stripped in ("/quit", "/exit", "/q"):
            _print_system("[bye]")
            break
        if stripped == "/help":
            _print_help()
            continue
        if stripped == "/clear":
            session.reset()
            _print_system("[conversation history cleared]")
            continue
        if stripped.startswith("/model"):
            parts = stripped.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                _print_system(f"current model: {session.config.litellm_model}")
            else:
                new_model = parts[1].strip()
                # Rebuild a config with the new model; keep everything else.
                session.config = ChatConfig(
                    api_key=session.config.api_key,
                    base_url=session.config.base_url,
                    model=new_model,
                    max_tokens=session.config.max_tokens,
                    temperature=session.config.temperature,
                    top_p=session.config.top_p,
                    stream=session.config.stream,
                    system_prompt=session.config.system_prompt,
                )
                _print_system(f"switched model -> {session.config.litellm_model}")
            continue
        if stripped.startswith("/"):
            _print_system(f"unknown command: {stripped}. Type /help for options.")
            continue

        # Stream the assistant's reply inline, token by token.
        try:
            for fragment in session.send_streaming(stripped):
                if fragment == "[DONE]":
                    continue
                # Write fragments as raw text to keep the stream contiguous.
                sys.stdout.write(fragment)
                sys.stdout.flush()
        except litellm.AuthenticationError:
            _print_system("\n[error] authentication failed — check OPENAI_API_KEY.")
        except litellm.RateLimitError:
            _print_system("\n[error] rate limited — try again shortly.")
        except litellm.APITimeoutError:
            _print_system("\n[error] request timed out — retry or check the endpoint.")
        except litellm.APIError as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            _print_system(f"\n[error] provider error ({status}): {exc}")
        except Exception as exc:
            logger.exception("unexpected error during chat turn")
            _print_system(f"\n[error] {exc!r}")
        finally:
            _print_system("")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chat",
        description="Interactive chat over an OpenAI-compatible endpoint.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible endpoint base URL "
        "(env: OPENAI_BASE_URL / OPENAI_API_BASE). "
        f"Default: {DEFAULT_BASE_URL}.",
    )
    parser.add_argument("--model", default=None, help="Model name (env: OPENAI_MODEL).")
    parser.add_argument("--api-key", default=None, help="API key (env: OPENAI_API_KEY).")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Max output tokens (env: OPENAI_MAX_TOKENS).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Temperature (env: OPENAI_TEMPERATURE).",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Top-p nucleus sampling (env: OPENAI_TOP_P).",
    )
    parser.add_argument(
        "--stream/--no-stream",
        dest="stream",
        default=None,
        help="Stream tokens as they arrive (env: OPENAI_STREAM).",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="System prompt (env: CHAT_SYSTEM_PROMPT).",
    )
    parser.add_argument(
        "--once",
        default=None,
        help="Run a single turn with this user message, print the reply, and exit.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = build_config(args)
    session = ChatSession(config=cfg)

    if args.once is not None:
        # Single-shot mode: one turn, one reply, then exit (still no reload).
        print("Assistant: ", end="", flush=True)
        for fragment in session.send_streaming(args.once):
            if fragment != "[DONE]":
                print(fragment, end="", flush=True)
        print()
        return 0

    _print_banner(cfg)
    _interactive_loop(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
