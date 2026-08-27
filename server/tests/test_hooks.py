from __future__ import annotations

from server.config.settings import AppSettings, HooksConfig
from server.domain.hooks import HookRunner
from server.sessions.service import DefaultSessionService
from server.storage import StorageHome
from server.storage.session_store import FileMessageRepository, FileSessionRepository
from server.toolkit import ToolRegistry
from server.toolkit.base import ToolContext, ToolResult
from server.toolkit.middleware import HookMiddleware


class TestHooksConfig:
    def test_hooks_default_empty(self):
        cfg = HooksConfig()
        assert cfg.pre_tool_use == []
        assert cfg.post_tool_use == []
        assert cfg.session_start == []
        assert cfg.timeout == 30

    def test_hooks_from_dict(self):
        cfg = HooksConfig(pre_tool_use=["echo hi"], post_tool_use=["ruff check ."], timeout=5)
        assert cfg.pre_tool_use == ["echo hi"]
        assert cfg.post_tool_use == ["ruff check ."]
        assert cfg.timeout == 5

    def test_appsettings_accepts_hooks(self):
        settings = AppSettings(
            hooks={"pre_tool_use": ["exit 1"], "session_start": ["echo start"], "timeout": 3}
        )
        assert settings.hooks.pre_tool_use == ["exit 1"]
        assert settings.hooks.session_start == ["echo start"]
        assert settings.hooks.timeout == 3

    def test_parse_hooks_env(self):
        from server.config.loader import parse_hooks_env

        parsed = parse_hooks_env(
            '{"pre_tool_use":["exit 1"],"post_tool_use":["echo ok"],"timeout":5}'
        )
        assert parsed == {"pre_tool_use": ["exit 1"], "post_tool_use": ["echo ok"], "timeout": 5}

    def test_parse_hooks_env_invalid(self):
        from server.config.loader import parse_hooks_env

        assert parse_hooks_env("") is None
        assert parse_hooks_env("not json{") is None
        assert parse_hooks_env('["list"]') is None


class TestHookRunner:
    async def test_pre_hook_exit_zero(self, temp_dir):
        runner = HookRunner(HooksConfig(pre_tool_use=["echo pre-ran"]))
        results = await runner.run_pre_tool_use("bash", {}, workspace_root=str(temp_dir))
        assert results[0]["exit_code"] == 0
        assert "pre-ran" in results[0]["stdout"]

    async def test_pre_hook_exit_nonzero(self, temp_dir):
        runner = HookRunner(HooksConfig(pre_tool_use=["exit 3"]))
        results = await runner.run_pre_tool_use("bash", {}, workspace_root=str(temp_dir))
        assert results[0]["exit_code"] == 3

    async def test_payload_on_stdin(self, temp_dir):
        runner = HookRunner(
            HooksConfig(
                pre_tool_use=["python -c \"import sys,json; json.load(sys.stdin); print('ok')\""]
            )
        )
        results = await runner.run_pre_tool_use("bash", {"k": 1}, workspace_root=str(temp_dir))
        assert results[0]["exit_code"] == 0
        assert "ok" in results[0]["stdout"]

    async def test_template_substitution(self, temp_dir):
        runner = HookRunner(
            HooksConfig(pre_tool_use=["echo tool={tool_name} session={session_id}"])
        )
        results = await runner.run_pre_tool_use(
            "bash", {}, workspace_root=str(temp_dir), session_id="s1"
        )
        assert "tool=bash" in results[0]["stdout"]
        assert "session=s1" in results[0]["stdout"]

    async def test_timeout_kills_hook(self, temp_dir):
        runner = HookRunner(
            HooksConfig(pre_tool_use=['python -c "import time; time.sleep(10)"'], timeout=1)
        )
        results = await runner.run_pre_tool_use("bash", {}, workspace_root=str(temp_dir))
        assert results[0]["exit_code"] == -1
        assert "timed out" in results[0]["stderr"]

    async def test_disabled_runner(self, temp_dir):
        runner = HookRunner(HooksConfig())
        assert runner.enabled is False
        assert await runner.run([], {}, str(temp_dir)) == []


class TestHookMiddleware:
    async def test_pre_hook_blocks(self, temp_dir):
        mw = HookMiddleware(HookRunner(HooksConfig(pre_tool_use=["exit 1"])))
        ctx = ToolContext(request_id="r", workspace_root=str(temp_dir))
        outcome = await mw.before_execute("bash", {"command": "echo hi"}, ctx)
        assert isinstance(outcome, ToolResult)
        assert outcome.success is False
        assert "Blocked by PreToolUse hook" in outcome.error

    async def test_pre_hook_passes(self, temp_dir):
        mw = HookMiddleware(HookRunner(HooksConfig(pre_tool_use=["exit 0"])))
        ctx = ToolContext(request_id="r", workspace_root=str(temp_dir))
        assert await mw.before_execute("bash", {}, ctx) is True

    async def test_no_pre_hooks_passes(self, temp_dir):
        mw = HookMiddleware(HookRunner(HooksConfig()))
        ctx = ToolContext(request_id="r", workspace_root=str(temp_dir))
        assert await mw.before_execute("bash", {}, ctx) is True

    async def test_post_hook_attaches_metadata(self, temp_dir):
        mw = HookMiddleware(HookRunner(HooksConfig(post_tool_use=["echo lint-ok"])))
        ctx = ToolContext(request_id="r", workspace_root=str(temp_dir))
        result = ToolResult(success=True, output="out")
        out = await mw.after_execute("bash", {}, result, ctx)
        assert out is result
        assert out.metadata["post_tool_use"][0]["exit_code"] == 0
        assert "lint-ok" in out.metadata["post_tool_use"][0]["stdout"]

    async def test_no_post_hooks_no_metadata(self, temp_dir):
        mw = HookMiddleware(HookRunner(HooksConfig()))
        ctx = ToolContext(request_id="r", workspace_root=str(temp_dir))
        result = ToolResult(success=True, output="out")
        out = await mw.after_execute("bash", {}, result, ctx)
        assert out.metadata == {}


class _EchoTool:
    name = "echo"
    modes = None

    async def execute(self, params, workspace_root):
        return ToolResult(success=True, output=params.get("text", ""))

    def validate_params(self, params):
        return True

    def get_schema(self):
        return {"type": "object", "properties": {}}


class TestHookRegistryE2E:
    async def test_pre_tool_use_blocks_via_registry(self, temp_dir):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.register_middleware(
            HookMiddleware(HookRunner(HooksConfig(pre_tool_use=["exit 1"])))
        )
        result = await registry.execute("echo", {"text": "hello"}, str(temp_dir))
        assert result.success is False
        assert "Blocked by PreToolUse hook" in result.error

    async def test_pre_tool_use_passes_via_registry(self, temp_dir):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.register_middleware(
            HookMiddleware(HookRunner(HooksConfig(pre_tool_use=["exit 0"])))
        )
        result = await registry.execute("echo", {"text": "hello"}, str(temp_dir))
        assert result.success is True
        assert result.output == "hello"


class TestSessionStartHook:
    async def test_session_start_fires(self, temp_dir):
        svc = DefaultSessionService(
            session_repo=FileSessionRepository(StorageHome(temp_dir)),
            message_repo=FileMessageRepository(StorageHome(temp_dir)),
            hooks=HooksConfig(session_start=["echo started >> session-hook.txt"]),
        )
        session = await svc.create(title="hook test", workspace_root=str(temp_dir))
        assert session.id
        marker = temp_dir / "session-hook.txt"
        # PowerShell's >> writes UTF-16; decode tolerantly and strip NULs so
        # the assertion is shell-encoding agnostic.
        content = marker.read_text(encoding="utf-8", errors="ignore")
        assert content.replace("\x00", "").strip() == "started"

    async def test_no_session_start_without_hooks(self, temp_dir):
        svc = DefaultSessionService(
            session_repo=FileSessionRepository(StorageHome(temp_dir)),
            message_repo=FileMessageRepository(StorageHome(temp_dir)),
        )
        await svc.create(title="no hooks", workspace_root=str(temp_dir))
        assert not (temp_dir / "session-hook.txt").exists()

    async def test_session_start_title_substitution(self, temp_dir):
        svc = DefaultSessionService(
            session_repo=FileSessionRepository(StorageHome(temp_dir)),
            message_repo=FileMessageRepository(StorageHome(temp_dir)),
            hooks=HooksConfig(session_start=["echo title={title} >> titles.txt"]),
        )
        await svc.create(title="my-session", workspace_root=str(temp_dir))
        assert (temp_dir / "titles.txt").read_text(encoding="utf-8", errors="ignore").replace(
            "\x00", ""
        ).strip() == "title=my-session"


class TestCreateDefaultRegistryHooks:
    async def test_registry_with_hooks_blocks(self, temp_dir):
        from server.toolkit import create_default_registry

        registry = create_default_registry(
            timeout=5, provider=None, hooks=HooksConfig(pre_tool_use=["exit 1"])
        )
        result = await registry.execute("bash", {"command": "echo hello"}, str(temp_dir))
        assert result.success is False
        assert "Blocked by PreToolUse hook" in result.error

    async def test_registry_without_hooks_executes(self, temp_dir):
        from server.toolkit import create_default_registry

        registry = create_default_registry(timeout=5, provider=None)
        result = await registry.execute("bash", {"command": "echo hello"}, str(temp_dir))
        assert result.success is True
        assert "hello" in result.output
