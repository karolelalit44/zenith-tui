from __future__ import annotations

import platform
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class PromptTemplate:
    _VAR_RE = re.compile("\\{\\{(\\w+)\\}\\}")

    def __init__(self, text: str) -> None:
        self._template = text
        self._variables: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self._variables[key] = value

    def render(self) -> str:
        result = self._template
        for key, value in self._variables.items():
            result = result.replace("{{" + key + "}}", value)
        return result

    @property
    def variables(self) -> list[str]:
        return list(set(self._VAR_RE.findall(self._template)))


class PromptBuilder:
    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._templates: dict[str, PromptTemplate] = {}

    def load_templates(self, directory: Path) -> None:
        for file in directory.glob("*.md"):
            template = PromptTemplate(file.read_text())
            self._templates[file.stem] = template

    def register(self, name: str, template: PromptTemplate) -> None:
        self._templates[name] = template

    def get(self, name: str) -> PromptTemplate | None:
        return self._templates.get(name)

    async def build_system_prompt(
        self, role: str, workspace_root: str, context_files: list[str] | None = None
    ) -> str:
        template = self._templates.get(f"system_{role}") or self._templates.get("system")
        if template is None:
            return ""
        template.set("workspace_root", workspace_root)
        template.set("date", datetime.now(UTC).strftime("%Y-%m-%d"))
        template.set("platform", sys.platform)
        template.set("os", f"{platform.system()} {platform.release()}")
        template.set("python_version", platform.python_version())
        if context_files:
            parts: list[str] = []
            for fp in context_files:
                p = Path(fp)
                if p.exists():
                    parts.append(f"## {p.name}\n\n{p.read_text(errors='replace')}")
            template.set("context_files", "\n\n".join(parts))
        else:
            template.set("context_files", "")
        return template.render()

    async def build_user_prompt(
        self, prompt: str, repo_map: str | None = None, file_context: list[str] | None = None
    ) -> str:
        parts = [prompt]
        if repo_map:
            parts.append(f"\n\n## Repository Map\n\n{repo_map}")
        if file_context:
            file_parts: list[str] = []
            for fp in file_context:
                p = Path(fp)
                if p.exists():
                    content = p.read_text(errors="replace")
                    file_parts.append(f"### {p.name}\n\n```\n{content}\n```")
            if file_parts:
                parts.append("\n\n## File Context\n\n" + "\n\n".join(file_parts))
        return "".join(parts)
