"""Feature flags configuration for AuraOne."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureFlags(BaseSettings):
    """Feature flags for instant module toggling and troubleshooting."""

    model_config = SettingsConfigDict(
        env_prefix="FLAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enable_trading: bool = Field(default=True)
    enable_content: bool = Field(default=True)
    enable_research: bool = Field(default=True)
    enable_media: bool = Field(default=True)
    enable_mcp: bool = Field(default=True)
    enable_hf_inference: bool = Field(default=True)
    enable_telegram_bot: bool = Field(default=True)
    enable_cost_governance: bool = Field(default=True)
