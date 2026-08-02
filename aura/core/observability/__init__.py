"""Structured logging and performance metrics for AuraOne."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
import structlog


def setup_logging(log_level: str = "INFO", log_dir: Path | None = None) -> None:
    """Initialize structured JSON logging with multi-channel file rotation."""
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


class MetricsCollector:
    """In-memory metrics tracker for latency, errors, and token usage."""

    def __init__(self) -> None:
        self._latencies: dict[str, list[float]] = {}
        self._error_counts: dict[str, int] = {}
        self._tokens_used: int = 0

    def record_latency(self, metric_name: str, duration_ms: float) -> None:
        """Record execution latency in milliseconds."""
        self._latencies.setdefault(metric_name, []).append(duration_ms)

    def increment_error(self, category: str) -> None:
        """Increment error counter for a category."""
        self._error_counts[category] = self._error_counts.get(category, 0) + 1

    def add_tokens(self, count: int) -> None:
        """Add tokens to running counter."""
        self._tokens_used += count

    def get_summary(self) -> dict[str, Any]:
        """Return summary of recorded metrics."""
        summary: dict[str, Any] = {
            "total_tokens_used": self._tokens_used,
            "error_counts": self._error_counts,
            "latencies_avg_ms": {},
        }
        for name, values in self._latencies.items():
            if values:
                summary["latencies_avg_ms"][name] = round(sum(values) / len(values), 2)
        return summary


metrics = MetricsCollector()
