"""SKILL.md loader — finds and loads skill definition files from workspace."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Skills are only discovered under these workspace-relative directories
# (opencode/pi/crush convention). This prevents arbitrary SKILL.md files
# vendored inside dependencies (e.g. .venv site-packages) from polluting
# the system prompt.
SKILL_ROOTS = ("skills", "agents/skills", ".zenith/skills", ".agent/skills")

# Skills are injected metadata-only: name, source path, one-line summary.
# The full body is loaded on demand (e.g. via file_read of the source path),
# so a skill can never blow the prompt budget. Mirrors opencode/pi/crush.
MAX_SKILLS_IN_PROMPT = 20


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
        """Find all SKILL.md files under the configured skill directories."""
        skills: list[dict[str, Any]] = []

        for root_name in SKILL_ROOTS:
            root_dir = self.root / root_name
            if not root_dir.is_dir():
                continue
            for skill_file in root_dir.rglob("SKILL.md"):
                if not skill_file.is_file():
                    continue
                # Skip hidden directories
                if any(part.startswith(".") for part in skill_file.relative_to(self.root).parts):
                    continue

                try:
                    content = skill_file.read_text(encoding="utf-8")
                    skills.append({
                        "path": skill_file.relative_to(self.root).as_posix(),
                        "content": content,
                        "directory": skill_file.parent.relative_to(self.root).as_posix(),
                        "size": len(content),
                        "summary": _summarize_skill(content),
                    })
                except Exception as e:
                    logger.warning("Failed to read skill file %s: %s", skill_file, e)

        return skills

    def get_skill_prompt(self, max_skills: int = MAX_SKILLS_IN_PROMPT) -> str:
        """Build a metadata-only prompt section from all loaded skills.

        Only the source path + summary are embedded so the prompt stays tiny;
        the model reads the full SKILL.md on demand (the source path is given).
        """
        skills = self.find_skills()
        if not skills:
            return ""

        parts = [
            "## Loaded Skills",
            "",
            "Each skill below is available — read its source file to use it.",
            "",
        ]
        for skill in skills[:max_skills]:
            parts.append(f"### Skill: {skill['directory']}")
            parts.append(f"*Source: {skill['path']}*")
            summary = skill.get("summary") or ""
            if summary:
                parts.append(summary)
            parts.append("")

        return "\n".join(parts)

    def get_skill_names(self) -> list[str]:
        """Get directory names of found skills."""
        return [s["directory"] for s in self.find_skills()]
