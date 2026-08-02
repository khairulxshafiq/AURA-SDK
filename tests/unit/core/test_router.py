"""Unit tests for aura/core/router.py."""

from aura.core.router import Intent, router


def test_router_command_classification():
    assert router.classify("/start") == Intent.COMMAND
    assert router.classify("/help") == Intent.COMMAND


def test_router_url_classification():
    assert router.classify("https://example.com/news/123") == Intent.URL_SCRAPE
    assert router.classify("http://malaysia-today.com/article") == Intent.URL_SCRAPE


def test_router_ticker_classification():
    assert router.classify("MAYBANK") == Intent.TICKER_ANALYSIS
    assert router.classify("1155.KL") == Intent.TICKER_ANALYSIS
    assert router.classify("AAPL") == Intent.TICKER_ANALYSIS


def test_router_conversational_classification():
    assert router.classify("Bagi pandangan mengenai pasaran saham hari ini") == Intent.CONVERSATIONAL
    assert router.classify("Tulis artikel mengenai AI") == Intent.CONVERSATIONAL
