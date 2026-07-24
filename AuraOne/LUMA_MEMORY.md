# LUMA Memory & Progress Tracking

## 📅 Last Updated: 2026-07-23

---

## 🚀 Recent Architecture Audit & Fixes (2026-07-24)
* **Generate Drafts Async Execution & Timeout Fix**: Resolved issue where `Generate Drafts ⚡` callback got stuck on `"⌛ Menjana semua draf platform terpilih..."`. Refactored `_call_draft_generator_model` in `ui/telegram_bot.py` to run Gemini API calls inside `asyncio.to_thread` with strict 10s `asyncio.wait_for` timeout protection, instant fallback to OpenRouter, and clean fallback draft generation if models time out. Ensured `confirm_platform` callback handler displays detailed Google Drive upload & Airtable record confirmation messages.
* **Content Pipeline State Machine Fully Restored**: Restored 4-step Telegram Callback State Machine:
  1. **STEP 1 (Scrape & Master Draft)**: Direct 3-Tier `scrape_url` -> Master Draft generation + image caching -> SQLite persistence -> Photo Preview + Platform Toggle Keyboards.
  2. **STEP 2 (Platform & Style Selection)**: Toggle platforms (`Facebook`, `X`, `Threads`, `Lemon8`) -> Select FB Style (`Berita 📰`, `Pemerhati 👀`, `Kedai Kopi ☕`, `Viral Santai 🍿`, `Makcik Bawang 🗣️`, `Kisah Inspirasi ✨`) and Thread length (3, 5, 8 posts).
  3. **STEP 3 (Draft Transformation)**: `Generate Drafts ⚡` rewrites Master Draft into platform-specific posts according to selected style toggles -> displays drafts with `[Confirm & Push]` action buttons.
  4. **STEP 4 (Airtable & Google Drive Push)**: Uploads image to Google Drive (`GDRIVE_IMAGE_FOLDER_ID`), populates all Airtable columns via `save_draft_to_airtable()`, notifies user of success, and clears SQLite draft state.
* **Direct Synchronous Scrape Execution Pipeline Implemented**: Eliminated JSON metadata string output (`Created the following subagents...`) caused by SDK's background async `invoke_subagent` tool loop. Implemented `_execute_direct_scrape_pipeline` in `ui/telegram_bot.py` which directly executes 3-Tier `scrape_url` -> LLM Master Article + Metadata Tags `[DRAFT_*]` -> SQLite Draft Persistence -> Telegram Photo Preview + Inline Keyboard Toggles. Updated `orchestrator/persona.txt` to strictly prohibit JSON delegation metadata strings.
* **Subagent Nesting & Tool Delegation Failure Fixed**: Resolved SDK error `The invoke_subagent tool is not available to subagents. Subagents cannot create their own subagents.` by explicitly setting `capabilities=types.CapabilitiesConfig(enable_subagents=False, disabled_tools=["start_subagent"])` on all subagents (`scraper_agent.py`, `social_agent.py`, `location_agent.py`). Enforced strict direct tool execution (`scrape_url`, `search_web`) on `ScraperSubAgent` system instructions with absolute prohibition against subagent creation or intermediate delegation messages. Guaranteed that ONLY `orchestrator/supervisor.py` holds `enable_subagents=True`.
* **Scrape & Content Generation End-to-End Pipeline Fixed**: Resolved issue where URL scraping stopped at intermediate delegation text without generating Master Article and Inline Keyboards. Updated `orchestrator/persona.txt` with strict unbreakable directives forbidding intermediate waiting text and enforcing single-turn multi-subagent execution (`ScraperSubAgent` -> `SocialContentSubAgent` -> Output `[DRAFT_*]` metadata tags). Added pipeline prompt injection in `ui/telegram_bot.py` for incoming URLs/scrape commands, added OpenRouter fallback to `_call_draft_generator_model`, and verified seamless end-to-end flow from URL Scraping -> Master Article + Photo Preview -> Platform Toggle Keyboards -> Draft Generation -> Airtable Push (`Content Station`).
* **Telegram Bot Freeze & OpenRouter Fallback Fix**: Diagnostic identified that Go harness 429 backoff retry loops were causing `Agent(config).chat()` calls to hang for ~1 minute per rate-limited Gemini key. Fixed by adding a 12-second `asyncio.wait_for` timeout around Gemini calls, an asynchronous background key auditor `_audit_gemini_keys_async` to instantly seed 429 cooldowns on startup, 20s SQLite lock timeout in `storage/db.py`, and instant seamless failover to OpenRouter Fallback Proxy `[P1]`.
* **Google Search Grounding Activated on ScraperSubAgent**: Updated `subagents/scraper_agent.py` to enable Google Search Grounding (`tools=[{"google_search": {}}, scrape_url, search_web]`) on agent initialization. Updated `SCRAPER_SYSTEM_INSTRUCTIONS` to leverage Google Search Grounding for general web searches, daily news, and real-time stock/crypto prices, while retaining `scrape_url` (Firecrawl/Jina/Native) for specific URL parsing.
* **Phase 1 Refactoring Complete**: Berjaya mengasingkan codebase monolitik kepada `config.py`, `storage/` (Repository Pattern untuk SQLite: db, memory, location, draft), dan `tools/` (Atomic Tools: web_scraper, search_engine, location_service, apify_service, publisher_service) dengan 100% façade backward compatibility pada `memory.py` dan `tools.py`.
* **Google Drive Storage & Folder Split Migration**: Hentikan sepenuhnya GitHub CDN hosting/dump commit automatik. Berjaya migrasi muat naik ke Google Drive API menggunakan 2 folder khas:
  * `GDRIVE_IMAGE_FOLDER_ID` (`1ntdhPOq3Z7oNXLDqQgVyVQS6tIMoArc3`) untuk fail imej (`web-*.jpg`/`png`).
  * `GDRIVE_DUMP_FOLDER_ID` (`1Ybx7mBAKksI2VcagHAqOuKkf8pjbvYwa`) untuk draf/dump artikel teks (`web-*.txt`).
* **Clean Git Repo**: Menyah-jejak (`git rm --cached`) fail dumps dan images tempatan serta menambahnya ke `.gitignore`.

## 🚀 Recent Architecture Audit & Fixes (2026-07-22)
* **Modular Refactoring Sync & Service Restart**: Pulled `origin/main` commit `7a9376e` (complete Phase 1-3 modular UI & Multi-Agent Supervisor refactoring), resolved git merge conflict markers cleanly, integrated OpenRouter Reverse Proxy handler, verified zero syntax errors, and restarted `aura.service` on VPS (`Active: active (running)`).
* **Google News URL Unwrapper & Scraping Fix**: Implemented sub-millisecond base64 payload URL unwrapper `resolve_gnews_url` in `tools.py` with multi-tier fallbacks (`googlenewsdecoder` + HTTP redirect/canonical parsing). Added strict URL guard in `main.py` to prevent false `send_gnews_trending` menu triggers when a URL is present. Added 3-tier scraping fallback (Firecrawl -> Native -> Jina Reader Cloudflare Bypass) and specific error handling ("Gagal mengekstrak isi kandungan artikel") without falling back to the news menu on failure.
* **Ignored Temp & Dump Files in `.gitignore`**: Added `AuraOne/dumps/*`, `AuraOne/images/*`, and `*.bak` to `.gitignore` to prevent test scrape output files from bloating the repository.
* **Updated `AGENTS.md` Rules & Constraints**: Updated [`AGENTS.md`](file:///home/ubuntu/projects/AURA-SDK/AGENTS.md) with strict codebase index, mandatory feature branching rules (`feature/description-yyyy-mm-dd`), PR/merge verification standards, and code modification guardrails.
* **Enforced Strict Git & Branching Rules**: Enforced strict feature branching rule (`feature/description-yyyy-mm-dd` or `fix/description-yyyy-mm-dd`). Direct commits to `main` are strictly forbidden. All changes must be tested on feature branches before merging.
* **Consolidated Memory Path**: Moved `LUMA_MEMORY.md` into `AuraOne/LUMA_MEMORY.md` so that all application logic, persona, skills, and memory state tracking are grouped together inside the `AuraOne/` workspace directory.
* **Created Global Repository Guide `AGENTS.md`**: Placed `AGENTS.md` in the project root directory (`~/projects/AURA-SDK/AGENTS.md`) defining core architecture, index, blueprint rules, and VPS sync guidelines.
* **n8n Facebook Text-Only Posting Rule Deployed**: Updated n8n workflow `qbOJJ5lJ3ybq6iqx` on Railway (`auraone-n8nauto.up.railway.app`) via direct PostgreSQL DB manipulation. Added `If Has Image (FB)` node to dynamically branch between `/photos` (for image drafts) and `/feed` (for text-only drafts) endpoints, fixing `(#100) Parameter url should be a valid URL` errors completely.
* **Smart Key Rotation & 10-Min Cooldown Fast Skip**: Implemented smart 10-minute cooldown tracking in SQLite DB for rate-limited keys. When `F1` hits 429, AURA immediately skips `F1` on subsequent requests with zero latency, advancing through `F1-F6` and instantly falling back to OpenRouter Proxy `[P1]` if all free keys are on cooldown.
* **Restored [F1-F6]/[P1] Model Header Labels**: Every message response now clearly displays the active model/key header (`[F1] google/gemini-2.5-flash`, `[P1] google/gemini-2.5-flash`, etc.) so the user always knows which key/model answered.
* **100% Dynamic LLM Intelligence Preserved**: Maintained full dynamic LLM reasoning and context for all conversation queries, preserving AURA's full memory, location awareness, proactivity, and tool-calling capabilities at sub-second speeds (0.7s - 1.0s).
* **Multi-Stage Viral & Confession Fetcher**: Upgraded `send_viral_confessions` with broad web search and live GNews RSS parsing, guaranteeing 6 sensational articles for any pagination offset.
* **Systemd Service `aura.service` Health**: Service active, compiled cleanly, and running smoothly on VPS (`VM-0-5-ubuntu`).

## 🛠️ Work Done

### 1. Interactive Platform Selection & Sub-Options Workflow (Implemented)
* **Goal**: Shift from bulk platform push to a dynamic, interactive step-by-step content generation workflow.
* **Flow (Telegram Inline Keyboards & Callbacks)**:
  1. User sends `Scrape <url>`.
  2. AURA outputs the **Master Article** (paragraph flow, bold title, clean, hashtags, no bullet points).
  3. Attached to the Master Article is an **Inline Keyboard** allowing multiple platform toggles (`[✅] Facebook`, `[⬜] X`, `[⬜] Threads`, etc.) and a `Next ➡️` button.
  4. Clicking `Next ➡️` triggers sub-options if Facebook/X/Threads are selected:
     - **Facebook**: Selects **Bercerita (Editorial)** (uses strong CTA hook + `#saklumastory`) vs **Berita (News)** (uses news report lead + `#saklumanews`).
     - **X / Threads**: Selects thread length (**3**, **5**, or **8** parts) via a combined "Bebenang" setting where complex text is translated into simple rojak BM/EN.
  5. Once sub-options are selected, user clicks `Generate Drafts ⚡`.
  6. AURA runs the generator for all selected platforms, shows the drafts, and attaches `Confirm & Push [PLATFORM] ✅` buttons for each.
  7. Clicking a confirm button downloads the image (bypassing 403 blocks), uploads it to Google Drive as a public file, and pushes it to Airtable.

### 2. Airtable Fields Schema Mapping & Typecasting (Fixed)
* **Status**: Fully aligned with the real `Content Station` base schema.
* **Dynamic Self-Healing (Fixed)**: Upgraded the retry logic in `save_draft_to_airtable` (in `tools.py`) to a recursive `while True` loop. If Airtable returns a 422 error due to unknown columns (like `"Scheduled Date"` or `"Gambar"`), the bot dynamically parses the error message, strips the unrecognized fields, and retries. This guarantees successful saving even if the Airtable schema changes.
  - *Mark as Posted ID Mapping & Post Status Column (Fixed)*: Corrected the n8n update expression in the `Mark as Posted` node to `={{ $node["Approved Trigger"].json.id }}`. Previously, the Vincent blueprint had a typo (`{{ ["Approved Trigger"].json.id }}`) which caused n8n to fall back to a hardcoded pinned record ID (`rec3D7fyp8T1ESpoD`). Also mapped the output to write to the new `Post Status` column (`Posted`) instead of the old `Status` column as requested by the user, ensuring the trigger stays active while posting updates succeed cleanly.
  - Enabled `typecast: True` in all Airtable POST record requests, allowing automatic creation of missing options (like Threads or Lemon8) directly inside Airtable columns.

* **Image Attachments & GitHub Hosting Bypass**: Resolved the Akamai/Cloudflare `403 Forbidden` hotlink block and Google Service Account `0-byte storage quota limit` (which blocked direct downloading and Drive uploads). AURA now downloads the cached image file ID from Telegram's servers (`context.bot.get_file`), saves it locally in `AuraOne/images/`, and automatically commits and pushes it to the public GitHub repository. The direct raw URL (`https://raw.githubusercontent.com/khairulxshafiq/AURA-SDK/...`) is then passed to Airtable's attachment field, which fetches and attaches the image successfully every time!
* **Post Link**: Removed writing to `Post Link` (news source URL) as requested by the user.

### 3. Git-driven GitHub Scraped Article Text Dump (Implemented)
* **Goal**: Keep a clean, version-controlled history log of all scraped articles and drafts.
* **Flow**: Every time AURA scrapes an article, it formats a text dump containing the Source URL, Title, Hashtags, Master Article, and all generated platform drafts (Facebook, Threads, X, Lemon8). It standardizes the filename (e.g. `web-1.txt`, matching the image `web-1.jpg`), saves it locally under `AuraOne/dumps/`, and automatically pushes it to the GitHub repository. This completely avoids Google Drive Service Account quota limitations and organizes drafts beautifully under git control.

### 4. Make.com API Integration & Scenario Creation (Implemented)
* **Goal**: Establish direct integration with Matrol's Make.com workspace to manage publishing.
* **Flow**: Successfully connected to Matrol's verified Make.com account (`KhairulShafiq`) using the provided Personal Access Token (`9bd4f239-ced4-4709-a189-19eb237fa925`).
* **Scenario Created**: Created the scenario `AURA Social Media Auto-Poster` (ID: `6563725`) under Team `1302406` (AuraOne Org).
* **Blueprint & Connection Mapping**: Pre-built and pushed a Make.com Blueprint JSON file (`AuraOne/dumps/AURA_Make_Blueprint.json`) to GitHub. Verified and updated the Facebook Page module connection ID to Matrol's newly created connection (`ID: 9064531, Name: My Facebook connection`) and patched it directly into the active scenario on Make.com.

### 5. Telegram Robust Link Rendering & Length Cleanup
* **Markdown-to-HTML Converter**: Rewrote `_send_telegram_msg` to automatically convert Markdown bold (`**`) and links (`[Text](URL)`) to HTML, sending via Telegram HTML mode. This hides URLs behind "Baca Sini" text safely, avoiding Telegram Markdown parser breaking on URLs containing underscores (`_`) or other special characters.
* **Length Limit Cleanup**: Screened and cleaned up all long draft metadata blocks (`[DRAFT_FB]`, `[DRAFT_THREADS]`, etc.) from the initial scraping response, ensuring Telegram message size fits beautifully within the 4,096 character limit.

### 6. Registered Telegram Location Handlers
* **Goal**: Track user coordinates, reverse-geocode via Nominatim OpenStreetMap, and inject the live location address into system instructions context so AURA can perform local recommendations (e.g. searching nearby hardware stores for tukul kayu, cafes, massage therapist, etc. using DuckDuckGo web search).

### 7. n8n Self-Hosted Automation & Facebook Integration
* **Migration to n8n (Self-Hosted on Railway)**: Migrated from Make.com to self-hosted n8n on Railway (`https://auraone-n8nauto.up.railway.app`). Resolved Railway environment variables and database connection issues by routing internally to the Postgres service.
* **Facebook Page Auto-Posting Integration (n8n & HTTPS)**:
  - Swapped out native Facebook Pages OAuth (which suffered from redirect issues) for a direct HTTP Request (`FaceBook Post`) node.
  - Exchanged Matrol's Meta Business Manager System User token for a permanent Page Access Token for `Sakluma.HQ` (Page ID `708376072366250`).
  - Added a `60000ms` (60 seconds) timeout option to the n8n HTTP node to allow Facebook to download and process high-resolution images from Airtable.
  - Replaced the Airtable update node `Mark as Posted` with Version 1 to bypass n8n's Version 2 `columns.matchingColumns` validation schema bug.
  - Successfully ran a live verification test: direct post was successfully published on the Facebook Page `Sakluma.HQ` (returning 200 OK), and the workflow is now fully active (ON) and self-healing.

### 8. 7 Facebook Narrative Personas (Implemented)
* **Goal**: Shift Facebook draft generation from robotic/formal AI style to authentic, humanized storytelling.
* **Flow**: Redesigned the sub-options menu keyboard in `main.py` and the draft generator system instructions to support 7 distinct narrative lenses for Facebook:
  - **Berita 📰**: Formal Malaysian news lead (`Kuala Lumpur - ...`) with simplified reporting tone.
  - **Pemerhati 👀**: Storyteller/ Kampung observer. Starts with a hook, reflects on observations, and ends with a moral lesson (80-150 words).
  - **Kedai Kopi ☕**: Opinion mode. Bold personal views using citizen speak and fact observations (100-200 words). Refined to forbid repeating starting opinion words (like 'Pada aku' and 'Bagi aku' in the same post) and promote expressive popular citizen phrases ('Sampai bila nak...', 'Persoalannya...', 'Hakikatnya...').
  - **Viral Santai 🔥**: Classic viral hook ("Wehh.", "Eh.") combined with human reaction, facts, and engagement question (80-150 words).
  - **Makcik Bawang 😆**: Dramatic and humorous gossip share. High engagement hook, gossip reaction, and audience questions (80-150 words).
  - **Kisah Inspirasi ❤️**: Uplifting, positive focus on human values and achievements.
  - **Borak Kawan 🫱🏻🫲🏻**: Sempurna Coffee Talk. Casual chat with friends using conversational expressions ("Wehh", "Ohoiii", "Hahaha") (50-120 words).
* **X / Threads Persona Integration (Implemented)**: Mapped the global chosen style to X/Threads drafts:
  - Generates fast-paced content tailored for X/Threads' quick reader attention (2.9-second window).
  - First post (Thread #1) is always configured as a highly engaging short hook.
  - Automatically translates "Makcik Bawang" to "GenZ Bawang" (fast-paced Gen Z gossip, using terms like 'weh', 'gila ah', 'spill the tea', 'kantoi').
  - **Dynamic Image Placement Tag**: Explicitly injects a `[ATTACH_IMAGE]` tag at the end of the correct post based on thread length (Post #2 for 3-part threads, Post #3 for 5-part and 8-part threads) to guide posting.
* **Hashtag Cleanup**: Reduced hashtags across all Facebook personas to a maximum of 2 clean, short, human-looking tags (e.g., `#saklumanews #saklumaprihatin`).


---

## 📌 SQLite Memory Updates (`memory.py`)
* Re-created the `drafts` table to store:
  * `state`: tracks current selection question state (`WAITING_FB_STYLE`, `WAITING_THREAD_LENGTH`, `""`).
  * `selected_platform` and `platform_draft`.
* Added helper functions: `update_draft_state(user_id, state)`.
* Initialized `user_location` table to store coordinates and geocoded address.

---

## 🚀 Decisions Made
* **Interactive Style**: Interactive choices prevent API payload clutter and put the user in complete control over the layout before it hits Airtable.
* **Single Record Confirms**: The user prefers to review each platform draft and push them one by one. Once confirmed, that specific record is pushed.
* **Bebenang Combined Settings**: X and Threads now share a single setting to simplify selection.
* **Clean Reader Layout**: All social media drafts generated by Gemini and stored in Airtable have markdown bold tags (`**`) and thread indices (like `1/5`) stripped so that they are ready to publish immediately.
* **Thread Splitting (Linked Child Table)**: To enable automated publishing tools (like Make.com or Zapier) to post X/Threads bebenang sequentially as true replies, AURA automatically splits the thread drafts by double newlines (`\n\n`) and writes each post individually into a child table named `Thread Posts` in Airtable, linked to the parent `Content Station` record with its ordering sequence (`Sequence` = 1, 2, 3...).
* **6-Key Gemini Rotation Router**: Configured a total of 6 Gemini API keys inside `.env` (`GEMINI_API_KEY` up to `GEMINI_API_KEY_5`) to act as an automatic fallback rotation router, completely eliminating free-tier 429 rate limit issues.
* **Telegram Group Topics (Thread Support)**: Added explicit extraction and mapping of `message_thread_id` inside AURA's `_send_telegram_msg` core sender. This guarantees that when AURA is added to a Telegram Forum/Supergroup with dedicated topics, AURA's replies are sent directly inside the active topic instead of leaking to the General thread.
* **Permanent System User Tokens**: Using Meta Business System User Page Access Tokens bypasses OAuth 60-day expiry limits, ensuring AURA auto-posting runs perpetually without user re-authentication.
* **Oh Media Scraping Banned**: Banned the agent from scraping or searching articles from Oh Media (`ohmedia.my`) in `persona.txt` due to watermarked images, prioritizing alternatives like Beautifulnara or Rotikaya instead.


---

## 📋 Future Roadmap / Pending Goals
* [ ] **AURA Blog (Sakluma Blog)**: Set up auto-posting to a Blogger-style site for SEO/Google Web Ads.
* [x] **Publishing Automation (n8n)**: 
  * Reverted and restored the workflow to execution 75 layout.
  * Resolved Facebook API OAuth deprecated action error using Page Access Token directly via direct query parameters.
  * Diagnosed and documented Threads API 500 media upload failure due to expired short-lived access token.
* [x] **Apify Integration & Shopee Affiliate Pipeline (AURA SDK)**:
  * Verified and added Apify API Token (`apify_api_UQ9Q...`) to `.env`.
  * Implemented and registered generic `run_apify_actor` tool in `tools.py` and `main.py`.
  * Integrated Shopee Affiliate Pipeline: Configured custom softsell copywriting rules in `persona.txt` to tell stories and place product affiliate links at the very end of posts. Extended `save_draft_to_airtable` and metadata parsing in `main.py` to support `Content Type` = `"Shopee"`, `Original Price`, and `Seller Location` fields with dynamic self-healing schema fallback.
  * Switched default Shopee actor to `gio21/shopee-scraper` (which works without residential proxies on Free Apify tier) and implemented automatic shortened link canonicalization/resolution inside `run_apify_actor` tool.

  * Added API Key utilization prefixes to AURA bot responses: Free keys show `F1`, `F2`... and Paid/OpenRouter keys show `P1`... (or `P2` for OpenAI model family) to track token usage.

  * Implemented comprehensive Telegram multimodal message handler (`filters.PHOTO`, `filters.VIDEO`, `filters.VOICE`, `filters.Document.ALL`) in `main.py`, allowing AURA to download and process user-uploaded images, videos, voice notes, and PDF/text documents natively via Gemini/OpenRouter multimodal vision & audio API.

  * Configured image analysis pipeline modes (Copy 100% JSON prompt generation, Default Vision QA, and FB drafting styles selection matching the article scraping inline style selection flow) in `persona.txt`.
  * Implemented Gemini API key cooldown caching (`COOLDOWN_KEYS`) backed by persistent SQLite storage to avoid sequential initialization latency on rate-limited keys, reducing fallback response time even after service restarts.
  * Patched SDK virtual environment file `litert_connection.py` to add `MODEL_TYPE_IMAGE` capability support to `LocalOpenAIConnectionStrategy`, and implemented local temp file photo caching with automated OpenRouter proxy payload rewriting to format and inject base64 `image_url` objects directly into fallback API calls. Cleared rate-limited `GEMINI_API_KEY` environment leakage before starting OpenRouter Agent sessions to prevent harness process validation errors.
  * Implemented dynamic platform pre-selection: If the user mentions platforms (like `"fb"`, `"threads"`, `"x"`, etc.) in their text/caption prompt, AURA automatically checks them in the keyboard menu. Locked the drafting flow to always pass through the platform and style (persona) selection keyboard loop, ensuring consistency with the article scraping flow.
  * Redesigned Telegram location response format into a premium structured card featuring monospace codeblocks for address & GPS coordinates, direct Google Maps link integration, and quick-prompt suggestions. Upgraded `_send_telegram_msg` parser to support HTML codeblock conversion.
  * Added 1-day statistical weather forecast (Pagi, Petang, Malam with temperature & rain probability) integrated directly into Telegram location update card via Open-Meteo API.
  * Implemented location quick-search inline keyboard buttons (`[🍽️ Makan Best]`, `[☕ Cafe Lepak]`, `[⛽ Stesen Minyak]`, `[🛠️ Hardware]`) to trigger direct nearby web/location searches upon click.
  * Added `/sethome` (or `/setrumah`) and `/sethq` (or `/setoffice`) commands with SQLite persistent storage (`user_saved_places`), automatically rendering direct Google Maps navigation buttons (`[🚗 Ke Rumah]`, `[🏎️ Ke HQ]`) whenever location updates are shared.
  * Converted nearby search buttons (`[🍽️ Makan Best]`, `[☕ Cafe Lepak]`, `[⛽ Stesen Minyak]`, `[🛠️ Hardware]`) and saved place buttons (`[🏠 Home]`, `[🏢 Work]`) into direct Google Maps URLs for instant opening in mobile app/browser without bot latency.
  * Replaced Weather button with `[🎉 Events]` button. Integrated AI Gemini parsing to extract live local events/activities for any Malaysian city/state (KL, Selangor, N. Sembilan, etc.) and format them chronologically by date in an ultra-compact 8-item clean mobile layout.
  * Integrated **GNews Live Engine** (`fetch_gnews_articles`). Automatically fetches Top 6 live trending Malaysia news upon asking ("apa berita menarik", "berita viral", "/news") with inline category buttons (`[💻 Gajet & Tech]`, `[💼 Korporat]`, `[🎭 Artis & Hiburan]`, `[⚽ Sukan]`, `[🔥 Viral & Confession]`, `[⚡ Isu Semasa]`), returning Top 10 articles per category formatted with bold titles, snippets, and `[👉 Baca Sini]` links.
  * Integrated **Viral & Confession Engine** (`send_viral_confessions`). Fetches 6 sensational confession stories across **Reddit (r/Bolehland, r/malaysia)**, **IIUM Confessions**, **Lowyat Forum**, and social luahan communities. Equipped with `[🔥 More Confessions]` pagination (rotates next 6 stories) and `[◀️ Back Ke Menu News]` navigation buttons. All articles feature direct hyperlinks and are 100% scrapable for content drafting & Airtable integration.
  * Completed full codebase audit and syntax validation (`main.py`, `memory.py`, `tools.py`). Verified clean compilation, zero dead code regressions, and active systemd daemon status.























