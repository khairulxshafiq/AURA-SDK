"""Capability and Tool Registry for AuraOne."""

from __future__ import annotations

from typing import Any, Callable, Type
from pydantic import BaseModel
import structlog

logger = structlog.get_logger("aura.core.registry")


class CapabilityRegistry:
    """Dynamic registry for domain tools, schemas, and capabilities."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, tuple[Type[BaseModel], Type[BaseModel]]] = {}
        self._domains: set[str] = set()

    def register_tool(
        self,
        domain: str,
        name: str,
        func: Callable,
        input_schema: Type[BaseModel],
        output_schema: Type[BaseModel],
    ) -> None:
        """Register a tool callable with explicit domain and Pydantic schemas."""
        self._tools[name] = func
        self._schemas[name] = (input_schema, output_schema)
        self._domains.add(domain)
        logger.info("Tool registered", domain=domain, tool_name=name)

    def get_tool(self, name: str) -> Callable:
        """Retrieve registered tool function by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered in CapabilityRegistry.")
        return self._tools[name]

    def get_schemas(self, name: str) -> tuple[Type[BaseModel], Type[BaseModel]]:
        """Retrieve (InputSchema, OutputSchema) tuple for a tool."""
        if name not in self._schemas:
            raise KeyError(f"Schemas for tool '{name}' not found.")
        return self._schemas[name]

    def list_tools(self, domain: str | None = None) -> list[str]:
        """List all tool names, optionally filtered by domain."""
        if domain is None:
            return list(self._tools.keys())
        return [
            name
            for name, func in self._tools.items()
            if getattr(func, "__domain__", None) == domain
        ]

    def list_domains(self) -> list[str]:
        """List all registered domains."""
        return sorted(list(self._domains))


# Global singleton instance
registry = CapabilityRegistry()
