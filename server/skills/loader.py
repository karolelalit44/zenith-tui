from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
SKILL_ROOTS = ("skills", "agents/skills", ".zenith/skills", ".agent/skills")
MAX_SKILLS_IN_PROMPT = 20


def _extract_yaml_field(content: str, field: str) -> str | None:
    match = re.search(f"^{field}:\\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else None


def _extract_first_heading(content: str) -> str | None:
    match = re.search("^#{1,2}\\s+(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _summarize_skill(content: str, max_chars: int = 250) -> str:
    desc = _extract_yaml_field(content, "description")
    if desc:
        return desc[:max_chars]
    heading = _extract_first_heading(content)
    lines = content.strip().split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            body_start = i + 1
            for j in range(body_start, len(lines)):
                if lines[j].strip() == "---":
                    body_start = j + 1
                    break
            break
    text_lines = []
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped and (not stripped.startswith("```")):
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
    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()

    def find_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for root_name in SKILL_ROOTS:
            root_dir = self.root / root_name
            if not root_dir.is_dir():
                continue
            for skill_file in root_dir.rglob("SKILL.md"):
                if not skill_file.is_file():
                    continue
                if any(part.startswith(".") for part in skill_file.relative_to(self.root).parts):
                    continue
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    skills.append(
                        {
                            "path": skill_file.relative_to(self.root).as_posix(),
                            "content": content,
                            "directory": skill_file.parent.relative_to(self.root).as_posix(),
                            "size": len(content),
                            "summary": _summarize_skill(content),
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to read skill file %s: %s", skill_file, e)
        return skills

    def get_skill_prompt(self, max_skills: int = MAX_SKILLS_IN_PROMPT) -> str:
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
        return [s["directory"] for s in self.find_skills()]
