"""SKILL.md loader — finds and loads skill definition files from workspace."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _extract_yaml_field(content: str, field: str) -> str | None:
    """Extract a YAML frontmatter field value."""
    match = re.search(rf"^{field}:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else None


def _extract_first_heading(content: str) -> str | None:
    """Extract the first markdown heading (## or #) line."""
    match = re.search(r"^#{1,2}\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _summarize_skill(content: str, max_chars: int = 250) -> str:
    """Return a brief summary of the skill content (first ~max_chars meaningful characters)."""
    # Try frontmatter description first
    desc = _extract_yaml_field(content, "description")
    if desc:
        return desc[:max_chars]

    # Try first heading + first non-empty, non-frontmatter line
    heading = _extract_first_heading(content)
    lines = content.strip().split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            body_start = i + 1
            # find closing ---
            for j in range(body_start, len(lines)):
                if lines[j].strip() == "---":
                    body_start = j + 1
                    break
            break

    text_lines = []
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped and not stripped.startswith("```"):
            text_lines.append(stripped)
            if sum(len(t) for t in text_lines) >= max_chars:
                break

    summary_parts = []
    if heading:
        summary_parts.append(heading)
    if text_lines:
        summary_parts.append(text_lines[0][:max_chars])
    result = " — ".join(summary_parts) if summary_parts else ""
    return result[:max_chars] if result else ""


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
                    "summary": _summarize_skill(content),
                })
            except Exception as e:
                logger.warning("Failed to read skill file %s: %s", skill_file, e)

        return skills

    def get_skill_prompt(self, max_chars_per_skill: int = 6000) -> str:
        """Build a prompt section from all loaded skills.

        Each skill's full content is embedded (capped per skill) so the model
        can use the skill without an extra read round-trip.
        """
        skills = self.find_skills()
        if not skills:
            return ""

        parts = [
            "## Loaded Skills",
            "",
            "Each skill below is available in full below its source path.",
            "",
        ]
        for skill in skills:
            parts.append(f"### Skill: {skill['directory']}")
            parts.append(f"*Source: {skill['path']}*")
            content = skill.get("content") or ""
            if len(content) > max_chars_per_skill:
                content = content[:max_chars_per_skill]
                parts.append("[skill content truncated]")
            parts.append(content or skill.get("summary", ""))
            parts.append("")

        return "\n".join(parts)

    def get_skill_names(self) -> list[str]:
        """Get directory names of found skills."""
        return [s["directory"] for s in self.find_skills()]
