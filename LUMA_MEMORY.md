# 🧠 LUMA Memory — AURA-SDK Living Document

> Fail ini auto-diupdate oleh LUMA selepas setiap session kerja.
> Antigravity (Mac) juga baca fail ni untuk context.

---

## 📅 Last Updated
_2026-07-11 19:05_ oleh LUMA

---

## 🏗️ Project Status

### AURA-SDK Architecture
- [x] Core agent loop (main.py)
- [x] Tool registration system (tools.py)
- [ ] Skill module framework
- [ ] Memory/persistence layer
- [ ] API integrations

### Infrastructure
- [x] VPS setup (Tencent Cloud)
- [x] LUMA boot animation
- [x] agy wrapper dengan animation
- [x] AGENTS.md configured
- [x] Git remote setup
- [x] Auto-sync dengan Mac (Dipindahkan service config & venv terus ke projects workspace)

---

## 📝 Conversation History Summary
- **Session #1 (Greeting, Sync & Service Migration)**: Memulakan chat, check status AURA bot. Mengalihkan semua fail sebenar (`.env`, `.venv`, `sessions`) dari `/home/ubuntu/AURA-SDK` ke development workspace di `/home/ubuntu/projects/AURA-SDK/AuraOne/`. Mengemaskini `aura.service` untuk point terus ke workspace pembangunan dan memadam klon pendua yang tidak lagi diperlukan.

---

## 🧩 Decisions Made
| Tarikh | Decision | Reason |
|--------|----------|--------|
| 2026-07-11 | VPS: Tencent Cloud | Sudah sedia ada |
| 2026-07-11 | Stack: Python + agy SDK | Sesuai dengan Gemini ecosystem |
| 2026-07-11 | Alih Service ke projects/ | Mengelakkan kekeliruan klon pendua, memudahkan code changes di-apply secara langsung |

---

## 🎯 Next Actions
- [ ] Build first custom tool in `tools.py`
- [ ] Start building skill modules



---

## 💡 Khairulshafiq Working Style Notes
- Prefer casual BM/English
- Direct executor — tak suka tunggu lama
- Focus pada practical results
