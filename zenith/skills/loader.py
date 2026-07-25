"""SKILL.md loader — finds and loads skill definition files from workspace."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillLoader:
    """Finds and loads SKILL.md files from the workspace."""

    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()

    def find_skills(self) -> list[dict[str, Any]]:
        """Find all SKILL.md files in the workspace."""
        skills: list[dict[str, Any]] = []

        for skill_file in self.root.rglob("SKILL.md"):
            if not skill_file.is_file():
                continue
            # Skip hidden directories
            if any(part.startswith(".") for part in skill_file.relative_to(self.root).parts):
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                skills.append({
                    "path": str(skill_file.relative_to(self.root)),
                    "content": content,
                    "directory": str(skill_file.parent.relative_to(self.root)),
                    "size": len(content),
                })
            except Exception as e:
                logger.warning("Failed to read skill file %s: %s", skill_file, e)

        return skills

    def get_skill_prompt(self) -> str:
        """Build a prompt section from all loaded skills."""
        skills = self.find_skills()
        if not skills:
            return ""

        parts = ["## Loaded Skills", ""]
        for skill in skills:
            parts.append(f"### Skill: {skill['directory']}")
            parts.append(f"*Source: {skill['path']}*")
            parts.append("")
            parts.append(skill["content"])
            parts.append("")

        return "\n".join(parts)

    def get_skill_names(self) -> list[str]:
        """Get directory names of found skills."""
        return [s["directory"] for s in self.find_skills()]
