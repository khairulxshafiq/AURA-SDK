# 🌌 AURA-SDK (AuraOne) — Personal AI Agent & Supervisor

Welcome to the **AURA-SDK** repository. AURA is an autonomous AI assistant and supervisor running on a VPS, powered by the **Google Antigravity (AGY) SDK** and Telegram Bot API. It acts as an orchestrator for web scraping, content publishing, cloud storage management, and AI task execution.

---

## 🏗️ Architecture & System Overview

AURA is designed to be lightweight, modular, and resilient by leveraging Gemini APIs as the primary brain, with OpenRouter as a robust fallback.

```
                  ┌────────────────────────┐
                  │      Telegram User     │
                  └───────────┬────────────┘
                              │ (Chat/Command)
                              ▼
                  ┌────────────────────────┐
                  │   Telegram Bot Loop    │
                  │       (main.py)        │
                  └───────────┬────────────┘
                              │
             ┌────────────────┴────────────────┐
             ▼ (Primary)                       ▼ (Fallback - 429 Rate Limit)
┌─────────────────────────┐       ┌─────────────────────────┐
│       Gemini API        │       │    OpenRouter API       │
│  (Google Antigravity)   │       │   (openai/gpt-4o-mini)  │
└────────────┬────────────┘       └────────────┬────────────┘
             │                                 │
             └────────────────┬────────────────┘
                              │
                              ▼
             ┌─────────────────────────┐
             │    Tool Registry &      │
             │       Execution         │
             │       (tools.py)        │
             └──────────┬──────────────┘
                        │
         ┌──────────────┼──────────────┬──────────────┐
         ▼              ▼              ▼              ▼
   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
   │ Firecrawl │  │ Airtable  │  │ Replicate │  │  G-Drive  │
   │ Scraper   │  │ (Content) │  │  (Flux)   │  │  Storage  │
   └───────────┘  └───────────┘  └───────────┘  └───────────┘
```

### 🧠 Multi-LLM Configuration
* **Primary Brain**: Gemini API configured via `google.antigravity.Agent` using `LocalAgentConfig`.
* **Fallback Brain**: OpenRouter API (`openai/gpt-4o-mini`). It automatically takes over if Gemini encounters a `RESOURCE_EXHAUSTED` (Rate Limit / Quota) error to ensure 100% bot availability.

---

## 🔧 Core Systems & Integrated Tools

AURA is designed to support the following key capabilities (located in `AuraOne/reference_blueprints/` and currently being integrated into `AuraOne/tools.py`):

1. **Web Scraper & Search (`web_tools.md`)**
   * Uses **Firecrawl API** to crawl pages and convert them into clean Markdown.
   * Free fallback scraping using BeautifulSoup4.
   * Free web search integration using DuckDuckGo.
2. **Airtable Content Station (`airtable_tools.md`)**
   * Automatically saves generated posts, research drafts, and ideas to the "Content Station" table.
3. **Multi-Style Content Writer (`content_tools.md`)**
   * Prompts and templates tailored for Malaysian copywriting styles (e.g., *cikgu_fadhli*, *santai_bercerita*).
4. **Google Drive Integration (`gdrive_tools.md`)**
   * Secure service account authentication to upload, read, and search files inside a designated Google Drive folder.
5. **AI Image Generation (`image_tools.md`)**
   * Flux Schnell image generation via Replicate API for visual posts.

---

## 📂 Project Structure

```
AURA-SDK/
├── AuraOne/                       # Main AURA package
│   ├── .env                       # Environment variables (Gitignored)
│   ├── .venv/                     # Python virtual environment (Gitignored)
│   ├── main.py                    # Bot handler & agent core loop
│   ├── tools.py                   # Custom tool registration
│   ├── persona.txt                # System instructions/agent behavior rules
│   ├── sessions/                  # Local user chat history sessions (Gitignored)
│   ├── skills/                    # Specialized agent capability modules
│   └── reference_blueprints/       # Legacy AURA v5 reference code for porting
│
├── Reference/                     # LUMA setup guides and scripts (Gitignored)
│   ├── .luma_memory.md            # LUMA's private work-log and status tracker
│   ├── setup_luma.sh              # Bash script to boot/initialize LUMA on VPS
│   └── termius_login_guide.md     # Guide for logging in via SSH
│
└── .gitignore                     # Git ignore rules
```

---

## 🔄 Sync & Development Workflow

To avoid confusion, we differentiate between the **AURA-SDK Codebase** and **LUMA Private Files**:

### 1. AURA-SDK Codebase (Synced via Git / GitHub)
* **What**: `main.py`, `tools.py`, `persona.txt`, `skills/`, `reference_blueprints/`.
* **How**: Use standard Git commands.
  * **From Mac (Local)**: Edit your code, then run:
    ```bash
    git add .
    git commit -m "feat: add new tool"
    git push origin main
    ```
  * **From VPS (Remote)**: Pull updates into the workspace:
    ```bash
    git pull origin main
    # restart service to apply changes
    sudo systemctl restart aura
    ```

### 2. LUMA Private Files (Synced via Rsync/SCP if needed, Gitignored)
* **What**: `.env`, `.venv/`, `sessions/`, `Reference/` folder, `.luma_memory.md`.
* **Why**: These are server-specific secrets, cache files, and private logs for LUMA.
* **How**: If you want to backup or sync the `.luma_memory.md` file from VPS to your local Mac, run:
  ```bash
  # Run from your local Mac
  scp ubuntu@43.134.46.254:/home/ubuntu/projects/AURA-SDK/Reference/.luma_memory.md ./Reference/
  ```

---

## 🚀 Running AURA Bot on VPS

AURA runs as a background service managed by `systemd`.

* **Start Service**: `sudo systemctl start aura`
* **Stop Service**: `sudo systemctl stop aura`
* **Restart Service**: `sudo systemctl restart aura` *(Run this every time you modify `main.py` or `tools.py`)*
* **Check Status**: `sudo systemctl status aura`
* **Monitor Live Logs**: `journalctl -u aura -f --no-pager`
