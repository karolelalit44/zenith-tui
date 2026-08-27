"""
E2E Context & Session Persistence Test — Launcher

Runs Part 1 then Part 2 in sequence.
Part 1: creates a session, sends 3 prompts, logs everything.
Part 2: resumes the same session in a new connection, sends 2 more prompts.

Prerequisites:
  - Server running on ws://127.0.0.1:8765/ws
  - websockets and httpx installed (pip install websockets httpx)

Usage:
  python server/tests/test_context_session_e2e_run_all.py

Output:
  server/tests/e2e_context_log.txt  (plain-text log of the entire flow)
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from server.tests.test_context_session_e2e_part1 import run_part1
from server.tests.test_context_session_e2e_part2 import run_part2


async def main() -> None:
    print("=" * 80)
    print("  E2E CONTEXT & SESSION PERSISTENCE TEST")
    print("  Part 1: Create session → 3 prompts → log context")
    print("  Part 2: Resume session → 2 more prompts → verify persistence")
    print("=" * 80)
    print()

    t0 = time.monotonic()

    # ── Part 1 ───────────────────────────────────────────────────────────
    print("Running Part 1 (new session + 3 prompts)...")
    try:
        session_id = await run_part1()
        print(f"\nPart 1 DONE. Session ID: {session_id}\n")
    except Exception as e:
        print(f"\nPart 1 FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Brief pause between parts (simulates user closing and reopening UI)
    print("Pausing 3s between Part 1 and Part 2...")
    await asyncio.sleep(3)

    # ── Part 2 ───────────────────────────────────────────────────────────
    print("\nRunning Part 2 (resume session + 2 prompts)...")
    try:
        ok = await run_part2()
        elapsed = time.monotonic() - t0
        print(f"\nPart 2 DONE. Result: {'PASS' if ok else 'FAIL'} ({elapsed:.1f}s total)")
    except Exception as e:
        print(f"\nPart 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 80)
    if ok:
        print("  ALL CHECKS PASSED")
    else:
        print("  SOME CHECKS FAILED — see log for details")
    print(f"  Log file: {Path(__file__).resolve().parent / 'e2e_context_log.txt'}")
    print("=" * 80)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
