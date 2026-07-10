# AURA v6 Architecture Notes

> **Core idea:**  
> **Hermes Experience + Antigravity Runtime + OpenRouter Models + Human Control**

Bukan lagi architecture yang terlalu technical-centric seperti:

```text
LangGraph + CrewAI + Agent + SubAgent + Supervisor + Planner + Critic + Evaluator + ...
```

🤣

---

## 1. Kenapa AURA v5 Rasa Over-Engineered

AURA v5 bukan gagal. Masalah dia ialah terlalu banyak benda bercampur dalam satu codebase:

- Framework
- Product
- Assistant
- Trading bot
- Content system
- Memory system
- Research engine
- Coding agent
- Image agent
- Future experimental modules

Bila semua benda dianggap sebagai agent, crew, graph, workflow dan evaluator, setiap feature kecil boleh jadi berat untuk maintain.

Kesimpulan penting:

> **Jangan delete AURA. Delete complexity.**

AURA v5 boleh di-freeze dan dijadikan archive/source of truth. AURA v6 dibina semula dengan struktur yang lebih simple, modular dan tahan lama.

---

# Cara Aku Nampak AURA v6

## Layer 1 - Interface

Ini tempat kau bercakap dengan AURA.

```text
Telegram
```

Start dengan Telegram dulu.

Pada masa depan boleh tambah:

```text
Telegram
Web
WhatsApp
```

Tapi untuk fasa awal, jangan tambah terlalu banyak interface. Fokus kepada Telegram sebab paling cepat untuk test dan automate.

---

## Layer 2 - Hermes Core

Ini ialah **muka AURA**.

```text
Hermes Core
```

Hermes Core bukan LLM. Hermes Core bukan OpenRouter. Hermes Core ialah experience layer / command layer / assistant shell.

Kerja Hermes Core:

- ✅ Terima arahan daripada Telegram
- ✅ Faham intent asas
- ✅ Pilih module yang sesuai
- ✅ Monitor task
- ✅ Bagi status balik kepada user
- ✅ Handle approval / Human In The Loop
- ✅ Return final response ke Telegram

Contoh command:

```text
/research NVDA
/research ranhill
/daily
/content
/saklomak
/trading
/memory
/help
```

Semua arahan masuk ke Hermes Core dahulu.

Analogi:

```text
Hermes = Receptionist / Front Desk / Command Centre
```

---

## Layer 3 - Antigravity Runtime

Inilah **enjin sebenar**.

```text
Antigravity SDK
```

Antigravity SDK bukan LLM. Dia bukan Claude, bukan GPT, bukan Gemini.

Antigravity SDK berfungsi sebagai runtime/orchestrator.

Kerja Antigravity Runtime:

- ✅ Reasoning
- ✅ Routing
- ✅ Workflow execution
- ✅ Tool calling
- ✅ Memory access
- ✅ Module execution
- ✅ Decide sama ada task simple atau complex
- ✅ Decide sama ada perlukan LangGraph / CrewAI atau tidak

Analogi:

```text
Hermes = Receptionist
Antigravity = Operation Manager
OpenRouter = Model Gateway
Claude/GPT/Gemini = Otak / Chef
```

---

## Layer 4 - Router

Router ialah bahagian yang tentukan request patut pergi ke mana.

Contoh:

```text
User: /research ranhill
```

Router fikir:

```text
Intent: Trading research
Module: Trading
Complexity: Medium
Need HITL: No
Need LangGraph: Maybe no
Need CrewAI: No
```

Contoh lain:

```text
User: Buat 30 content Saklomak dan post ke Facebook
```

Router fikir:

```text
Intent: Content generation + publishing
Module: Content / Saklomak
Complexity: Medium
Need HITL: Yes, before publish
Need LangGraph: No
Need CrewAI: No
```

---

# Layer 5 - Modules

Ini benda paling penting yang hilang sebelum ni.

```text
Modules

├─ Trading
├─ Content
├─ Saklomak
├─ Personal
├─ Research
├─ Coding
└─ M365
```

Setiap module berdikari.

Prinsip penting:

> **Everything is module. Only complex things become crew. Only deep reasoning becomes graph.**

---

## Trading Module

Trading Module tahu tentang:

- Bursa
- US market
- HK market
- ETFs
- TradingView
- Portfolio
- Watchlist
- Screener
- FA/TA
- News sentiment
- Risk scoring

Contoh command:

```text
/research ranhill
/watchlist
/portfolio
/scan fbmscap
/compare RANHILL LFG MSC
```

Output contoh:

```text
RANHILL Quick View

Status: Watch / Accumulate / Avoid
Risk: Medium
Catalyst: Pending
Suggested Action: Tunggu breakout / tunggu pullback
```

Nota penting:

- Trading Module boleh bagi research dan scoring.
- Tidak execute buy/sell secara automatik.
- Semua trade decision masih Human In The Loop.

---

## Content Module

Content Module tahu tentang:

- Facebook
- Instagram
- Threads
- TikTok
- Canva
- Airtable Content Station
- Caption
- Hashtag
- Content calendar
- Brand tone

Contoh command:

```text
/content saklomak 7 hari
/generate caption salmon smoked
/rewrite caption lebih santai
```

Output boleh dihantar ke:

```text
Airtable Content Station
Telegram preview
CSV
Markdown
```

---

## Saklomak Module

Saklomak Module tahu tentang:

- Product
- Order
- Campaign
- Content Station
- Customer notes
- Sales summary
- Brand voice
- Stock status

Contoh command:

```text
/saklomak daily
/saklomak content minggu ni
/saklomak campaign merdeka
/saklomak stock
```

Output contoh:

```text
Saklomak Daily Brief

Sales Yesterday: RMxxx
Top Product: xxx
Low Stock: xxx
Suggested Content: xxx
```

---

## Personal Module

Personal Module untuk benda harian Khairul OS.

Tahu tentang:

- Daily brief
- Reminders
- Study plan AZ-104
- Personal finance notes
- Family planning notes
- Habit tracker
- Task reminders

Contoh command:

```text
/daily
/today
/az104
/remind
/habit
```

---

## Research Module

Research Module untuk general research.

Contoh command:

```text
/research topic
/deepresearch topic
/summarise link
```

Simple research boleh jalan direct menggunakan tool search + model.

Deep research boleh panggil LangGraph.

---

## Coding Module

Coding Module untuk code tasks.

Contoh:

```text
/code review
/fix error
/explain code
/create script
```

Module ini boleh connect ke repo atau local project pada masa depan.

---

## M365 Module

M365 Module untuk kerja enterprise / IT Infra.

Contoh:

```text
/m365 draft email
/m365 summarise meeting
/m365 find policy
/m365 powerbi note
/m365 exchange sop
```

Module ini boleh bantu untuk kerja seperti:

- Exchange Hybrid
- Entra ID
- Power BI
- Intune
- Freshservice notes
- SOP drafting
- Email drafting

---

# Layer 6 - Memory

Memory guna Supabase.

```text
Memory

├─ Conversations
├─ Preferences
├─ Knowledge
├─ Activities
└─ Long-term facts
```

Yang kau dah bina dalam AURA v5 sebenarnya berguna dan jangan buang.

Memory yang patut dikekalkan:

- `memories`
- `aura_conversations`
- `aura_preferences`
- `aura_knowledge`
- `activity_logs`
- RPC `search_memories`
- Full-Text Search index
- Supabase Service Role Key configuration

Memory bukan tempat semua benda dicampak. Memory perlu ada rules.

Contoh memory yang sesuai:

- User preference
- Long-term project info
- Watchlist trading
- Saklomak brand tone
- Important architecture decision
- Recurring workflow

Contoh yang tidak sesuai:

- Temporary chat noise
- Raw logs terlalu banyak
- Duplicate output
- Data sensitif tanpa sebab

---

# Layer 7 - Tools

Tools ialah benda yang agent boleh guna untuk buat kerja.

```text
Tools

├─ Web Search
├─ Airtable
├─ Telegram
├─ Shopify
├─ EasyStore
├─ TradingView
├─ Google Drive
├─ Supabase
├─ File Generator
└─ PDF/Excel/Markdown Export
```

Tools bukan agent.

Tools cuma capability.

Contoh:

```text
Tool: sendTelegramMessage()
Tool: searchWeb()
Tool: updateAirtableRecord()
Tool: getPortfolio()
Tool: saveMemory()
Tool: generatePDF()
```

---

# Layer 8 - OpenRouter Models

Baru di layer ini kita panggil model.

```text
OpenRouter
   ↓
Claude
Gemini
GPT
DeepSeek
Qwen
Kimi
```

Ini penting:

> OpenRouter bukan runtime.  
> OpenRouter bukan memory.  
> OpenRouter bukan workflow.  
> OpenRouter cuma model provider / model gateway.

Kelebihan OpenRouter:

- Satu API key boleh access banyak model
- Senang tukar model ikut module
- Trading boleh guna model lain
- Content boleh guna model lain
- Coding boleh guna model lain
- Backup model kalau satu provider down

Contoh mapping:

```text
Trading Module  -> Claude / GPT
Content Module  -> Gemini / Claude
Coding Module   -> DeepSeek / Claude
Research Module -> GPT / Gemini / Perplexity-style model
```

---

# Human In The Loop (HITL)

Ini wajib ada.

Sebab AURA bukan chatbot biasa.

AURA ialah assistant yang boleh buat tindakan.

Jadi perlu kawalan manusia.

---

## HITL Tahap 1 - Auto Terus

Untuk task selamat.

Contoh:

```text
/research ranhill
/daily
/summarise note
/generate idea
```

AURA boleh terus jalan dan return output.

---

## HITL Tahap 2 - Minta Approval

Untuk task yang melibatkan publish, update, atau create data.

Contoh:

```text
Generate 30 content dan post ke Facebook
```

Hermes response:

```text
Saya dah generate 30 content.

Approve untuk publish?

[✅ Publish]
[✏️ Edit]
[❌ Cancel]
```

---

## HITL Tahap 3 - Critical Action

Untuk tindakan berisiko tinggi.

Contoh:

```text
Post campaign RM500
Send email board
Delete data
Execute trade
Update production database
```

Hermes wajib tanya confirmation.

Pattern:

```text
Critical action detected.

Action: Send email to Board
Impact: External / high visibility
Need approval: Yes

[✅ Confirm]
[❌ Cancel]
```

Prinsip:

```text
Human-Governed AI
```

Bukan:

```text
Fully Autonomous AI
```

---

# LangGraph Duduk Mana?

LangGraph jangan jadi backbone.

LangGraph hanya dipanggil oleh module bila perlu deep workflow atau loop.

```text
Module

└─ Research
      ├─ Simple Research
      └─ Deep Research
              ↓
          LangGraph
```

Contoh simple research:

```text
/research ranhill
```

Tak perlu graph.

Contoh deep research:

```text
Bedah RANHILL, LFG, MSC.

Cari:
- FA
- TA
- News
- EPF Holding
- Debt
- Catalyst

Buat report 10 muka surat.
```

Baru masuk LangGraph.

LangGraph sesuai untuk:

- Multi-step research
- Loop search-analysis-verify
- State machine
- Retry logic
- Long-running workflow
- Deep report generation

---

# CrewAI Duduk Mana?

CrewAI juga jangan jadi backbone.

CrewAI ialah optional expert team.

```text
Trading Module
   ↓
Need experts?
   ↓
CrewAI
```

Kalau task simple, tak perlu CrewAI.

Kalau task complex, baru panggil CrewAI.

Contoh:

```text
CrewAI

├─ FA Agent
├─ TA Agent
├─ Risk Agent
├─ News Agent
└─ Final Analyst
```

CrewAI sesuai untuk:

- Multiple expert roles
- Review from different perspectives
- Structured comparison
- Debate / validation
- Scoring framework

---

# Architecture Akhir AURA v6

```text
Telegram
    ↓

Hermes Core
    ↓

Antigravity SDK
    ↓

Router
    ↓

Modules
    ├─ Trading
    ├─ Content
    ├─ Saklomak
    ├─ Research
    ├─ M365
    ├─ Coding
    └─ Personal
    ↓

Memory
(Supabase)
    ↓

Tools
    ├─ Web Search
    ├─ Airtable
    ├─ Telegram
    ├─ Shopify
    ├─ EasyStore
    ├─ TradingView
    ├─ Google Drive
    ├─ Supabase
    └─ File Generator
    ↓

OpenRouter
    ↓

Claude
Gemini
GPT
DeepSeek
Qwen
Kimi
```

---

# Request Flow Example 1 - Simple Trading Research

```text
User Telegram:
/research ranhill

↓

Hermes Core receives command

↓

Antigravity Router detects:
Intent = Trading Research
Module = Trading
Risk = Low
HITL = No

↓

Trading Module runs:
- Get price data
- Get news
- Get watchlist context
- Get memory

↓

OpenRouter calls selected model

↓

Model generates analysis

↓

Hermes returns response to Telegram
```

---

# Request Flow Example 2 - Content With Approval

```text
User Telegram:
Buat 10 content Saklomak untuk minggu ni dan post ke FB

↓

Hermes Core receives command

↓

Router detects:
Intent = Content generation + publish
Module = Content + Saklomak
Risk = Medium
HITL = Required

↓

Content Module generates content

↓

Hermes sends preview:
Saya dah generate 10 content.
Approve untuk publish?

[✅ Publish]
[✏️ Edit]
[❌ Cancel]

↓

User approve

↓

Tool posts to Facebook / schedules content

↓

Hermes confirms completion
```

---

# Request Flow Example 3 - Deep Research With LangGraph

```text
User Telegram:
Bedah RANHILL, LFG, MSC untuk swing 4-8 bulan.
Cari FA, TA, debt, news, EPF/KWAP holding dan catalyst.

↓

Hermes Core receives command

↓

Router detects:
Intent = Deep Trading Research
Module = Trading
Complexity = High
Need LangGraph = Yes
Need CrewAI = Optional

↓

Trading Module starts Deep Research Flow

↓

LangGraph runs loop:
Search → Analyse → Verify → Score → Summarise

↓

Optional CrewAI:
FA Agent + TA Agent + Risk Agent + News Agent

↓

Final report generated

↓

Hermes returns report to Telegram
```

---

# Request Flow Example 4 - Critical Action

```text
User Telegram:
Send email to Board about project status

↓

Hermes Core receives command

↓

Router detects:
Intent = Email sending
Module = M365
Risk = High
HITL = Critical

↓

M365 Module drafts email

↓

Hermes asks approval:

Critical action detected.

Action: Send email to Board
Need approval: Yes

[✅ Send]
[✏️ Edit]
[❌ Cancel]

↓

Only send if user approves
```

---

# Decision: Apa Perlu Buat Dengan AURA v5

Kalau aku jadi kau hari ni:

## Jangan Buat

- ❌ Delete AURA
- ❌ Rewrite semua sekali gus
- ❌ Tambah Crew lagi
- ❌ Tambah LangGraph lagi
- ❌ Campur semua feature dalam core
- ❌ Jadikan semua benda agent
- ❌ Jadikan semua benda autonomous

## Buat

- ✅ Freeze AURA v5
- ✅ Archive sebagai backup
- ✅ Ambil Memory System
- ✅ Ambil Supabase schema
- ✅ Ambil Telegram integration
- ✅ Ambil OpenRouter config
- ✅ Buang complexity
- ✅ Build Hermes Core baru
- ✅ Antigravity jadi runtime
- ✅ Semua benda lain jadi module
- ✅ Tambah HITL dari awal

---

# Naming Concept

Nama architecture:

```text
AURA v6 = Khairul OS
```

Bukan sekadar:

- AI Project
- Trading Bot
- Content System
- Chatbot

Tapi:

> Satu operating system peribadi yang kebetulan menggunakan AI.

---

# Guiding Principle AURA v6

```text
Simple core.
Powerful modules.
Human controlled.
Model flexible.
Memory persistent.
Automation safe.
```

---

# Final Architecture Philosophy

AURA v6 patut rasa macam Hermes dari sudut user experience:

```text
Telegram-first
Command-based
Fast feedback
Cronjob friendly
Automation ready
```

Tapi di belakang tabir:

```text
Antigravity Runtime
OpenRouter Models
Supabase Memory
Modular Tools
Optional LangGraph
Optional CrewAI
Human In The Loop
```

Ini architecture yang boleh hidup lama sebab core dia kecil, module dia jelas, dan complexity hanya muncul bila benar-benar perlu.

---

# One-Liner Summary

> **AURA v6 ialah Hermes-style personal operating system, powered by Antigravity SDK, model-flexible via OpenRouter, memory-backed by Supabase, modular by design, and governed by Human In The Loop.**
