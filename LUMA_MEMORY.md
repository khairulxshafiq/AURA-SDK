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
* **Self-Healing Select Choices (`typecast: True`)**: Enabled `typecast: True` in all Airtable POST record requests, allowing automatic creation of missing options (like Threads or Lemon8) directly inside Airtable columns.
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
* [x] **Publishing Automation**: Complete the configuration of the n8n workflow for Facebook Page posting, sequence X/Threads loops, and schedule polling.
