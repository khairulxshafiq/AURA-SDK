"""Unit tests for aura/core/registry.py."""

from pydantic import BaseModel
from aura.core.registry import registry


class SampleInput(BaseModel):
    query: str


class SampleOutput(BaseModel):
    result: str


def dummy_tool(inp: SampleInput) -> SampleOutput:
    return SampleOutput(result=inp.query.upper())


def test_registry_tool_registration():
    registry.register_tool(
        domain="trading",
        name="dummy_tool",
        func=dummy_tool,
        input_schema=SampleInput,
        output_schema=SampleOutput,
    )

    assert "dummy_tool" in registry.list_tools()
    assert "trading" in registry.list_domains()
    assert registry.get_tool("dummy_tool") == dummy_tool
    in_s, out_s = registry.get_schemas("dummy_tool")
    assert in_s == SampleInput
    assert out_s == SampleOutput
