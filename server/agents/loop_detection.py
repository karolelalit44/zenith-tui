from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)
WINDOW_SIZE = 10
MAX_REPEATS = 2


def _compute_signature(tool_name: str, params: dict, result_output: str) -> str:
    h = hashlib.sha256()
    h.update(tool_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    h.update(b"\x00")
    h.update(result_output.encode("utf-8"))
    return h.hexdigest()


class LoopDetector:
    def __init__(self, window_size: int = WINDOW_SIZE, max_repeats: int = MAX_REPEATS) -> None:
        self.window_size = window_size
        self.max_repeats = max_repeats
        self._signatures: list[str] = []

    def record(self, tool_name: str, params: dict, result_output: str) -> None:
        sig = _compute_signature(tool_name, params, result_output)
        self._signatures.append(sig)
        if len(self._signatures) > self.window_size:
            self._signatures = self._signatures[-self.window_size :]

    def is_loop_detected(self) -> bool:
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
        self._signatures.clear()

    @property
    def window_fill(self) -> int:
        return len(self._signatures)
