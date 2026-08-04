from __future__ import annotations

import logging

logger = logging.getLogger("zenith.persistence")


def _fmt(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace(" ", "_")
    return f'"{text}"'


def db_log(
    operation: str,
    *,
    table: str = "",
    status: str = "ok",
    duration_ms: float | None = None,
    error: str = "",
    version: str = "",
    level: int = logging.INFO,
    **fields: object,
) -> None:
    parts = [f"db.{operation}", f"status={status}"]
    if table:
        parts.append(f"table={_fmt(table)}")
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.2f}")
    if version:
        parts.append(f"version={_fmt(version)}")
    for key, value in fields.items():
        parts.append(f"{key}={_fmt(value)}")
    if error:
        parts.append(f"error={_fmt(error)}")
    logger.log(level, " ".join(parts))


