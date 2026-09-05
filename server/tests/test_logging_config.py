from __future__ import annotations

import logging
from unittest.mock import MagicMock

from server.logging_config import (
    BRIGHT_CYAN,
    BRIGHT_GREEN,
    BRIGHT_MAGENTA,
    ColoredFormatter,
    PlainFileFormatter,
    format_model_payload,
    log_model_payload,
    setup_logging,
)


def test_colored_formatter_formats_with_ansi():
    formatter = ColoredFormatter("%(levelname)s %(name)s: %(message)s")
    record = logging.LogRecord(
        name="server.api.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Hello World",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    assert "\033[" in result
    assert "INFO" in result
    assert "server.api.test" in result
    assert "Hello World" in result


def test_colored_formatter_smart_levels_and_keywords():
    formatter = ColoredFormatter("%(levelname)s %(name)s: %(message)s")

    # DEBUG: dim gray
    debug_record = logging.LogRecord(
        name="server.debug",
        level=logging.DEBUG,
        pathname="test.py",
        lineno=1,
        msg="routine internal detail",
        args=(),
        exc_info=None,
    )
    debug_out = formatter.format(debug_record)
    assert "\033[2m\033[90m" in debug_out

    # WARNING: yellow
    warn_record = logging.LogRecord(
        name="server.warn",
        level=logging.WARNING,
        pathname="test.py",
        lineno=1,
        msg="quota running low",
        args=(),
        exc_info=None,
    )
    warn_out = formatter.format(warn_record)
    assert "\033[93m" in warn_out

    # ERROR: red
    err_record = logging.LogRecord(
        name="server.err",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="connection failed",
        args=(),
        exc_info=None,
    )
    err_out = formatter.format(err_record)
    assert "\033[91m" in err_out

    # INFO with keywords
    info_record = logging.LogRecord(
        name="server.handlers",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="PROMPT.RECEIVED session=123",
        args=(),
        exc_info=None,
    )
    info_out = formatter.format(info_record)
    assert "PROMPT.RECEIVED" in info_out
    assert "\033[1;96mPROMPT.RECEIVED\033[0m" in info_out or "\033[1m\033[96mPROMPT.RECEIVED\033[0m" in info_out


def test_plain_file_formatter_strips_ansi():
    formatter = PlainFileFormatter("%(levelname)s %(name)s: %(message)s")
    record = logging.LogRecord(
        name="server.api.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg=f"{BRIGHT_GREEN}Hello{BRIGHT_CYAN} World\033[0m",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    assert "\033[" not in result
    assert "Hello World" in result


def test_format_model_payload_renders_messages_and_final_indicator():
    kwargs = {
        "model": "openrouter/free",
        "temperature": 0.2,
        "max_tokens": 4096,
        "tool_choice": "auto",
        "messages": [
            {"role": "system", "content": "You are Zenith."},
            {
                "role": "user",
                "content": '<attachment path="plan.md">\n# Plan\n</attachment>\n\nanalyze plan',
            },
            {
                "role": "assistant",
                "content": "Reading file.",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "plan.md"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "name": "read_file",
                "content": "file contents",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file contents",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
    }

    output = format_model_payload(kwargs, call_type="stream")

    # ANSI colors present
    assert "\033[" in output

    from server.config.constants import ANSI_RE

    plain = ANSI_RE.sub("", output)

    # Header verification
    assert "LLM OUTBOUND PAYLOAD [stream]" in plain
    assert "model=openrouter/free" in plain
    assert "Messages: 4" in plain
    assert "Tools: 1" in plain

    # System message
    assert "[SYSTEM]" in plain
    assert "You are Zenith." in plain

    # User message with attachment
    assert "[USER]" in plain
    assert '<attachment path="plan.md">' in plain

    # Tool call formatting
    assert "Tool Calls (1)" in plain
    assert "read_file" in plain
    assert "call_123" in plain

    # Final outbound message indicator
    assert "★ FINAL OUTBOUND" in plain
    assert "[TOOL]" in plain

    # Registered tools section
    assert "Registered Tools (1)" in plain
    assert "read_file(path) — Read file contents" in plain


def test_log_model_payload_safety():
    mock_logger = MagicMock(spec=logging.Logger)
    # Valid payload
    log_model_payload(mock_logger, {"model": "test", "messages": []})
    mock_logger.info.assert_called_once()

    # Even with weird arguments, does not crash
    mock_logger.reset_mock()
    log_model_payload(mock_logger, None)  # type: ignore[arg-type]


def test_setup_logging_initialization(tmp_path):
    log_file = tmp_path / "test_zenith.log"
    setup_logging(level="DEBUG", log_file=log_file)

    root = logging.getLogger()
    assert len(root.handlers) == 2

    stream_handler = next((h for h in root.handlers if isinstance(h, logging.StreamHandler)), None)
    file_handler = next((h for h in root.handlers if isinstance(h, logging.FileHandler)), None)

    assert stream_handler is not None
    assert isinstance(stream_handler.formatter, ColoredFormatter)

    assert file_handler is not None
    assert isinstance(file_handler.formatter, PlainFileFormatter)

    # Test that logging to root writes clean plain text to file
    test_logger = logging.getLogger("test.logger")
    test_logger.info(f"{BRIGHT_MAGENTA}Special colored message\033[0m")

    file_handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "\033[" not in content
    assert "Special colored message" in content
