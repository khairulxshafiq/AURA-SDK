"""Typed Pydantic settings for AuraOne configuration."""

from __future__ import annotations

import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuraConfig(BaseSettings):
    """Central configuration for AuraOne operating system."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Operational settings
    env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    app_data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "data"
    )

    # LLM Provider settings
    gemini_api_key: str = Field(default="")
    gemini_api_key_1: str = Field(default="")
    gemini_api_key_2: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    openrouter_api_key: str = Field(default="")
    openrouter_fallback_model: str = Field(default="google/gemini-2.5-flash")

    # Interface settings
    telegram_bot_token: str = Field(default="")

    # External Integration settings
    airtable_api_key: str = Field(default="")
    airtable_base_id: str = Field(default="")
    airtable_table_name: str = Field(default="Content Station")
    gdrive_image_folder_id: str = Field(default="")
    gdrive_dump_folder_id: str = Field(default="")
    google_service_account_json: str = Field(default="")
    hf_token: str = Field(default="")
    apify_api_token: str = Field(default="")

    # Cost Governance & Budget settings
    daily_budget_cap_usd: float = Field(default=2.00)
    daily_token_limit: int = Field(default=500000)
    max_prompt_chars: int = Field(default=8000)

    def get_gemini_keys(self) -> list[str]:
        """Collect all configured Gemini API keys into a rotation pool."""
        keys = []
        if self.gemini_api_key:
            keys.append(self.gemini_api_key)
        if self.gemini_api_key_1 and self.gemini_api_key_1 not in keys:
            keys.append(self.gemini_api_key_1)
        if self.gemini_api_key_2 and self.gemini_api_key_2 not in keys:
            keys.append(self.gemini_api_key_2)
        return keys
