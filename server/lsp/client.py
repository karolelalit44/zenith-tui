from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
DEFAULT_SERVERS: dict[str, dict[str, Any]] = {
    ".py": {"command": "pyright-langserver", "args": ["--stdio"], "name": "pyright"},
    ".js": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "name": "typescript-language-server",
    },
    ".ts": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "name": "typescript-language-server",
    },
    ".tsx": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "name": "typescript-language-server",
    },
    ".jsx": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "name": "typescript-language-server",
    },
    ".go": {"command": "gopls", "args": [], "name": "gopls"},
    ".rs": {"command": "rust-analyzer", "args": [], "name": "rust-analyzer"},
    ".java": {"command": "jdtls", "args": [], "name": "jdtls"},
    ".rb": {"command": "solargraph", "args": ["stdio"], "name": "solargraph"},
    ".c": {"command": "clangd", "args": [], "name": "clangd"},
    ".cpp": {"command": "clangd", "args": [], "name": "clangd"},
    ".h": {"command": "clangd", "args": [], "name": "clangd"},
}
_EXT_TO_LANG_ID: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".jsx": "javascriptreact",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "shellscript",
    ".bash": "shellscript",
    ".xml": "xml",
}


def get_language_id(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG_ID.get(ext, "plaintext")


class LspClient:
    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args or []
        self.cwd = cwd
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._notifications: asyncio.Queue[dict] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._initialized = False
        self._capabilities: dict = {}
        self._env = env
        self._open_files: set[str] = set()

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def capabilities(self) -> dict:
        return self._capabilities

    async def start(self) -> None:
        full_env = {**os.environ, **(self._env or {})}
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=full_env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("LSP server '%s' started (pid=%s)", self.name, self._process.pid)

    async def stop(self) -> None:
        if not self._process:
            return
        try:
            await self._send_request("shutdown", None)
            await self._send_notification("exit")
        except Exception:
            pass
        if self._reader_task and (not self._reader_task.done()):
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process and self._process.returncode is None:
            self._process.kill()
            try:
                await self._process.wait()
            except Exception:
                pass
        self._initialized = False
        logger.info("LSP server '%s' stopped", self.name)

    async def initialize(self, root_uri: str, root_path: str) -> dict:
        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": root_path,
            "capabilities": {
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": False,
                        "willSave": False,
                        "didSave": True,
                        "willSaveWaitUntil": False,
                    },
                    "publishDiagnostics": {},
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "rename": {"dynamicRegistration": False},
                    "completion": {
                        "dynamicRegistration": False,
                        "completionItem": {"snippetSupport": False},
                    },
                }
            },
            "initializationOptions": {},
        }
        result = await self._send_request("initialize", params)
        self._capabilities = result.get("capabilities", {})
        await self._send_notification("initialized", {})
        self._initialized = True
        logger.info(
            "LSP server '%s' initialized, capabilities=%s",
            self.name,
            list(self._capabilities.keys()),
        )
        return result

    async def did_open(self, file_path: str, language_id: str, content: str) -> None:
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": content}
        }
        await self._send_notification("textDocument/didOpen", params)
        self._open_files.add(uri)

    async def did_change(self, file_path: str, content: str, version: int | None = None) -> None:
        uri = Path(file_path).as_uri()
        ver = version or len(self._open_files) + 1
        params = {
            "textDocument": {"uri": uri, "version": ver},
            "contentChanges": [{"text": content}],
        }
        await self._send_notification("textDocument/didChange", params)

    async def did_close(self, file_path: str) -> None:
        uri = Path(file_path).as_uri()
        params = {"textDocument": {"uri": uri}}
        await self._send_notification("textDocument/didClose", params)
        self._open_files.discard(uri)

    async def did_save(self, file_path: str, content: str) -> None:
        uri = Path(file_path).as_uri()
        params = {"textDocument": {"uri": uri}, "text": content}
        await self._send_notification("textDocument/didSave", params)

    async def get_diagnostics(self, file_path: str, content: str) -> list[dict]:
        language_id = get_language_id(file_path)
        await self.did_open(file_path, language_id, content)
        await asyncio.sleep(0.5)
        diagnostics: list[dict] = []
        temp: list[dict] = []
        while not self._notifications.empty():
            try:
                notif = self._notifications.get_nowait()
                temp.append(notif)
            except asyncio.QueueEmpty:
                break
        for notif in temp:
            if notif.get("method") == "textDocument/publishDiagnostics":
                diag_uri = notif.get("params", {}).get("uri", "")
                if diag_uri == Path(file_path).as_uri():
                    for d in notif.get("params", {}).get("diagnostics", []):
                        diagnostics.append(
                            {
                                "range": d.get("range", {}),
                                "severity": _severity_name(d.get("severity", 1)),
                                "message": d.get("message", ""),
                                "source": d.get("source", ""),
                                "code": d.get("code", ""),
                            }
                        )
        await self.did_close(file_path)
        return diagnostics

    async def goto_definition(
        self, file_path: str, content: str, line: int, character: int
    ) -> list[dict]:
        language_id = get_language_id(file_path)
        await self.did_open(file_path, language_id, content)
        uri = Path(file_path).as_uri()
        params = {"textDocument": {"uri": uri}, "position": {"line": line, "character": character}}
        try:
            result = await self._send_request("textDocument/definition", params, timeout=10.0)
        except Exception:
            result = None
        await self.did_close(file_path)
        if result is None:
            return []
        locations = result if isinstance(result, list) else [result]
        definitions = []
        for loc in locations:
            if "targetUri" in loc:
                definitions.append(
                    {
                        "file": _uri_to_path(loc["targetUri"]),
                        "line": loc.get("targetRange", loc.get("range", {}))
                        .get("start", {})
                        .get("line", 0),
                        "character": loc.get("targetRange", loc.get("range", {}))
                        .get("start", {})
                        .get("character", 0),
                    }
                )
            elif "uri" in loc:
                definitions.append(
                    {
                        "file": _uri_to_path(loc["uri"]),
                        "line": loc.get("range", {}).get("start", {}).get("line", 0),
                        "character": loc.get("range", {}).get("start", {}).get("character", 0),
                    }
                )
        return definitions

    async def goto_references(
        self, file_path: str, content: str, line: int, character: int
    ) -> list[dict]:
        language_id = get_language_id(file_path)
        await self.did_open(file_path, language_id, content)
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        }
        try:
            result = await self._send_request("textDocument/references", params, timeout=10.0)
        except Exception:
            result = None
        await self.did_close(file_path)
        if result is None:
            return []
        references = []
        for loc in result if isinstance(result, list) else []:
            references.append(
                {
                    "file": _uri_to_path(loc.get("uri", "")),
                    "line": loc.get("range", {}).get("start", {}).get("line", 0),
                    "character": loc.get("range", {}).get("start", {}).get("character", 0),
                }
            )
        return references

    async def rename(
        self, file_path: str, content: str, line: int, character: int, new_name: str
    ) -> dict[str, str] | None:
        language_id = get_language_id(file_path)
        await self.did_open(file_path, language_id, content)
        uri = Path(file_path).as_uri()
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "newName": new_name,
        }
        try:
            result = await self._send_request("textDocument/rename", params, timeout=10.0)
        except Exception:
            result = None
        await self.did_close(file_path)
        if not result or "changes" not in result:
            return None
        file_edits: dict[str, str] = {}
        for edit_uri, edits in result["changes"].items():
            file_path_str = _uri_to_path(edit_uri)
            if not Path(file_path_str).exists():
                continue
            original = Path(file_path_str).read_text(encoding="utf-8", errors="replace")
            sorted_edits = sorted(
                edits,
                key=lambda e: (e["range"]["start"]["line"], e["range"]["start"]["character"]),
                reverse=True,
            )
            new_text = original
            for edit in sorted_edits:
                start = edit["range"]["start"]
                end = edit["range"]["end"]
                start_offset = _position_to_offset(original, start["line"], start["character"])
                end_offset = _position_to_offset(original, end["line"], end["character"])
                new_text = new_text[:start_offset] + edit["newText"] + new_text[end_offset:]
            file_edits[file_path_str] = new_text
        return file_edits if file_edits else None

    async def _send_request(self, method: str, params: Any, timeout: float = 30.0) -> Any:
        if not self._process or not self._process.stdin or (not self._process.stdout):
            raise RuntimeError(f"LSP server '{self.name}' not running")
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
            raise TimeoutError(f"LSP request '{method}' timed out after {timeout}s")

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
                        future.set_exception(RuntimeError(f"LSP error: {message['error']}"))
                    else:
                        future.set_result(message.get("result"))
                elif "method" in message:
                    await self._notifications.put(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("LSP reader for '%s' stopped: %s", self.name, e)


def _encode_message(message: dict) -> bytes:
    body = json.dumps(message)
    body_bytes = body.encode("utf-8")
    return f"Content-Length: {len(body_bytes)}\r\n\r\n".encode() + body_bytes


def _severity_name(severity: int) -> str:
    return {1: "error", 2: "warning", 3: "information", 4: "hint"}.get(severity, "unknown")


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file://"):
        return uri[7:]
    return uri


def _position_to_offset(text: str, line: int, character: int) -> int:
    lines = text.split("\n")
    offset = 0
    for i, current_line in enumerate(lines):
        if i == line:
            return offset + min(character, len(current_line))
        offset += len(current_line) + 1
    return len(text)
