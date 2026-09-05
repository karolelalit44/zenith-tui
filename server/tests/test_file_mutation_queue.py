"""Module 04 additive interface-lock: serial file-mutation queue.

Reference: opencode tool/file-mutation-queue.ts (Semaphore) serializes file
mutations per workspace. Not yet wired into file tools (Phase 2) — this guards
the primitive itself.
"""

import asyncio
from contextlib import asynccontextmanager

from server.toolkit.tools import file_delete, file_edit, file_write
from server.toolkit.tools.file_delete import FileDeleteTool
from server.toolkit.tools.file_edit import FileEditTool
from server.toolkit.tools.file_mutation_queue import (
    FILE_MUTATION_QUEUE,
    FileMutationQueue,
)
from server.toolkit.tools.file_write import FileWriteTool


class TestFileMutationQueue:
    def test_mutations_on_same_workspace_are_serialized(self):
        queue = FileMutationQueue()
        root = "/workspace/a"

        in_flight = 0
        max_in_flight = 0

        async def mutation():
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

        async def main():
            await asyncio.gather(
                *(queue.run_exclusive(root, mutation) for _ in range(20))
            )

        asyncio.run(main())
        # Only ever one mutation running at a time within the workspace.
        assert max_in_flight == 1

    def test_different_workspaces_may_run_concurrently(self):
        queue = FileMutationQueue()

        in_flight = 0
        max_in_flight = 0

        async def mutation():
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

        async def main():
            await asyncio.gather(
                *(
                    queue.run_exclusive(f"/workspace/w{i}", mutation)
                    for i in range(5)
                )
            )

        asyncio.run(main())
        assert max_in_flight > 1  # distinct workspaces are not serialized together

    def test_context_manager_critical_section(self):
        queue = FileMutationQueue()
        n = 0

        async def main():
            async def guarded(label):
                nonlocal n
                async with queue.mutation("/w"):
                    n += 1
                    assert n == 1
                    await asyncio.sleep(0.01)
                    n -= 1

            await asyncio.gather(*(guarded(lbl) for lbl in ("a", "b", "c")))

        asyncio.run(main())
        assert n == 0

    def test_shared_default_queue_exists(self):
        # The daemon-wide queue is a singleton that independently serializes each
        # workspace; calling run_exclusive through it does not raise.
        async def noop():
            return "ok"

        result = asyncio.run(FILE_MUTATION_QUEUE.run_exclusive("/w", noop))
        assert result == "ok"

    def test_write_edit_and_delete_use_the_workspace_queue(self, tmp_path, monkeypatch):
        class TrackingQueue:
            def __init__(self):
                self.workspaces = []

            @asynccontextmanager
            async def mutation(self, workspace_root):
                self.workspaces.append(workspace_root)
                yield

        queue = TrackingQueue()
        for module in (file_write, file_edit, file_delete):
            monkeypatch.setattr(module, "FILE_MUTATION_QUEUE", queue)

        async def mutate():
            written = await FileWriteTool().execute(
                {"path": "queued.txt", "content": "before"}, str(tmp_path)
            )
            edited = await FileEditTool().execute(
                {"path": "queued.txt", "old_content": "before", "new_content": "after"},
                str(tmp_path),
            )
            deleted = await FileDeleteTool().execute({"path": "queued.txt"}, str(tmp_path))
            return written, edited, deleted

        results = asyncio.run(mutate())

        assert all(result.success for result in results)
        assert queue.workspaces == [str(tmp_path), str(tmp_path), str(tmp_path)]
