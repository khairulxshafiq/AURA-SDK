# AURA v5 (AuraAgent) Migration & Blueprints Reference

This directory contains the exact, verified code listings and implementation blueprints migrated from the previous **AURA v5 (`AuraAgent`)** codebase. 

Use these blueprints to easily port and integrate each capability into the modern **AURA-SDK (AuraOne)** codebase powered by the Google Antigravity SDK.

## Capabilities Index

1. [Web Scraping & Search Blueprint](web_tools.md)
   - Double-tier scraping (Firecrawl API + BeautifulSoup4 fallback).
   - DuckDuckGo free search integration.
2. [Airtable Content Station Blueprint](airtable_tools.md)
   - Draft creation & retrieval from the Airtable "Content Station" table.
3. [Content Rewriting Blueprint](content_tools.md)
   - OpenRouter multi-style content rewrites tailored for Malaysian audiences (`cikgu_fadhli`, `santai_bercerita`, etc.).
4. [Google Drive Blueprint](gdrive_tools.md)
   - Authentication via Service Account JSON and file list/read/write capabilities in Google Drive folders.
5. [AI Image Generation Blueprint](image_tools.md)
   - Flux Schnell image generation via Replicate, fallback image generation, and optimized prompt refinement.

## Migration Design to Antigravity SDK (AuraOne)

The Google Antigravity SDK makes this code **vastly simpler** to run:

```
[Old Flow in AuraAgent]
Manual GenAI tool declarations (JSON schema) → Manual parsing of candidates → Manual dispatching loop → Manual context tracking (history list)

[New Flow in AuraOne]
Import functions into tools.py → Pass functions to LocalAgentConfig(tools=[...]) → Antigravity SDK handles schema compilation, execution, dispatching, and conversation context history automatically!
```

---

## Evolving Day-by-Day
We will port these files sequentially from this reference directory directly into `AuraOne/tools.py` and register them in `AuraOne/main.py` as needed.
