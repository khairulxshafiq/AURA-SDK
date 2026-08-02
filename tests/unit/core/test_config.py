"""Unit tests for aura/config.py and aura/flags.py."""

from aura.config import AuraConfig
from aura.flags import FeatureFlags


def test_aura_config_defaults():
    config = AuraConfig()
    assert config.gemini_model == "gemini-2.5-flash"
    assert config.daily_budget_cap_usd == 2.00
    assert config.daily_token_limit == 500000


def test_gemini_keys_collection():
    config = AuraConfig(
        gemini_api_key="key_main",
        gemini_api_key_1="key_1",
        gemini_api_key_2="key_2",
    )
    keys = config.get_gemini_keys()
    assert len(keys) == 3
    assert keys == ["key_main", "key_1", "key_2"]


def test_feature_flags_defaults():
    flags = FeatureFlags()
    assert flags.enable_trading is True
    assert flags.enable_content is True
    assert flags.enable_cost_governance is True
