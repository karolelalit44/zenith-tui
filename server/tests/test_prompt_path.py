"""Tests for the additive single prompt path (module 02, prompt_sending).

Covers the feature-doc guarantees:
- ``resolve_user_parts`` resolves text/file/folder/inline/agent/MCP parts at
  prompt time (opencode resolveUserPart / codex ResponseItem style).
- ``PromptPath.send`` is a single path: parts -> SimpleLoop, no delegation
  branching.
- ``build_clean_system_context`` assembles the tagged module-15 surface.
"""

import os

import pytest

from server.agents.prompt_path import (
    PromptPath,
    build_clean_system_context,
    resolve_user_parts,
)
from server.config.providers import ProviderConfig
from server.config.settings import AppSettings
from server.domain.events import EventKind
from server.providers.base import BaseProvider
from server.toolkit import create_default_registry


class _EchoProvider(BaseProvider):
    def __init__(self, response):
        super().__init__("echo", "echo-model")
        self.response = response
        self.call_count = 0

    async def complete(self, messages, tools=None):
        self.call_count += 1
        return self.response

    async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
        response = await self.complete(messages, tools)
        for char in response:
            yield (char, None)

    async def validate(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return ["echo-model"]


@pytest.fixture
def test_config(temp_dir):
    return AppSettings(
        providers={"test": ProviderConfig(model="test-model", is_active=True)},
        active_provider="test",
        home_dir=str(temp_dir / "test.db"),
        workspace_root=str(temp_dir),
    )


@pytest.mark.asyncio
async def test_resolve_user_parts_text_and_file(test_config):
    fpath = os.path.join(test_config.workspace_root, "notes.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("hello notes")

    combined, parts = await resolve_user_parts(
        "Read these notes", [{"kind": "file", "path": "notes.txt"}], test_config.workspace_root
    )
    assert "hello notes" in combined
    assert parts[0] == {"type": "text"}
    assert parts[1]["type"] == "file"
    assert parts[1]["resolved"] is True


@pytest.mark.asyncio
async def test_resolve_user_parts_inline_overrides_file(test_config):
    combined, parts = await resolve_user_parts(
        "",
        [{"kind": "file", "path": "missing.txt", "content": "inline body"}],
        test_config.workspace_root,
    )
    assert "inline body" in combined
    assert parts[0]["resolved"] == "inline"


@pytest.mark.asyncio
async def test_resolve_user_parts_missing_file_reports_error(test_config):
    combined, parts = await resolve_user_parts(
        "", [{"kind": "file", "path": "nope.txt"}], test_config.workspace_root
    )
    assert "error" in combined
    assert parts[0]["resolved"] is False
    assert parts[0]["error"]


@pytest.mark.asyncio
async def test_resolve_user_parts_folder_scope(test_config):
    sub = os.path.join(test_config.workspace_root, "proj")
    os.makedirs(sub, exist_ok=True)
    with open(os.path.join(sub, "a.py"), "w", encoding="utf-8") as f:
        f.write("x = 1")

    combined, parts = await resolve_user_parts(
        "", [{"kind": "folder", "path": "proj"}], test_config.workspace_root
    )
    assert "a.py" in combined
    assert parts[0]["type"] == "folder"
    assert parts[0]["resolved"] is True


@pytest.mark.asyncio
async def test_prompt_path_send_is_single_path(test_config):
    provider = _EchoProvider("No tools, just answering.")
    path = PromptPath(test_config, provider, tool_registry=create_default_registry())

    events = []
    async for event in path.send("Explain x", "s1", attachments=[], mode="build"):
        events.append(event)

    assert provider.call_count == 1, "single prompt path streams exactly one turn"
    messages = [e for e in events if e.kind == EventKind.MESSAGE]
    assert any("just answering" in e.data.get("text", "") for e in messages)


def test_build_clean_system_context_uses_module15_surface(test_config):
    parts = build_clean_system_context(mode="build", workspace_root=test_config.workspace_root)
    assert parts, "rendered context parts should be non-empty"
    joined = "\n".join(parts)
    assert "<instructions>" in joined, "must be assembled from tagged sections (module 15)"
