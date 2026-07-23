# 🌌 AURA-SDK (AuraOne) — Personal AI Agent & Supervisor

Welcome to the **AURA-SDK** repository. AURA is an autonomous AI assistant and supervisor running on a VPS, powered by the **Google Antigravity (AGY) SDK** and Telegram Bot API. It acts as an orchestrator for web scraping, content publishing, cloud storage management, and AI task execution.

---

## 🏗️ Architecture & System Overview (Option B: Orchestrator + Subagents)

To prevent prompt bloat, high latency, and LLM tool calling hallucinations, AURA is built on the **Supervisor-Worker (Hybrid Orchestration)** model. 

* **Orchestrator/Supervisor (AURA Main)**: Handles the Telegram interface, manages session states, classifies user intents, and routes tasks. It acts as the user's primary interface.
* **Worker Subagents**: Dynamically spawned by AURA Main using Google Antigravity's native subagent orchestration. Each subagent has a highly focused system instruction set and only a small subset of tools (e.g., only trading tools for the TradingAgent).

```
                  ┌────────────────────────┐
                  │      Telegram User     │
                  └───────────┬────────────┘
                              │ (Chat/Command)
                              ▼
                  ┌────────────────────────┐
                  │      AURA Main         │ (Orchestrator Bot)
                  │       (main.py)        │ (Primary: Gemini / Fallback: OpenRouter)
                  └───────────┬────────────┘
                              │
             ┌────────────────┼────────────────┐
             ▼ (Delegates)    ▼ (Delegates)    ▼ (Delegates)
       ┌───────────┐    ┌───────────┐    ┌───────────┐
       │ Trading   │    │  Content  │    │    Web    │
       │ Subagent  │    │ Subagent  │    │ Subagent  │
       └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
             │                │                │
       ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐
       │ yfinance  │    │ Airtable  │    │ Firecrawl │
       │ technical │    │ Replicate │    │ DDGSearch │
       └───────────┘    └───────────┘    └───────────┘
```

### 🧠 Multi-LLM Configuration
* **Primary Brain**: Gemini API configured via `google.antigravity.Agent` using `LocalAgentConfig`.
* **Fallback Brain**: OpenRouter API (`openai/gpt-4o-mini`). It automatically takes over if Gemini encounters a `RESOURCE_EXHAUSTED` (Rate Limit / Quota) error to ensure 100% bot availability.
* **Subagent Native Support**: Antigravity is configured with `capabilities=types.CapabilitiesConfig(enable_subagents=True)` enabling AURA to define and invoke isolated subprocess agents seamlessly.


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
4. **Google Drive Integration & Cloud Storage (`gdrive_tools.md`)**
   * Secure service account authentication to upload, read, and search files inside designated Google Drive folders.
   * Official cloud storage for image uploads (`GDRIVE_IMAGE_FOLDER_ID`: `1ntdhPOq3Z7oNXLDqQgVyVQS6tIMoArc3`) and article text draft dumps (`GDRIVE_DUMP_FOLDER_ID`: `1Ybx7mBAKksI2VcagHAqOuKkf8pjbvYwa`), replacing legacy GitHub CDN auto-commits.
5. **AI Image Generation (`image_tools.md`)**
   * Flux Schnell image generation via Replicate API for visual posts.
6. **Trading & Market Analysis (`trading_tools.md`)**
   * Stock indicators querying (yfinance), technical trend calculations (RSI, SMA), and multi-agent trading analysis.


---

## 📂 Project Structure

```
AURA-SDK/
├── AuraOne/                       # Main AURA package
│   ├── .env                       # Environment variables (Gitignored)
│   ├── .venv/                     # Python virtual environment (Gitignored)
│   ├── main.py                    # Bot handler & agent core loop
│   ├── config.py                  # Environment configuration & constants
│   ├── tools.py                   # Atomic tools façade (100% backward compatibility)
│   ├── memory.py                  # Storage repository façade (100% backward compatibility)
│   ├── persona.txt                # System instructions/agent behavior rules
│   ├── storage/                   # SQLite Repository Pattern layer
│   │   ├── db.py                  # Core database connection helper
│   │   ├── memory_repository.py   # Key rotation & cooldown persistence repository
│   │   ├── location_repository.py # User coordinates & saved places repository
│   │   └── draft_repository.py    # Platform draft selection & workflow state repository
│   ├── tools/                     # Atomic modular tools
│   │   ├── web_scraper.py         # Article scraping & URL resolution
│   │   ├── search_engine.py       # DuckDuckGo & GNews live engine
│   │   ├── location_service.py    # Geocoding & Open-Meteo weather integration
│   │   ├── apify_service.py       # Apify Shopee scraper pipeline
│   │   └── publisher_service.py   # Google Drive API & Airtable sync publisher
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

## �️ Git & PR Workflow for Contributors

All changes to this repository must follow the safe workflow below, especially when LUMA, Cline, Copilot, or any automation agent is involved.

### Required workflow
1. Create or switch to a dedicated branch before editing files.
2. Commit changes on that branch only.
3. Open a Pull Request for review before merging into `main`.
4. Do not merge directly to `main` without approval.
5. If an agent cannot create a branch, it must stop and ask for confirmation instead of forcing a push or merge.

### Suggested branch naming
- `feature/description-yyyy-mm-dd`
- `fix/issue-description-yyyy-mm-dd`
- `backup/description-yyyy-mm-dd`

### Example commands
```bash
git checkout -b feature/my-change
git add .
git commit -m "feat: describe change"
git push -u origin feature/my-change
```

### PR checklist
- Summary of what changed
- Why it changed
- Validation performed
- No direct merge to `main`

---

## �🚀 Running AURA Bot on VPS

AURA runs as a background service managed by `systemd`.

* **Start Service**: `sudo systemctl start aura`
* **Stop Service**: `sudo systemctl stop aura`
* **Restart Service**: `sudo systemctl restart aura` *(Run this every time you modify `main.py` or `tools.py`)*
* **Check Status**: `sudo systemctl status aura`
* **Monitor Live Logs**: `journalctl -u aura -f --no-pager`
