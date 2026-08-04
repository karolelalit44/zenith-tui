
from __future__ import annotations
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any
from .client import DEFAULT_SERVERS, LspClient

logger = logging.getLogger(__name__)


class LspManager:

    def __init__(self, workspace_root: str, custom_servers: dict[str, dict[str, Any]] | None = None) -> None:
        self.workspace_root = workspace_root
        self._clients: dict[str, LspClient] = {}
        self._ext_to_server: dict[str, str] = {}
        self._custom_servers = custom_servers or {}
        self._init_task: asyncio.Task | None = None
        self._build_ext_index()

    def _build_ext_index(self) -> None:
        servers = {**DEFAULT_SERVERS, **self._custom_servers}
        for ext, config in servers.items():
            self._ext_to_server[ext] = config.get("name", config.get("command", ext))

    def get_server_for_file(self, file_path: str) -> dict[str, Any] | None:
        ext = Path(file_path).suffix.lower()
        all_servers = {**DEFAULT_SERVERS, **self._custom_servers}
        return all_servers.get(ext)

    def supports_file(self, file_path: str) -> bool:
        return self.get_server_for_file(file_path) is not None

    def _get_server_name(self, file_path: str) -> str | None:
        config = self.get_server_for_file(file_path)
        if config is None:
            return None
        return config.get("name", config.get("command", ""))

    async def get_client(self, file_path: str) -> LspClient | None:
        server_name = self._get_server_name(file_path)
        if server_name is None:
            return None

        if server_name in self._clients:
            client = self._clients[server_name]
            if client.initialized:
                return client

        config = self.get_server_for_file(file_path)
        if config is None:
            return None

        command = config.get("command", "")
        if not shutil.which(command):
            logger.debug("LSP server '%s' not found on PATH", command)
            return None

        client = LspClient(name=server_name, command=command, args=config.get("args", []), cwd=self.workspace_root)
        try:
            await client.start()
            root_uri = Path(self.workspace_root).as_uri()
            await client.initialize(root_uri, self.workspace_root)
            self._clients[server_name] = client
            logger.info("LSP client '%s' ready for %s files", server_name, list(config.get("file_types", [Path("").suffix])))
            return client
        except Exception as e:
            logger.warning("Failed to start LSP server '%s': %s", server_name, e)
            await client.stop()
            return None

    async def shutdown_all(self) -> None:
        for name, client in list(self._clients.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.warning("Error stopping LSP '%s': %s", name, e)
        self._clients.clear()

    def active_servers(self) -> list[str]:
        return [name for name, c in self._clients.items() if c.initialized]


_manager: LspManager | None = None


def get_lsp_manager() -> LspManager | None:
    return _manager


def set_lsp_manager(manager: LspManager) -> None:
    global _manager
    _manager = manager
