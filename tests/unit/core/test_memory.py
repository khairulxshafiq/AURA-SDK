"""Unit tests for 5-Tier Memory Architecture (aura/core/memory/)."""

import pytest
from aura.config import AuraConfig
from aura.core.memory.manager import MemoryManager


@pytest.mark.asyncio
async def test_memory_idempotency_store(temp_data_dir):
    config = AuraConfig(env="testing", app_data_dir=temp_data_dir)
    mgr = MemoryManager(config=config)

    assert await mgr.is_update_processed(12345) is False

    await mgr.mark_update_processed(12345)
    assert await mgr.is_update_processed(12345) is True

    # Duplicate mark should not error
    await mgr.mark_update_processed(12345)
    assert await mgr.is_update_processed(12345) is True

    mgr.close()


@pytest.mark.asyncio
async def test_memory_vector_remember_and_recall(temp_data_dir):
    config = AuraConfig(env="testing", app_data_dir=temp_data_dir)
    mgr = MemoryManager(config=config)

    row_id = await mgr.remember("Analisa saham Maybank menunjukkan trend bullish", metadata={"symbol": "MAYBANK"})
    assert row_id > 0

    hits = await mgr.recall("saham Maybank", k=1)
    assert len(hits) == 1
    assert "Maybank" in hits[0].text
    assert hits[0].similarity > 0.0

    mgr.close()


@pytest.mark.asyncio
async def test_memory_dedup_check(temp_data_dir):
    config = AuraConfig(env="testing", app_data_dir=temp_data_dir)
    mgr = MemoryManager(config=config)

    await mgr.remember("Draft artikel Facebook mengenai pelaburan saham", metadata={"platform": "facebook"})

    is_dup, hit = await mgr.dedup_check("Draft artikel Facebook mengenai pelaburan saham", threshold=0.80)
    assert is_dup is True
    assert hit is not None

    mgr.close()
