"""Tool-name aliasing in validate_tool_calls (server/toolkit/executor.py).

Prod logs showed repeated wasted turns on ``Tool calls for non-existent
tools: read`` — the model reaches for ``read`` but only ``file_read``
exists. Aliasing converts a 100%-invalid-today call into a served call
instead of a full-LLM-turn error round-trip.
"""

from server.toolkit import create_default_registry
from server.toolkit.executor import _TOOL_NAME_ALIASES, validate_tool_calls


def test_read_alias_rewrites_to_file_read():
    calls = [{"tool": "read", "params": {"path": "a.txt"}}]
    valid, invalid = validate_tool_calls(calls, {"file_read", "grep"})
    assert invalid == []
    assert len(valid) == 1
    assert valid[0]["tool"] == "file_read"
    assert valid[0]["params"] == {"path": "a.txt"}


def test_read_alias_requires_canonical_registered():
    calls = [{"tool": "read", "params": {"path": "a.txt"}}]
    valid, invalid = validate_tool_calls(calls, {"grep"})
    assert valid == []
    assert len(invalid) == 1
    assert invalid[0]["tool"] == "read"


def test_genuinely_unknown_tools_still_invalid():
    calls = [{"tool": "frobnicate", "params": {}}]
    valid, invalid = validate_tool_calls(calls, {"file_read", "grep"})
    assert valid == []
    assert [c["tool"] for c in invalid] == ["frobnicate"]


def test_registered_tools_pass_through_untouched():
    calls = [{"tool": "grep", "params": {"pattern": "x"}}]
    valid, invalid = validate_tool_calls(calls, {"file_read", "grep"})
    assert invalid == []
    assert valid[0]["tool"] == "grep"


def test_aliases_never_target_mutating_tools():
    registry = create_default_registry()
    for alias, canonical in _TOOL_NAME_ALIASES.items():
        assert alias != canonical
        tool = registry.get(canonical)
        assert tool is not None, f"alias '{alias}' targets unregistered tool '{canonical}'"
        assert tool.read_only, f"alias '{alias}' targets mutating tool '{canonical}'"
