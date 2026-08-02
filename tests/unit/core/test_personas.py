"""Unit tests for aura/core/personas.py."""

from aura.core.personas import persona_selector


def test_persona_selector_facebook():
    persona = persona_selector.select_persona(platform="facebook")
    assert persona["name"] == "viral_santai"
    assert persona["platform"] == "facebook"
    assert "viral_santai" in persona_selector._personas


def test_persona_selector_threads():
    persona = persona_selector.select_persona(platform="threads")
    assert persona["name"] == "genz"
    assert persona["platform"] == "threads"


def test_persona_selector_fallback():
    persona = persona_selector.select_persona(platform="unknown_platform")
    assert persona["name"] == "sakluma_brand"
