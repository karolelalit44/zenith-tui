"""Module 04 additive interface-lock: serial file-mutation queue.

Reference: opencode tool/file-mutation-queue.ts (Semaphore) serializes file
mutations per workspace. Not yet wired into file tools (Phase 2) — this guards
the primitive itself.
"""

import asyncio

from server.toolkit.tools.file_mutation_queue import (
    FILE_MUTATION_QUEUE,
    FileMutationQueue,
)


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
