"""Shared pytest configuration and offline FakeAgent fixtures for AuraOne."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import AsyncGenerator
import pytest
import pytest_asyncio

from aura.config import AuraConfig
from aura.core.memory.manager import MemoryManager


class FakeAgentResponse:
    """Mock response for FakeAgent."""

    def __init__(self, text_content: str = "Mocked offline agent response") -> None:
        self._text = text_content

    async def text(self) -> str:
        return self._text

    def __aiter__(self):
        async def _gen():
            yield self._text
        return _gen()


class FakeAgent:
    """Offline mock Agent fixture that returns pre-recorded responses without network calls."""

    def __init__(self, default_response: str = "Mocked offline agent response") -> None:
        self.default_response = default_response
        self.calls: list[str] = []

    async def chat(self, prompt: str) -> FakeAgentResponse:
        self.calls.append(prompt)
        return FakeAgentResponse(self.default_response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for data storage during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def fake_config(temp_data_dir: Path) -> AuraConfig:
    """Provide AuraConfig initialized with temp data directory."""
    return AuraConfig(
        env="testing",
        app_data_dir=temp_data_dir,
        gemini_api_key="test_key_dummy",
        daily_token_limit=100000,
    )


@pytest_asyncio.fixture
async def memory_manager(temp_data_dir: Path) -> AsyncGenerator[MemoryManager, None]:
    """Provide a fresh MemoryManager instance backed by temporary databases."""
    config = AuraConfig(env="testing", app_data_dir=temp_data_dir)
    mgr = MemoryManager(config=config)
    yield mgr
    mgr.close()


@pytest.fixture
def fake_agent() -> FakeAgent:
    """Provide FakeAgent offline fixture."""
    return FakeAgent()
