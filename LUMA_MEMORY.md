# LUMA Memory & Progress Tracking

## 📅 Last Updated: 2026-07-13

---

## 🛠️ Work Done

### 1. Interactive Platform Selection & Sub-Options Workflow (Implemented)
* **Goal**: Shift from bulk platform push to a dynamic, interactive step-by-step content generation workflow.
* **Flow**:
  1. User sends `Scrape <url>`.
  2. AURA outputs the **Master Article** (paragraph flow, bold title, clean, hashtags, no bullet points) and caches it.
  3. AURA asks which platform to generate for: `Facebook`, `Threads`, `X`, `Lemon8`, `Instagram`.
  4. If **Facebook**: AURA asks for **Bercerita (Editorial)** vs **Berita (News)**:
     - **Bercerita**: Uses a strong CTA hook at the start to catch attention, writes a casual story, and uses `#saklumastory`.
     - **Berita**: Writes in news report style (starts with location/reporter info like `"Dungun - ..."`) and uses `#saklumanews`.
  5. If **Threads** or **X**: AURA asks for thread length (**3**, **5**, or **8** parts):
     - Translates complex topics into neutral, simple, casual rojak BM/EN that everyday Malaysians easily understand.
     - Numbers them: `1/X`, `2/X` etc.
     - Intersperse 1-2 engagement questions (CTA rotation not too frequent).
  6. If **Lemon8**: Generates a long, structured, aesthetic post.
  7. If **Instagram**: Generates a short, punchy visual caption.
  8. Once generated, user reviews the draft on Telegram and replies `confirm` to publish.

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
