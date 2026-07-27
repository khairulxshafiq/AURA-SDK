# ADELIA Content Microservice Skill Specification (v1.0)

> **Role & Persona:** ADELIA — Web Scraper, News Analyst, and Social Media Copywriter Engine.

---

## 📡 Microservice API Endpoints

- `GET /health` : Service health status check.
- `POST /api/v1/content/scrape` : 3-Tier Web Scraping & Photo Extraction (Firecrawl -> Jina -> Native).
- `POST /api/v1/content/generate-drafts` : Multi-platform persona transformation (FB 7 Lenses, Threads/X mini-threads, Lemon8).
- `POST /api/v1/content/publish` : Airtable Content Station schema sync & Google Drive backup publisher.
