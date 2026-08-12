from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from server.toolkit.tools.mcp_tool import McpToolWrapper

from .client import McpClient

if TYPE_CHECKING:
    from server.config.settings import McpServerConfig
logger = logging.getLogger(__name__)


class McpManager:
    def __init__(self, servers: dict[str, McpServerConfig]) -> None:
        self._servers = dict(servers)
        self._clients: dict[str, McpClient] = {}
        self._status: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    @property
    def servers(self) -> dict[str, McpServerConfig]:
        return self._servers

    @property
    def status(self) -> dict[str, str]:
        return dict(self._status)

    @property
    def errors(self) -> dict[str, str]:
        return dict(self._errors)

    async def start(self) -> None:
        for name, cfg in self._servers.items():
            client = McpClient(name, cfg.command, cfg.args, cfg.env)
            self._clients[name] = client
            self._status[name] = "connecting"
            try:
                await client.start()
                self._status[name] = "connected"
                logger.info("MCP server '%s' connected with %d tools", name, len(client.tools))
            except Exception as e:
                self._status[name] = "failed"
                self._errors[name] = str(e)
                logger.warning("MCP server '%s' failed to start: %s", name, e)

    async def stop(self) -> None:
        for name, client in self._clients.items():
            try:
                await client.stop()
                self._status[name] = "stopped"
            except Exception:
                logger.exception("Error stopping MCP server '%s'", name)

    def build_wrappers(self) -> list[McpToolWrapper]:
        wrappers: list[McpToolWrapper] = []
        for name, client in self._clients.items():
            if not client.initialized:
                continue
            for tool in client.tools:
                wrappers.append(McpToolWrapper(tool, client, server_name=name))
        return wrappers

    def list_servers(self) -> list[dict]:
        return [
            {
                "name": name,
                "status": self._status.get(name, "unknown"),
                "tools": len(client.tools),
                "error": self._errors.get(name, ""),
            }
            for name, client in self._clients.items()
        ]
