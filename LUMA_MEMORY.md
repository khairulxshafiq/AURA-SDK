# LUMA Memory & Progress Tracking

## 📅 Last Updated: 2026-07-14

---

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

  * Added API Key utilization prefixes to AURA bot responses: Free keys show `F1`, `F2`... and Paid/OpenRouter keys show `P1`... to track token usage.
  * Implemented Telegram photo message handler (`filters.PHOTO`) in `main.py` allowing AURA to download and process user-uploaded images natively via Gemini/OpenRouter multimodal vision API.
  * Configured image analysis pipeline modes (Copy 100% JSON prompt generation, Default Vision QA, and FB drafting styles selection matching the article scraping inline style selection flow) in `persona.txt`.
  * Implemented Gemini API key cooldown caching (`COOLDOWN_KEYS`) to avoid sequential initialization latency on rate-limited keys, reducing fallback response time.










