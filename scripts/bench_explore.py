"""WP6 §7 benchmark harness — measures explore efficiency on a fixed question set.

Runs the 10-question benchmark (5 relational, 5 discovery) against this
workspace and reports per-question tool calls + child tokens + wall time, plus
totals. This produces the numbers for docs/WP6_STRUCTURAL_RETRIEVAL_PLAN.md §10.

Usage:
    python scripts/bench_explore.py            # mock provider (pipeline sanity)
    python scripts/bench_explore.py --live     # real configured provider

The harness is provider-agnostic: `--live` loads the user's active provider via
the standard configuration layer; without it, a scripted in-repo provider runs
so the pipeline itself stays verifiable offline. Baseline-vs-after comparisons
are captured by checking out the two tree states and running this same script.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


QUESTIONS: list[tuple[str, str, str]] = [
    # (kind, question, thoroughness)
    ("relational", "who calls apply_evidence_rule and with what arguments?", "quick"),
    ("relational", "what breaks if run_scout changes its signature?", "quick"),
    ("relational", "which files reference CaptainOrchestrator?", "quick"),
    ("relational", "who consumes get_workspace_stats?", "quick"),
    ("relational", "what depends on build_task_envelope?", "quick"),
    ("discovery", "how does context compaction decide when to trigger?", "standard"),
    ("discovery", "where is session state persisted across restarts?", "standard"),
    ("discovery", "how does the scout report contract get validated?", "standard"),
    ("discovery", "where are explore token budgets enforced?", "standard"),
    ("discovery", "how does the mission brief reach the child prompt?", "standard"),
]

MOCK_REPORT = (
    'Mock synthesis.\n```json {"task_id":"b","agent_id":"apogee","status":"completed",'
    '"summary":"mock","findings":[],"evidence":[]} ```'
)


def _build_provider(live: bool):
    if not live:
        from server.providers.base import BaseProvider

        class _MockProvider(BaseProvider):
            model = "bench-mock"

            def __init__(self):
                super().__init__("bench-mock", "bench-mock")

            async def complete(self, messages, tools=None):
                flat = "\n".join(str(m.get("content", "")) for m in messages or [])
                if "OUTPUT CONTRACT" in flat:
                    return MOCK_REPORT
                return "Proceed."

            async def stream(self, messages, tools=None, tool_choice=None, response_format=None):
                text = await self.complete(messages)
                for ch in text:
                    yield (ch, None)

            async def validate(self):
                return True

            async def list_models(self):
                return ["bench-mock"]

        return _MockProvider()

    from server.config.loader import load_config
    from server.providers import create_provider  # type: ignore[attr-defined]

    cfg = load_config()
    provider = create_provider(cfg.active_provider, cfg)
    return provider


async def _run_one(provider, config, question: str, thoroughness: str) -> dict:
    from server.toolkit import create_default_registry
    from server.toolkit.tools.explore_tool import ExploreTool

    registry = create_default_registry(provider=provider, config=config)
    tool = ExploreTool(
        config=config,
        provider=provider,
        tool_registry=registry,
        weak_model=getattr(config, "weak_model", None),
    )
    started = time.monotonic()
    result = await tool.execute(
        {"objective": question, "thoroughness": thoroughness}, config.workspace_root
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    meta = result.metadata or {}
    return {
        "question": question[:60],
        "success": bool(result.success),
        "status": meta.get("explore_status"),
        "tool_calls": int(meta.get("tool_calls") or 0),
        "tokens_used": int(meta.get("tokens_used") or 0),
        "elapsed_ms": elapsed_ms,
        "output_chars": len(result.output or ""),
    }


async def _main(live: bool) -> int:
    from server.config.settings import AppSettings

    workspace = Path.cwd()
    provider = _build_provider(live)
    config = AppSettings(workspace_root=str(workspace))
    rows: list[dict] = []
    for kind, question, thoroughness in QUESTIONS:
        row = await _run_one(provider, config, question, thoroughness)
        row["kind"] = kind
        row["thoroughness"] = thoroughness
        rows.append(row)
        print(json.dumps(row), flush=True)

    totals = {
        "questions": len(rows),
        "successful": sum(1 for r in rows if r["success"]),
        "total_tool_calls": sum(r["tool_calls"] for r in rows),
        "total_tokens": sum(r["tokens_used"] for r in rows),
        "total_elapsed_ms": sum(r["elapsed_ms"] for r in rows),
    }
    print("\n=== TOTALS ===")
    print(json.dumps(totals, indent=2))
    print(
        "\nPaste this block into docs/WP6_STRUCTURAL_RETRIEVAL_PLAN.md §10 "
        "(label it baseline or structural-on per the tree state you ran)."
    )
    return 0 if totals["successful"] == len(rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use the configured live provider")
    args = parser.parse_args()
    return asyncio.run(_main(args.live))


if __name__ == "__main__":
    raise SystemExit(main())
