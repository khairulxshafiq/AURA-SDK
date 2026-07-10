# Blueprint: Alasan & Pemetaan Penyelarasan Antigravity SDK (AuraOne)

Dokumen ini menerangkan bagaimana idea asal **AURA v5** (menggunakan CrewAI, LangGraph, dan orkestrasi manual) diselaraskan secara penuh dengan **Google Antigravity SDK** di bawah satu sistem orkestrasi yang efisien, ringan, dan berskala besar.

---

## 1. Perbandingan Seni Bina: Lama vs Baru

| Bahagian | Seni Bina Lama (AURA v5) | Penyelarasan Antigravity (AuraOne) |
| :--- | :--- | :--- |
| **Backbone** | Pelbagai framework bercampur (CrewAI + LangGraph + manual HTTP requests) | **Satu Runtime Tunggal**: Google Antigravity SDK |
| **Tool Calling** | Pengisytiharan JSON Schema manual + dispatcher loops (`dispatch_tool`) | **Auto-Generated**: Antigravity menukarkan fungsi Python (dengan docstring) terus kepada tools LLM secara asli. |
| **Multi-Agent (Crew)** | Pustaka `crewai` (berat, menyedut banyak token, sukar dikawal) | **Sub-Ejen Dinamik**: Ejen Utama (Supervisor) melancarkan sub-ejen secara dinamik menggunakan tool `start_subagent`. |
| **State Machine** | LangGraph (re-react agents, graph compiles) | **ReAct Loop Asli**: Antigravity menguruskan kitaran Fikir ➔ Guna Tool ➔ Pedomani Hasil secara asli dengan had pusingan terbina. |
| **Memory & History** | Pembersihan token manual, in-memory list per `chat_id` | **Persistent Session**: Auto-saving conversation state menggunakan `save_dir` dan `conversation_id`. |

---

## 2. Bagaimana Idea Asal Anda Dipetakan ke Antigravity Natively

### A. Penggantian CrewAI (Swing Trading Crew)
Dalam CrewAI lama, anda menggunakan 3 ejen berasingan (Growth Analyst, Technical Analyst, Strategist) dengan tugas yang dijadualkan secara berturutan (*sequential process*).

**Di bawah Antigravity SDK:**
1. **Ejen Utama (AURA - Conductor)** bertindak sebagai Portfolio Strategist.
2. Apabila arahan analisis masuk (cth: `Analisa saham 1155.KL`), AURA akan memanggil tool `start_subagent` secara automatik di belakang tabir untuk melancarkan dua tugasan sub-ejen:
   - **Subagent A (Growth Analyst)**: Dikonfigurasikan dengan persona fundamental, menggunakan tool fundamental (`ratios_tool`).
   - **Subagent B (Technical Analyst)**: Dikonfigurasikan dengan persona teknikal, menggunakan tool teknikal (`rsi_tool`, `sma_tool`).
3. Subagent A & B mengembalikan laporan ringkas mereka kepada AURA.
4. AURA (Ejen Utama) mengumpul hasil kerja kedua-dua subagent, menjana keputusan akhir, menyusun **Laporan Akhir 8-Bahagian**, dan memaparkannya di Telegram.
5. **Kelebihan**: Kos lebih murah (kurang token overhead), lebih pantas, dan tiada lagi pergantungan kepada pustaka `crewai` yang berat.

### B. Penggantian LangGraph (ASB Trading Agent)
Dalam LangGraph lama, ejen dibina menggunakan `create_react_agent` untuk memanggil quotes dan fundamental ratios secara berulang.

**Di bawah Antigravity SDK:**
* Antigravity SDK mempunyai enjin **ReAct (Reasoning and Action) asli**. Apabila kita membekalkan tools di dalam `LocalAgentConfig(tools=[quote_tool, ratios_tool])`, ejen akan merancang langkahnya sendiri, memanggil tools, menilai keputusan, dan memanggil tools seterusnya sehingga ia selesai. Tiada sebarang persediaan graf atau *state definition* yang renyah diperlukan.

### C. Aliran Pembelajaran Kemahiran (Hermes-Style)
Hermes Agent terkenal dengan cara menyusun kepakarannya dalam fail Markdown.

**Di bawah Antigravity SDK:**
* Kami memanfaatkan **Filesystem-based Skill Loading** (`skills_paths=[SKILLS_DIR]`).
* Segala logik keputusan trading jangka panjang gaya ASB, teknik penulisan content media sosial, dan risk management portfolio boleh diletakkan di dalam fail Markdown di folder `AuraOne/skills/` (cth: `skills/trading/SKILL.md`).
* Ejen AURA akan membaca arahan kepakaran tersebut pada runtime secara automatik tanpa memerlukan kod parsing tambahan.

---

## 3. Struktur Fail Akhir yang Diselaraskan (AuraOne)

Untuk menyokong pembangunan berperingkat (*day-by-day*), folder `AuraOne` kita disusun seperti berikut:

```text
AuraOne/
├── .env                         # Menyimpan kunci API secara lokal
├── .env.example                 # Contoh templat untuk rujukan/GitHub
├── requirements.txt             # Dependensi asas sahaja (ringan!)
├── persona.txt                  # Watak dan arahan sistem Ejen Utama (AURA)
├── tools.py                     # Tempat himpunan semua fungsi Python (scrape, airtable, trading)
├── main.py                      # Telegram bot + Antigravity Orchestrator
│
├── skills/                      # Folder kemahiran (Hermes-Style Markdown instructions)
│   ├── web_scraping/SKILL.md    # Arahan pengikisan
│   ├── trading/SKILL.md         # [AKAN DATANG] Arahan analisis saham ASB/Swing
│   └── content/SKILL.md         # [AKAN DATANG] Arahan penulisan semula content
│
└── reference_blueprints/        # Rujukan kod asal v5 (untuk copy-paste)
    ├── README.md
    ├── web_tools.md
    ├── airtable_tools.md
    ├── content_tools.md
    ├── gdrive_tools.md
    ├── image_tools.md
    └── trading_tools.md
```
