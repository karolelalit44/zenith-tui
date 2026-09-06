from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from server.config.constants import ANSI_RE

# ANSI Escape Sequences
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Standard Foreground Colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

# Bright Foreground Colors
BRIGHT_BLACK = "\033[90m"  # Gray / Dim
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

LEVEL_COLORS: dict[str, str] = {
    "DEBUG": BRIGHT_BLACK,
    "INFO": BRIGHT_GREEN,
    "WARNING": BRIGHT_YELLOW,
    "ERROR": BRIGHT_RED,
    "CRITICAL": "\033[1;41;97m",
}

ROLE_COLORS: dict[str, str] = {
    "system": BRIGHT_MAGENTA,
    "user": BRIGHT_GREEN,
    "assistant": BRIGHT_YELLOW,
    "tool": BRIGHT_BLUE,
}


def _clamp_single_line(text: str, max_chars: int = 120) -> str:
    """Collapse to one line and hard-clamp its width.

    Prevents wide tool descriptions from exceeding terminal line width, which
    on Windows (CRLF) makes subsequent lines visually overwrite earlier ones.
    """
    if not text:
        return text
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1].rstrip() + "…"

# Operational patterns to highlight in INFO logs so critical milestones stand out
EXACT_HIGHLIGHTS: dict[str, str] = {
    "PROMPT.RECEIVED": f"{BOLD}{BRIGHT_CYAN}PROMPT.RECEIVED{RESET}",
    "PROMPT.RESOLVED": f"{BOLD}{CYAN}PROMPT.RESOLVED{RESET}",
    "_execute START": f"{BOLD}{BRIGHT_MAGENTA}_execute START{RESET}",
    "API CALL": f"{BOLD}{BRIGHT_CYAN}API CALL{RESET}",
    "API RESPONSE": f"{BOLD}{BRIGHT_GREEN}API RESPONSE{RESET}",
    "API STREAM OPENED": f"{BOLD}{BRIGHT_BLUE}API STREAM OPENED{RESET}",
    "API FIRST CHUNK": f"{DIM}{BRIGHT_CYAN}API FIRST CHUNK{RESET}",
    "[TOOL CALL]": f"{BOLD}{BRIGHT_YELLOW}[TOOL CALL]{RESET}",
    "[TOOL RESULT]": f"{BOLD}{BRIGHT_BLUE}[TOOL RESULT]{RESET}",
    "[ASSISTANT MESSAGE]": f"{BOLD}{BRIGHT_WHITE}[ASSISTANT MESSAGE]{RESET}",
    "[THINKING]": f"{DIM}{BRIGHT_MAGENTA}[THINKING]{RESET}",
}
_INJECTED_ATTACHMENT_RE = re.compile(r"\bInjected (\d+) attachment block\(s\)")
_INJECTED_ATTACHMENT_REPL = f"{BOLD}{BRIGHT_YELLOW}Injected \\1 attachment block(s){RESET}"


def highlight_info_message(msg: str) -> str:
    for target, replacement in EXACT_HIGHLIGHTS.items():
        if target in msg:
            msg = msg.replace(target, replacement)
    if "Injected " in msg and "attachment block" in msg:
        msg = _INJECTED_ATTACHMENT_RE.sub(_INJECTED_ATTACHMENT_REPL, msg)
    return msg


class ColoredFormatter(logging.Formatter):
    """Console formatter with smart semantic coloring:

    - DEBUG: dim gray throughout (low priority, easy to ignore)
    - INFO: green level tag, cyan logger, with highlighted operational keywords
    - WARNING: bold yellow level tag, yellow message (attention needed)
    - ERROR: bold red level tag, bright red message, red traceback (critical)
    - CRITICAL: white-on-red badge, bright red message
    """

    def format(self, record: logging.LogRecord) -> str:
        orig_levelname = record.levelname
        orig_name = record.name
        orig_msg = record.msg

        try:
            if record.levelno == logging.DEBUG:
                record.levelname = f"{DIM}{BRIGHT_BLACK}{record.levelname:<7}{RESET}"
                record.name = f"{DIM}{BRIGHT_BLACK}{record.name}{RESET}"
                if isinstance(record.msg, str) and "\033[" not in record.msg:
                    record.msg = f"{DIM}{BRIGHT_BLACK}{record.msg}{RESET}"
                return super().format(record)

            if record.levelno == logging.WARNING:
                record.levelname = f"{BOLD}{BRIGHT_YELLOW}{record.levelname:<7}{RESET}"
                record.name = f"{BRIGHT_CYAN}{record.name}{RESET}"
                if isinstance(record.msg, str) and "\033[" not in record.msg:
                    record.msg = f"{BRIGHT_YELLOW}{record.msg}{RESET}"
                return super().format(record)

            if record.levelno >= logging.ERROR:
                badge_style = (
                    "\033[1;41;97m" if record.levelno >= logging.CRITICAL else f"{BOLD}{BRIGHT_RED}"
                )
                record.levelname = f"{badge_style}{record.levelname:<7}{RESET}"
                record.name = f"{BRIGHT_CYAN}{record.name}{RESET}"
                if isinstance(record.msg, str) and "\033[" not in record.msg:
                    record.msg = f"{BOLD}{BRIGHT_RED}{record.msg}{RESET}"
                return super().format(record)

            # INFO level
            record.levelname = f"{BRIGHT_GREEN}{record.levelname:<7}{RESET}"
            record.name = f"{BRIGHT_CYAN}{record.name}{RESET}"
            if isinstance(record.msg, str) and "\033[" not in record.msg:
                record.msg = highlight_info_message(record.msg)

            return super().format(record)
        finally:
            record.levelname = orig_levelname
            record.name = orig_name
            record.msg = orig_msg

    def formatException(self, ei: Any) -> str:
        s = super().formatException(ei)
        return f"{BRIGHT_RED}{s}{RESET}"


class PlainFileFormatter(logging.Formatter):
    """File formatter stripping all ANSI escape codes to ensure clean file logs."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return ANSI_RE.sub("", formatted)


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler ensuring unicode strings never raise UnicodeEncodeError on Windows."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                msg = self.format(record)
                stream = self.stream
                encoding = getattr(stream, "encoding", "utf-8") or "utf-8"
                safe_msg = msg.encode(encoding, errors="replace").decode(encoding)
                stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type is not None and issubclass(exc_type, (ValueError, OSError)):
            msg = str(exc_val or "").lower()
            if "closed" in msg or "i/o operation on closed file" in msg:
                return
        super().handleError(record)


def format_model_payload(
    kwargs: dict[str, Any],
    call_type: str = "stream",
    max_chars_per_msg: int | None = None,
) -> str:
    """Format the exact outbound LLM payload for terminal/console inspection."""
    if not isinstance(kwargs, dict):
        kwargs = {}
    model = kwargs.get("model", "unknown")
    messages: list[dict[str, Any]] = kwargs.get("messages") or []
    tools: list[dict[str, Any]] = kwargs.get("tools") or []
    temp = kwargs.get("temperature")
    max_tok = kwargs.get("max_tokens")
    tool_choice = kwargs.get("tool_choice")

    if max_chars_per_msg is None:
        if os.getenv("ZENITH_LOG_FULL_PAYLOAD", "0").lower() in ("1", "true", "yes"):
            max_chars_per_msg = 0
        else:
            try:
                max_chars_per_msg = int(os.getenv("ZENITH_LOG_PAYLOAD_MAX_CHARS", "50000"))
            except ValueError:
                max_chars_per_msg = 50000

    banner_w = 88
    div_double = f"{BRIGHT_CYAN}{'═' * banner_w}{RESET}"
    div_single = f"{BRIGHT_BLACK}{'─' * banner_w}{RESET}"

    lines: list[str] = [
        "",
        div_double,
        f"{BOLD}{BRIGHT_CYAN}>>> LLM OUTBOUND PAYLOAD [{call_type}]{RESET} {BOLD}model={model}{RESET}",
        (
            f"    {BRIGHT_BLACK}Messages:{RESET} {BOLD}{len(messages)}{RESET} | "
            f"{BRIGHT_BLACK}Tools:{RESET} {BOLD}{len(tools)}{RESET} | "
            f"{BRIGHT_BLACK}Temp:{RESET} {temp} | "
            f"{BRIGHT_BLACK}MaxTokens:{RESET} {max_tok} | "
            f"{BRIGHT_BLACK}ToolChoice:{RESET} {tool_choice}"
        ),
        div_single,
    ]

    total_msgs = len(messages)
    for idx, msg in enumerate(messages):
        is_final = idx == total_msgs - 1
        if not isinstance(msg, dict):
            lines.append(f"  {BRIGHT_BLACK}[MSG {idx + 1}/{total_msgs}]{RESET} {msg}")
            continue

        raw_role = str(msg.get("role") or "unknown").lower()
        role_color = ROLE_COLORS.get(raw_role, BRIGHT_WHITE)
        role_badge = f"{role_color}[{raw_role.upper()}]{RESET}"

        raw_content = msg.get("content")
        if raw_content is None:
            content_str = "(empty)"
        elif isinstance(raw_content, str):
            content_str = raw_content
        elif isinstance(raw_content, (list, dict)):
            try:
                content_str = json.dumps(raw_content, indent=2, ensure_ascii=False)
            except Exception:
                content_str = str(raw_content)
        else:
            content_str = str(raw_content)

        chars_count = len(content_str)
        chars_info = f"{BRIGHT_BLACK}({chars_count:,} chars){RESET}"

        extra_meta: list[str] = []
        if name := msg.get("name"):
            extra_meta.append(f"name={name}")
        if tool_call_id := msg.get("tool_call_id"):
            extra_meta.append(f"tool_call_id={tool_call_id}")
        meta_str = f" {BRIGHT_BLACK}{' '.join(extra_meta)}{RESET}" if extra_meta else ""

        if is_final:
            box_color = BRIGHT_GREEN if raw_role == "user" else BRIGHT_CYAN
            box_top = f"{box_color}╔{'═' * (banner_w - 2)}╗{RESET}"
            title = (
                f"★ FINAL OUTBOUND MESSAGE (Message {idx + 1}/{total_msgs}) "
                f"— [{raw_role.upper()}] ({chars_count:,} chars){meta_str}"
            )
            box_mid = f"{box_color}║{RESET} {BOLD}{box_color}{title}{RESET}"
            box_bot = f"{box_color}╚{'═' * (banner_w - 2)}╝{RESET}"
            lines.append(box_top)
            lines.append(box_mid)
            lines.append(box_bot)
        else:
            idx_badge = f"{BRIGHT_BLACK}[MSG {idx + 1}/{total_msgs}]{RESET}"
            lines.append(f"{idx_badge} {role_badge}{meta_str} {chars_info}")
            lines.append(f"{BRIGHT_BLACK}{'─' * 40}{RESET}")

        if max_chars_per_msg and max_chars_per_msg > 0 and len(content_str) > max_chars_per_msg:
            head_len = max_chars_per_msg - 1000
            truncated_len = len(content_str) - max_chars_per_msg
            lines.append(content_str[:head_len])
            lines.append(
                f"\n{BRIGHT_YELLOW}... [Truncated {truncated_len:,} chars. "
                f"Set ZENITH_LOG_FULL_PAYLOAD=1 to view entire payload] ...{RESET}\n"
            )
            lines.append(content_str[-1000:])
        else:
            lines.append(content_str)

        # Format assistant tool calls if present
        tool_calls = msg.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            lines.append(f"  {BRIGHT_CYAN}Tool Calls ({len(tool_calls)}):{RESET}")
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_id = tc.get("id", "")
                    func = tc.get("function") or {}
                    func_name = func.get("name", "unknown")
                    func_args = func.get("arguments", "")
                    try:
                        if isinstance(func_args, str) and func_args.strip().startswith(("{", "[")):
                            formatted_args = json.dumps(json.loads(func_args), ensure_ascii=False)
                        else:
                            formatted_args = str(func_args)
                    except Exception:
                        formatted_args = str(func_args)
                    lines.append(
                        f"    {BRIGHT_BLUE}•{RESET} {BOLD}{func_name}{RESET}({formatted_args}) "
                        f"{BRIGHT_BLACK}[id: {tc_id}]{RESET}"
                    )
                else:
                    lines.append(f"    • {tc}")

        if is_final:
            lines.append(f"{box_color}{'─' * banner_w}{RESET}")
        elif idx < total_msgs - 1:
            lines.append("")

    if tools and isinstance(tools, list):
        lines.append(
            f"{BOLD}{BRIGHT_CYAN}Registered Tools ({len(tools)}){RESET}"
        )
        for tool in tools:
            if isinstance(tool, dict):
                func = tool.get("function") or tool
                t_name = func.get("name", "unknown")
                t_desc = _clamp_single_line((func.get("description") or "").strip().split("\n")[0])
                params = func.get("parameters") or {}
                props = list((params.get("properties") or {}).keys())
                reqs = set(params.get("required") or [])
                param_sig = [f"{p}" if p in reqs else f"{p}?" for p in props]
                sig_str = f"({', '.join(param_sig)})" if param_sig else "()"
                lines.append(
                    f"  {BRIGHT_BLUE}•{RESET} {BOLD}{t_name}{RESET}{sig_str} {BRIGHT_BLACK}— {t_desc}{RESET}"
                )
            else:
                lines.append(f"  • {tool}")

    lines.append(div_double)
    lines.append("")
    return "\n".join(lines)


def log_model_payload(
    logger: logging.Logger,
    kwargs: dict[str, Any],
    call_type: str = "stream",
) -> None:
    """Safe wrapper to log outbound model payload.

    Logs at DEBUG level by default. Set ZENITH_LOG_PAYLOADS=1 to force INFO.
    """
    if not logger.isEnabledFor(logging.DEBUG) and os.getenv("ZENITH_LOG_PAYLOADS", "").lower() not in ("1", "true", "yes"):
        return
    try:
        payload_text = format_model_payload(kwargs, call_type=call_type)
        if os.getenv("ZENITH_LOG_PAYLOADS", "").lower() in ("1", "true", "yes"):
            logger.info(payload_text)
        else:
            logger.debug(payload_text)
    except Exception as exc:
        model_name = kwargs.get("model") if isinstance(kwargs, dict) else "unknown"
        msgs_cnt = len(kwargs.get("messages") or []) if isinstance(kwargs, dict) else 0
        logger.warning(
            "Failed to format model payload: %s (model=%s, messages=%d)",
            exc,
            model_name,
            msgs_cnt,
        )


def setup_logging(
    level: str | int | None = None,
    log_file: str | Path = "zenith_server.log",
) -> None:
    """Configure ANSI colored logging for stdout and clean plain text logging for file."""
    try:
        import colorama

        colorama.just_fix_windows_console()
    except Exception:
        pass

    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if level is None:
        level_str = os.getenv("ZENITH_LOG_LEVEL", "INFO").upper()
        resolved_level = getattr(logging, level_str, logging.INFO)
    elif isinstance(level, str):
        resolved_level = getattr(logging, level.upper(), logging.INFO)
    else:
        resolved_level = level

    console_handler = SafeStreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_format = f"{BRIGHT_BLACK}%(asctime)s{RESET} [%(levelname)s] %(name)s: %(message)s"
    console_handler.setFormatter(ColoredFormatter(console_format))

    file_handler = logging.FileHandler(str(log_file), mode="w", encoding="utf-8")
    file_handler.setLevel(resolved_level)
    plain_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    file_handler.setFormatter(PlainFileFormatter(plain_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress chatty loggers
    for noisy in ("LiteLLM", "urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
