from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from server.config.constants import BUILD_MODE

logger = logging.getLogger(__name__)


def _render_command(command: str, payload: dict[str, Any]) -> str:
    try:
        return command.format(**payload)
    except (KeyError, IndexError, ValueError):
        return command


class HookRunner:
    def __init__(self, config: Any | None = None) -> None:
        from server.config.settings import HooksConfig

        self._config = config if config is not None else HooksConfig()

    @property
    def enabled(self) -> bool:
        return bool(self.pre_tool_use or self.post_tool_use or self.session_start)

    @property
    def pre_tool_use(self) -> list[str]:
        return list(getattr(self._config, "pre_tool_use", None) or [])

    @property
    def post_tool_use(self) -> list[str]:
        return list(getattr(self._config, "post_tool_use", None) or [])

    @property
    def session_start(self) -> list[str]:
        return list(getattr(self._config, "session_start", None) or [])

    @property
    def timeout(self) -> int:
        try:
            return int(getattr(self._config, "timeout", 30))
        except (TypeError, ValueError):
            return 30

    async def run(
        self, commands: list[str], payload: dict[str, Any], workspace_root: str = "."
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for command in commands:
            results.append(await self._run_one(command, payload, workspace_root))
        return results

    async def _run_one(
        self, command: str, payload: dict[str, Any], workspace_root: str
    ) -> dict[str, Any]:
        rendered = _render_command(command, payload)
        try:
            from server.shell_runner import run_shell_command

            proc = await run_shell_command(
                rendered,
                cwd=workspace_root or ".",
            )
        except Exception as e:
            logger.warning("Failed to start hook '%s': %s", command, e)
            return {"command": command, "exit_code": -1, "stdout": "", "stderr": str(e)}
        payload_bytes = json.dumps(payload, default=str).encode("utf-8", errors="replace")
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload_bytes), timeout=self.timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"hook timed out after {self.timeout}s",
            }
        return {
            "command": command,
            "exit_code": proc.returncode or 0,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
        }

    async def run_pre_tool_use(
        self,
        name: str,
        params: dict[str, Any],
        workspace_root: str = ".",
        session_id: str | None = None,
        mode: str = BUILD_MODE,
    ) -> list[dict[str, Any]]:
        payload = {
            "name": name,
            "tool_name": name,
            "params": params,
            "workspace_root": workspace_root,
            "session_id": session_id or "",
            "mode": mode,
        }
        return await self.run(self.pre_tool_use, payload, workspace_root)

    async def run_post_tool_use(
        self,
        name: str,
        params: dict[str, Any],
        result: Any,
        workspace_root: str = ".",
        session_id: str | None = None,
        mode: str = BUILD_MODE,
    ) -> list[dict[str, Any]]:
        payload = {
            "name": name,
            "tool_name": name,
            "params": params,
            "result_success": bool(getattr(result, "success", True)),
            "result_error": getattr(result, "error", "") or "",
            "result_output": (getattr(result, "output", "") or "")[:2000],
            "workspace_root": workspace_root,
            "session_id": session_id or "",
            "mode": mode,
        }
        return await self.run(self.post_tool_use, payload, workspace_root)

    async def run_session_start(
        self,
        session_id: str,
        title: str = "",
        mode: str = BUILD_MODE,
        provider: str = "",
        workspace_root: str = ".",
    ) -> list[dict[str, Any]]:
        payload = {
            "session_id": session_id,
            "title": title,
            "mode": mode,
            "provider": provider,
            "workspace_root": workspace_root,
        }
        return await self.run(self.session_start, payload, workspace_root)
