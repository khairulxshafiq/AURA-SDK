"""Decoupled async in-memory Event Bus for AuraOne."""

from __future__ import annotations

import asyncio
from typing import Any, Callable
import structlog

logger = structlog.get_logger("aura.core.events")


class EventBus:
    """Async event bus for handling system-wide decoupled events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Subscribe a callable handler to an event name."""
        self._subscribers.setdefault(event_name, []).append(handler)
        logger.debug("Subscribed event handler", event=event_name, handler=handler.__name__)

    async def emit(self, event_name: str, payload: dict[str, Any]) -> None:
        """Emit an event asynchronously without blocking callers."""
        trace_id = payload.get("trace_id", "none")
        handlers = self._subscribers.get(event_name, [])
        logger.info(
            "Event emitted",
            event=event_name,
            trace_id=trace_id,
            subscriber_count=len(handlers),
        )

        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(self._safe_async_call(handler, event_name, payload))
            else:
                try:
                    handler(payload)
                except Exception as exc:
                    logger.error(
                        "Sync event handler error",
                        event=event_name,
                        handler=handler.__name__,
                        error=str(exc),
                    )

    async def _safe_async_call(
        self, handler: Callable, event_name: str, payload: dict[str, Any]
    ) -> None:
        """Safely invoke an async event handler catching all exceptions."""
        try:
            await handler(payload)
        except Exception as exc:
            logger.error(
                "Async event handler error",
                event=event_name,
                handler=handler.__name__,
                error=str(exc),
            )


# Global singleton instance
bus = EventBus()
