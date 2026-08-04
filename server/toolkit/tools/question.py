from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)
_question_callback: Callable[[str, list[str]], Awaitable[str]] | None = None


def set_question_callback(callback: Callable[[str, list[str]], Awaitable[str]] | None) -> None:
    global _question_callback
    _question_callback = callback


class QuestionTool(BaseTool):
    name = "question"
    description = "Ask user interactive question"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question text"},
                "options": {
                    "type": "array",
                    "description": "Multiple-choice options",
                    "items": {"type": "string"},
                },
            },
            "required": ["question"],
        }

    async def execute(self, params: dict[str, Any], workspace_root: str) -> ToolResult:
        question = params.get("question", "")
        options = params.get("options", [])
        if not question:
            return ToolResult(success=False, error="No question provided")
        if _question_callback is None:
            return ToolResult(
                success=True,
                output=f"[Question asked but no interactive handler available]\n{question}",
                metadata={"question": question, "options": options, "answered": False},
            )
        try:
            answer = await _question_callback(question, options)
            return ToolResult(
                success=True,
                output=f"User answered: {answer}",
                metadata={
                    "question": question,
                    "options": options,
                    "answer": answer,
                    "answered": True,
                },
            )
        except Exception as e:
            logger.warning("Question callback failed: %s", e)
            return ToolResult(success=False, error=f"Failed to get user answer: {e}")
