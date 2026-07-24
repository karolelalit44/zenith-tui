"""Permission gate — risk-based tool approval."""

from __future__ import annotations

from .base import BaseTool
from zenith.core.errors import PermissionDenied


class PermissionGate:
    """Checks tool permission level against auto-approval settings."""

    def __init__(
        self,
        auto_approve_low: bool = True,
        auto_approve_medium: bool = False,
    ) -> None:
        self.auto_approve_low = auto_approve_low
        self.auto_approve_medium = auto_approve_medium

    def check(self, tool: BaseTool) -> bool:
        """Return True if the tool is auto-approved."""
        if tool.permission_level == "HIGH":
            return False  # Always require approval for HIGH
        if tool.permission_level == "MEDIUM":
            return self.auto_approve_medium
        if tool.permission_level == "LOW":
            return self.auto_approve_low
        return False

    def require(self, tool: BaseTool) -> None:
        """Raise PermissionDenied if the tool is not auto-approved."""
        if not self.check(tool):
            raise PermissionDenied(tool.name)
