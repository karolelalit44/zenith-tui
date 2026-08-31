from server.toolkit.command_result import CommandResult, detect_false_success
from server.toolkit.command_safety import (
    PermissionDecision,
    RiskAssessment,
    evaluate_permission,
)
from server.toolkit.param_normalizer import decode_params_with_schema
from server.toolkit.path_validator import (
    is_destructive_delete,
    is_destructive_write,
    validate_path,
)


# ---------------------------------------------------------------------------
# Module 23 — schema-based param decode helper
# ---------------------------------------------------------------------------


def test_decode_without_registry_falls_back_to_normalizer():
    res = decode_params_with_schema({"filePath": "a.txt"}, "file_write")
    assert res == {"path": "a.txt"}


def test_decode_coerces_types_via_schema():
    fake_registry = _RegistryWithSchema(
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "ratio": {"type": "number"},
                "verbose": {"type": "boolean"},
                "tags": {"type": "array"},
            },
            "required": ["count"],
        }
    )
    res = decode_params_with_schema(
        {"count": "3", "ratio": "1.5", "verbose": "true", "tags": '["a","b"]'},
        "some_tool",
        fake_registry,
    )
    assert res["count"] == 3
    assert res["ratio"] == 1.5
    assert res["verbose"] is True
    assert res["tags"] == ["a", "b"]


def test_decode_adds_required_default():
    fake_registry = _RegistryWithSchema(
        {
            "type": "object",
            "properties": {"mode": {"type": "string", "default": "auto"}},
            "required": ["mode"],
        }
    )
    res = decode_params_with_schema({}, "some_tool", fake_registry)
    assert res["mode"] == "auto"


def test_decode_unknown_tool_falls_back_to_normalizer():
    res = decode_params_with_schema({"filepath": "a.py"}, "nope", _RegistryWithSchema(None))
    assert res["path"] == "a.py"


# ---------------------------------------------------------------------------
# Module 23 — path validator safety helpers
# ---------------------------------------------------------------------------


def test_validate_path_workspace_confined(tmp_path):
    p = validate_path("sub/a.txt", str(tmp_path))
    assert p is not None
    assert p == tmp_path / "sub/a.txt"


def test_validate_path_rejects_escape(tmp_path):
    assert validate_path("../escape.txt", str(tmp_path)) is None


def test_destructive_write_flags_existing_file(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("x")
    assert is_destructive_write(f, str(tmp_path)) is True
    assert is_destructive_write(tmp_path / "new.txt", str(tmp_path)) is False


def test_destructive_write_flags_outside_workspace(tmp_path):
    assert is_destructive_write(tmp_path.parent / "x", str(tmp_path)) is True


def test_destructive_delete_flags_non_existent(tmp_path):
    assert is_destructive_delete(tmp_path / "missing.txt", str(tmp_path)) is True
    f = tmp_path / "real.txt"
    f.write_text("x")
    assert is_destructive_delete(f, str(tmp_path)) is False


# ---------------------------------------------------------------------------
# Module 23 — permission/approval model
# ---------------------------------------------------------------------------


def test_read_only_permits():
    d = evaluate_permission(RiskAssessment(False, "", "safe", tier="read_only"))
    assert isinstance(d, PermissionDecision)
    assert d.permission == "allow"
    assert bool(d)


def test_workspace_write_auto_allow_when_safe():
    d = evaluate_permission(
        RiskAssessment(False, "", "safe", requires_approval=False, tier="workspace_write")
    )
    assert d.permission == "allow"


def test_workspace_write_asks_when_requires_approval():
    d = evaluate_permission(
        RiskAssessment(
            True, "needs check", "medium", requires_approval=True, tier="workspace_write"
        )
    )
    assert d.permission == "ask"


def test_network_asks():
    d = evaluate_permission(
        RiskAssessment(True, "net", "medium", requires_approval=True, tier="network")
    )
    assert d.permission == "ask"


def test_destructive_high_denies():
    d = evaluate_permission(
        RiskAssessment(True, "rm -rf /", "high", requires_approval=True, tier="destructive")
    )
    assert d.permission == "deny"


# ---------------------------------------------------------------------------
# Module 23 — consolidated CommandResult
# ---------------------------------------------------------------------------


def test_command_result_ok_basic():
    r = CommandResult(exit_code=0, output="hello")
    assert r.ok
    assert r.false_success is None


def test_command_result_not_ok_on_nonzero():
    assert CommandResult(exit_code=1).ok is False


def test_command_result_not_ok_on_false_success():
    r = CommandResult.from_parts(exit_code=0, output="", error="Unable to initialize device PRN")
    assert r.ok is False
    assert r.false_success is not None


def test_command_result_truncation_budget():
    r = CommandResult.from_parts(exit_code=0, output="x" * 100, error="", trim_budget=50)
    assert r.truncated
    assert len(r.combined) <= 50


def test_detect_false_success_none():
    assert detect_false_success("all good", "") is None


class _RegistryWithSchema:
    """Minimal fake tool registry exposing .get(tool) -> object with .schema."""

    def __init__(self, schema):
        self._schema = schema

    def get(self, name):
        if self._schema is None:
            return None
        return _FakeTool(self._schema)


class _FakeTool:
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, **kwargs):
        return kwargs
