# LUMA Memory & Progress Tracking

## 📅 Last Updated: 2026-07-13

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
     - **X / Threads**: Selects thread length (**3**, **5**, or **8** parts) where complex text is translated into simple rojak BM/EN.
  5. Once sub-options are selected, user clicks `Generate Drafts ⚡`.
  6. AURA runs the generator for all selected platforms, shows the drafts, and attaches `Confirm & Push [PLATFORM] ✅` buttons for each.
  7. Clicking a confirm button uploads the image to Google Drive and pushes that specific platform draft to Airtable.


### 2. Airtable Fields Schema Mapping (Fixed)
* **Status**: Fully aligned with the real `Content Station` base schema:
  * **`Caption`**: Receives the specific generated platform draft.
  * **`Hashtags`**: Receives the hashtags (e.g. `#saklumastory`, `#saklumanews`).
  * **`Title`**: Receives the post title.
  * **`Platform`**: Receives the platform choice as a list (e.g. `['Facebook']`).
  * **`Scheduled Time`**: Receives the parsed ISO date/time if confirmed with scheduling.
  * **`Status`**: Pushed as `"Draft"` (or `"Scheduled"` if confirmed with a date).
  * Removed direct writing to `AI Caption` and `AI Hashtags` as they are read-only calculated fields in Airtable.

### 3. Date & Scheduling Parser
* **Goal**: Support scheduling confirmation commands.
* **Flow**: User can reply: `confirm schedule esok pukul 10 pagi`. AURA utilizes a quick, robust Gemini call under the hood to parse the natural language date into ISO format (e.g., `2026-07-14T10:00:00+08:00`) and saves it to Airtable's `Scheduled Time` column.

---

## 📌 SQLite Memory Updates (`memory.py`)
* Re-created the `drafts` table to store:
  * `state`: tracks current selection question state (`WAITING_FB_STYLE`, `WAITING_THREAD_LENGTH`, `""`).
  * `selected_platform` and `platform_draft`.
* Added helper functions: `update_draft_state(user_id, state)`.

---

## 🚀 Decisions Made
* **Interactive Style**: Interactive choices prevent API payload clutter and put the user in complete control over the layout before it hits Airtable.
* **Single Record Confirms**: The user prefers to review each platform draft and push them one by one. Once confirmed, that specific record is pushed.

---

## 📋 Future Roadmap / Pending Goals
* [ ] **AURA Blog (Sakluma Blog)**: Set up auto-posting to a Blogger-style site for SEO/Google Web Ads.
* [ ] **Publishing Automation**: Connect Airtable `Content Station` via Make.com/Zapier to auto-publish to Facebook/Threads when `Status = Scheduled` and `Scheduled Time` is reached.
