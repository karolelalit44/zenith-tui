"""Permission gate — risk-based tool approval with persistence."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import BaseTool
from .permission_store import PermissionStore
from zenith.core.errors import PermissionDenied

logger = logging.getLogger(__name__)

PERMISSION_TIMEOUT_SECONDS = 60


class PermissionGate:
    def __init__(
        self,
        auto_approve_low: bool = True,
        auto_approve_medium: bool = True,
        store: PermissionStore | None = None,
    ) -> None:
        self.auto_approve_low = auto_approve_low
        self.auto_approve_medium = auto_approve_medium
        self._store = store
        self._session_approved: set[str] = set()
        self._pending: dict[str, asyncio.Future] = {}

    def set_store(self, store: PermissionStore) -> None:
        self._store = store

    def check_sync(self, tool: BaseTool) -> bool:
        if tool.permission_level == "LOW":
            return self.auto_approve_low
        if tool.permission_level == "MEDIUM":
            return self.auto_approve_medium
        if tool.permission_level == "HIGH":
            return tool.name in self._session_approved
        return False

    async def check(self, tool: BaseTool) -> bool:
        if tool.permission_level == "LOW":
            return self.auto_approve_low
        if tool.permission_level == "MEDIUM":
            return self.auto_approve_medium
        if tool.permission_level == "HIGH":
            if tool.name in self._session_approved:
                return True
            if self._store:
                return await self._store.is_approved(tool.name)
            return False
        return False

    async def request_permission(
        self, tool: BaseTool, params: dict[str, Any], request_id: str | None = None
    ) -> bool:
        if await self.check(tool):
            return True

        future_key = request_id or tool.name
        loop = asyncio.get_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[future_key] = future

        try:
            approved = await asyncio.wait_for(future, timeout=PERMISSION_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "Permission request timed out: tool=%s request_id=%s",
                tool.name, request_id,
            )
            approved = False
        except asyncio.CancelledError:
            approved = False
        except Exception as e:
            logger.error("Permission request error: tool=%s error=%s", tool.name, e)
            approved = False
        finally:
            self._pending.pop(future_key, None)

        if approved:
            self._session_approved.add(tool.name)

        return approved

    def respond(self, request_id: str, approved: bool, remember: bool = False) -> bool:
        future = self._pending.get(request_id)
        if not future or future.done():
            return False
        future.set_result(approved)
        logger.info("Permission response: id=%s approved=%s", request_id, approved)
        return True

    def respond_first(self, approved: bool) -> bool:
        for key, future in self._pending.items():
            if not future.done():
                future.set_result(approved)
                return True
        return False

    def get_any_pending_key(self) -> str | None:
        for key, future in self._pending.items():
            if not future.done():
                return key
        return None

    def has_pending(self, request_id: str) -> bool:
        future = self._pending.get(request_id)
        return future is not None and not future.done()

    def pending_count(self) -> int:
        return sum(1 for f in self._pending.values() if not f.done())

    def cancel_all(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(asyncio.CancelledError())
        self._pending.clear()

    def approve_session(self, tool_name: str) -> None:
        self._session_approved.add(tool_name)

    def deny_session(self, tool_name: str) -> None:
        self._session_approved.discard(tool_name)

    def get_session_approved(self) -> set[str]:
        return self._session_approved.copy()
