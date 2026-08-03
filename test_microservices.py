"""
Automated Integration & Microservices Verification Test Suite for AURA-SDK
Tests:
1. AMIRA microservice endpoints & trading engine logic.
2. ADELIA microservice endpoints & content engine logic.
3. AURA Router fallback & delegation dispatchers.
"""
import unittest
import sys
import os

# Add AuraOne, amira-app, adelia-app to sys.path for testing
sys.path.insert(0, os.path.abspath("AuraOne"))
sys.path.insert(0, os.path.abspath("amira-app"))
sys.path.insert(0, os.path.abspath("adelia-app"))

import importlib.util

def load_module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

amira_engine = load_module_from_path("amira_trading_engine", os.path.abspath("amira-app/trading_engine.py"))
adelia_engine = load_module_from_path("adelia_content_engine", os.path.abspath("adelia-app/content_engine.py"))

class TestAmiraEngine(unittest.TestCase):
    def test_resolve_symbol(self):
        res = amira_engine.resolve_symbol("Maybank")
        self.assertIn("matches", res)
        self.assertEqual(res["matches"][0]["symbol"], "1155")
        self.assertIn("disclaimer", res)
        self.assertIn("AMIRA BUKAN advisor", res["disclaimer"])

    def test_analyze_counter_advisory_guardrail(self):
        res = amira_engine.analyze_counter("1155", mode="swing")
        self.assertIn("disclaimer", res)
        self.assertIn("DYOR", res["disclaimer"])
        self.assertEqual(res["mode"], "swing")

    def test_screener(self):
        res = amira_engine.screen_stocks(mode="swing", limit=3)
        self.assertIn("results", res)
        self.assertGreater(len(res["results"]), 0)

class TestAdeliaEngine(unittest.TestCase):
    def test_ensure_https(self):
        url = adelia_engine._ensure_https("http://example.com/image.jpg")
        self.assertTrue(url.startswith("https://"))

    def test_build_fb_prompt(self):
        prompt = adelia_engine.build_fb_prompt("fb_berita", "Sample Master Draft Body")
        self.assertIn("FB_BERITA", prompt)
        self.assertIn("Sample Master Draft Body", prompt)


class TestRouterDelegation(unittest.TestCase):
    def test_trading_service_imports(self):
        import tools.trading_service as ts
        res = ts.resolve_symbol("Aemulus")
        self.assertIn("matches", res)

    def test_web_scraper_imports(self):
        import tools.web_scraper as ws
        self.assertTrue(callable(ws.scrape_url))

if __name__ == "__main__":
    unittest.main()
