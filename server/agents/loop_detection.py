from __future__ import annotations

import hashlib
import json
import logging

from server.config.constants import (
    LOOP_DETECTION_MAX_REPEATS,
    LOOP_DETECTION_WINDOW_SIZE,
    LOOP_IDENTICAL_CONSECUTIVE_LIMIT,
)

logger = logging.getLogger(__name__)


def _compute_signature(tool_name: str, params: dict, result_output: str) -> str:
    h = hashlib.sha256()
    h.update(tool_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    h.update(b"\x00")
    h.update(result_output.encode("utf-8"))
    return h.hexdigest()


class LoopDetector:
    def __init__(
        self,
        window_size: int = LOOP_DETECTION_WINDOW_SIZE,
        max_repeats: int = LOOP_DETECTION_MAX_REPEATS,
        identical_limit: int = LOOP_IDENTICAL_CONSECUTIVE_LIMIT,
    ) -> None:
        self.window_size = window_size
        self.max_repeats = max_repeats
        self.identical_limit = identical_limit
        self._signatures: list[str] = []
        self._consecutive_sig: str | None = None
        self._consecutive_count = 0

    def record(self, tool_name: str, params: dict, result_output: str) -> None:
        sig = _compute_signature(tool_name, params, result_output)
        self._signatures.append(sig)
        if len(self._signatures) > self.window_size:
            self._signatures = self._signatures[-self.window_size :]
        if sig == self._consecutive_sig:
            self._consecutive_count += 1
        else:
            self._consecutive_sig = sig
            self._consecutive_count = 1

    def is_loop_detected(self) -> bool:
        if self._consecutive_count >= self.identical_limit:
            logger.warning(
                "LOOP DETECTED: signature %s repeated %d consecutive times",
                str(self._consecutive_sig)[:16],
                self._consecutive_count,
            )
            return True
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
        self._consecutive_sig = None
        self._consecutive_count = 0

    @property
    def window_fill(self) -> int:
        return len(self._signatures)
