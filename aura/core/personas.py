"""Deterministic Persona Selector and Loader for AuraOne."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import structlog

logger = structlog.get_logger("aura.core.personas")


class PersonaSelector:
    """Loads YAML persona definitions and performs deterministic selection."""

    def __init__(self, personas_dir: Path | None = None) -> None:
        if personas_dir is None:
            personas_dir = Path(__file__).resolve().parent.parent / "personas"
        self.personas_dir = Path(personas_dir)
        self._personas: dict[str, dict[str, Any]] = {}
        self._load_personas()

    def _load_personas(self) -> None:
        if not self.personas_dir.exists():
            logger.warning("Personas directory not found", path=str(self.personas_dir))
            return

        for filepath in self.personas_dir.glob("*.yaml"):
            try:
                # Basic YAML reader without third party dependencies if standard open
                import json
                # Lightweight key-value parsing for simple YAML structures
                content = filepath.read_text(encoding="utf-8")
                persona_data = self._parse_simple_yaml(content)
                name = persona_data.get("name", filepath.stem)
                self._personas[name] = persona_data
                logger.debug("Loaded persona definition", name=name)
            except Exception as exc:
                logger.error("Failed to load persona file", file=filepath.name, error=str(exc))

    def _parse_simple_yaml(self, text: str) -> dict[str, Any]:
        """Simple line-by-line YAML parser for basic key-value structures."""
        data: dict[str, Any] = {}
        current_list_key = None
        for line in text.splitlines():
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                continue
            if ":" in line_strip and not line_strip.startswith("-"):
                parts = line_strip.split(":", 1)
                key = parts[0].strip()
                val = parts[1].strip().strip('"').strip("'")
                if val:
                    data[key] = val
                    current_list_key = None
                else:
                    data[key] = []
                    current_list_key = key
            elif line_strip.startswith("- ") and current_list_key:
                val = line_strip[2:].strip().strip('"').strip("'")
                data[current_list_key].append(val)
        return data

    def select_persona(self, platform: str, text_context: str = "") -> dict[str, Any]:
        """Deterministically select best persona by platform and context keywords."""
        plat = platform.lower().strip()
        if plat in ["facebook", "fb"]:
            return self._personas.get("viral_santai", self._get_fallback(plat))
        elif plat in ["threads", "x", "twitter"]:
            return self._personas.get("genz", self._get_fallback(plat))
        return self._personas.get("sakluma_brand", self._get_fallback(plat))

    def _get_fallback(self, platform: str) -> dict[str, Any]:
        return {
            "name": "default",
            "display_name": "Default Persona",
            "platform": platform,
            "tone": "Mesra dan profesional",
            "do_rules": [],
            "dont_rules": [],
        }


# Global singleton instance
persona_selector = PersonaSelector()
