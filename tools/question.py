"""Question tool — allows the agent to ask the user a question interactively.

Unlike other tools that return results, this tool sends a question to the
user via an event and waits for their response.  The agent can specify
multiple-choice options or allow free-form answers.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# The question callback is set at agent initialization time.
# It receives (question, options) and returns the user's answer.
_question_callback: Callable[[str, list[str]], Awaitable[str]] | None = None


def set_question_callback(callback: Callable[[str, list[str]], Awaitable[str]] | None) -> None:
    """Set the callback for handling interactive questions."""
    global _question_callback
    _question_callback = callback


class QuestionTool(BaseTool):
    name = "question"
    description = "Ask the user a question interactively and wait for their response"

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user",
                },
                "options": {
                    "type": "array",
                    "description": "Optional list of multiple-choice options the user can choose from",
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
            # Fallback: just return the question without waiting
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
                metadata={"question": question, "options": options, "answer": answer, "answered": True},
            )
        except Exception as e:
            logger.warning("Question callback failed: %s", e)
            return ToolResult(
                success=False,
                error=f"Failed to get user answer: {e}",
            )
