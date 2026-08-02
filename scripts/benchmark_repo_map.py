"""Benchmark the repo-map path: first-build tokens/time vs repeat-turn (cached).

Before this optimization: a 55-char prompt cost 6,348 tokens (5,184 of them the
repo map scanning ref_repo/) and ~55s to build. Run from the repo root:

    python scripts/benchmark_repo_map.py

Exits non-zero if the repeat-turn path is slower than the FIRST_SLOW_MS budget.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from server.agents.context import ContextManager, _get_repo_map_instance
from server.config.settings import AppSettings
from server.providers.token_counter import TokenCounter

# The optimization target: repeat turns must be far below this.
FIRST_SLOW_MS = 5000
REPEAT_SLOW_MS = 50

BASELINE_TOKENS = 6348
BASELINE_SECONDS = 55.0


def _config(root: str) -> AppSettings:
    return AppSettings(
        db_path=str(Path(root) / "benchmark.db"),
        workspace_root=root,
        max_context_tokens=128000,
        repo_map_tokens=None,  # auto -> clamp(ctx/8, 1024, 4096) = 1024
    )


def main() -> int:
    root = r"D:\vdo\code\zenith-frontend-tui"
    tc = TokenCounter()
    model = "gpt-4o"

    cm = ContextManager(_config(root))

    # First build (cold: enumeration + symbols + budget fitting)
    t0 = time.monotonic()
    messages = cm.build_messages(history=[], system_prompt="SYS", new_prompt="hi", model=model)
    first_s = time.monotonic() - t0
    map_tokens = cm.token_counter.count(messages[1]["content"], model) if len(messages) > 1 else 0

    # Repeat turn (should hit ContextManager cache entirely)
    t0 = time.monotonic()
    cm.build_messages(history=[], system_prompt="SYS", new_prompt="hello again", model=model)
    repeat_s = time.monotonic() - t0

    repo = _get_repo_map_instance(root)
    file_count = repo.get_file_count()
    summary = repo.get_summary()

    print("=== Repo map benchmark (zenith-frontend-tui) ===")
    print(f"  files enumerated:        {file_count}")
    print(f"  summary:                 {summary}")
    print(f"  first-build map tokens:  {map_tokens}   (baseline was {BASELINE_TOKENS})")
    print(f"  first build:             {first_s * 1000:8.1f} ms  (baseline was {BASELINE_SECONDS * 1000:.0f} ms)")
    print(f"  repeat turn (cached):    {repeat_s * 1000:8.2f} ms")
    print(f"  total prompt tokens:     {cm.token_counter.count_messages(messages, model)}")

    ok = first_s * 1000 < FIRST_SLOW_MS and repeat_s * 1000 < REPEAT_SLOW_MS
    print(f"\n  verdict:                 {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
