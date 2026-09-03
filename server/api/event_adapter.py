from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from server.domain.events import Event

logger = logging.getLogger(__name__)


async def iter_client_events(stream: AsyncIterator[Event]) -> AsyncIterator[Event]:
    """Forward the upstream event stream to the client transport unmodified.

    A no-op passthrough retained for a stable call site and future transport
    adaptation.
    """
    async for event in stream:
        yield event
