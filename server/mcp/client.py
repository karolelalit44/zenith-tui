from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class McpClient:
    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self._env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._tools: list[dict] = []
        self._initialized = False

    @property
    def tools(self) -> list[dict]:
        return self._tools

    @property
    def initialized(self) -> bool:
        return self._initialized

    async def start(self) -> None:
        import os

        full_env = {**os.environ, **(self._env or {})}
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "zenith", "version": "1.0.0"},
            },
        )
        if result:
            await self._send_notification("notifications/initialized", {})
            self._initialized = True
            tools_result = await self._send_request("tools/list", {})
            if tools_result and "tools" in tools_result:
                self._tools = tools_result["tools"]
                logger.info("MCP server '%s' discovered %d tools", self.name, len(self._tools))

    async def stop(self) -> None:
        if self._reader_task and (not self._reader_task.done()):
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process and self._process.returncode is None:
            try:
                await self._send_request("shutdown", None, timeout=5.0)
            except Exception:
                pass
            try:
                await self._send_notification("exit", None)
            except Exception:
                pass
            self._process.kill()
            try:
                await self._process.wait()
            except Exception:
                pass
        self._initialized = False

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if not self._initialized:
            return {"error": "MCP server not initialized"}
        result = await self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        return result or {}

    async def _send_request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        if not self._process or not self._process.stdin:
            raise RuntimeError(f"MCP server '{self.name}' not running")
        self._request_id += 1
        req_id = self._request_id
        message = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        payload = _encode_message(message)
        self._process.stdin.write(payload)
        await self._process.stdin.drain()
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' timed out")

    async def _send_notification(self, method: str, params: Any = None) -> None:
        if not self._process or not self._process.stdin:
            return
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        payload = _encode_message(message)
        self._process.stdin.write(payload)
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        if not self._process or not self._process.stdout:
            return
        reader = self._process.stdout
        try:
            while True:
                header_line = await reader.readline()
                if not header_line:
                    break
                content_length = 0
                while header_line and header_line.strip():
                    header_str = header_line.decode("utf-8", errors="replace")
                    if header_str.lower().startswith("content-length:"):
                        content_length = int(header_str.split(":", 1)[1].strip())
                    header_line = await reader.readline()
                if content_length == 0:
                    continue
                body = await reader.readexactly(content_length)
                message = json.loads(body.decode("utf-8", errors="replace"))
                if "id" in message and message["id"] in self._pending:
                    future = self._pending.pop(message["id"])
                    if "error" in message:
                        future.set_exception(RuntimeError(f"MCP error: {message['error']}"))
                    else:
                        future.set_result(message.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


def _encode_message(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body
