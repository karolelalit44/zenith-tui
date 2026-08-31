"""Serial file-mutation queue (additive interface-lock, module 04).

Reference: opencode ``tool/file-mutation-queue.ts`` serializes file mutations so
only one runs at a time (Semaphore), avoiding races when tools execute in
parallel; codex likewise applies edits sequentially. zenith's file tools declare
``concurrency_group = WORKSPACE_MUTATION`` but do not actually serialize today.

This module provides the additive serialization primitive. It is NOT yet wired
into file_write/file_edit/file_delete (that is Phase 2, which changes behavior
and needs coordination); consumers adopting the reference contract may lock via
:func:`run_exclusive` / :func:`mutation`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class FileMutationQueue:
    """Serialize file mutations per workspace.

    Mutations are keyed by resolved workspace root, so mutations on *different*
    workspaces may proceed concurrently while mutations on the *same* workspace
    are strictly serialized (one at a time), matching opencode's Semaphore.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    @staticmethod
    def _key(workspace_root: str) -> str:
        return str(Path(workspace_root).resolve())

    @asynccontextmanager
    async def mutation(self, workspace_root: str | None = None) -> Iterator[None]:
        """Acquire the per-workspace mutation lock.

        Yield a critical section within which exactly one file mutation for this
        workspace executes at a time.
        """
        if workspace_root is None:
            lock = await self._lock_for("__global__")
        else:
            lock = await self._lock_for(self._key(workspace_root))
        async with lock:
            yield

    async def run_exclusive(
        self,
        workspace_root: str,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run ``fn`` while holding the workspace's mutation lock (serialized)."""
        async with self.mutation(workspace_root):
            return await fn(*args, **kwargs)


# Module-level default queue shared by the daemon process. Each workspace is
# serialized independently against this single instance.
FILE_MUTATION_QUEUE: FileMutationQueue = FileMutationQueue()
