"""Loop detection — detects when the agent is stuck repeating the same tool calls.

Uses a sliding window over recent steps, computing a SHA-256 signature for
each (tool_name, params, result_output) tuple.  If any signature appears
more than MAX_REPEATS times within the window, the agent is considered stuck.
"""

from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)

WINDOW_SIZE = 10
MAX_REPEATS = 5


def _compute_signature(tool_name: str, params: dict, result_output: str) -> str:
    """Compute a stable SHA-256 signature for a tool interaction.

    The signature covers the tool name, normalized params, and result output.
    This ensures that identical tool calls with identical results are detected
    as loops, while different results (e.g. the tool making progress) are not.
    """
    h = hashlib.sha256()
    h.update(tool_name.encode("utf-8"))
    h.update(b"\x00")
    # Normalize params to a stable JSON string
    h.update(json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    h.update(b"\x00")
    h.update(result_output.encode("utf-8"))
    return h.hexdigest()


class LoopDetector:
    """Sliding-window loop detector for agent tool call sequences.

    Tracks the last WINDOW_SIZE tool interactions and detects if any
    identical (tool, params, output) signature repeats more than MAX_REPEATS
    times, indicating the agent is stuck in a loop.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        max_repeats: int = MAX_REPEATS,
    ) -> None:
        self.window_size = window_size
        self.max_repeats = max_repeats
        self._signatures: list[str] = []

    def record(self, tool_name: str, params: dict, result_output: str) -> None:
        """Record a tool interaction for loop detection."""
        sig = _compute_signature(tool_name, params, result_output)
        self._signatures.append(sig)
        # Keep only the window
        if len(self._signatures) > self.window_size:
            self._signatures = self._signatures[-self.window_size:]

    def is_loop_detected(self) -> bool:
        """Check if the agent is stuck in a loop.

        Returns True if any signature appears more than max_repeats times
        within the current window.
        """
        if len(self._signatures) < self.window_size:
            return False

        counts: dict[str, int] = {}
        for sig in self._signatures:
            counts[sig] = counts.get(sig, 0) + 1
            if counts[sig] > self.max_repeats:
                logger.warning(
                    "LOOP DETECTED: signature %s repeated %d times in window of %d",
                    sig[:16],
                    counts[sig],
                    self.window_size,
                )
                return True

        return False

    def reset(self) -> None:
        """Reset the detector (e.g. after user provides new context)."""
        self._signatures.clear()

    @property
    def window_fill(self) -> int:
        """How many entries are currently in the window."""
        return len(self._signatures)
