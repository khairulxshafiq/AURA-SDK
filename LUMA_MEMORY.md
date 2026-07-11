# 🧠 LUMA Memory — AURA-SDK Living Document

> Fail ini auto-diupdate oleh LUMA selepas setiap session kerja.
> Antigravity (Mac) juga baca fail ni untuk context.

---

## 📅 Last Updated
_2026-07-11 18:40_ oleh LUMA

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
- [x] Auto-sync dengan Mac (Symlinked development folder with service config)

---

## 📝 Conversation History Summary
- **Session #1 (Greeting & Status Check)**: Memulakan chat, check status AURA bot (`aura.service`), sync git repo `/home/ubuntu/AURA-SDK` dengan `/home/ubuntu/projects/AURA-SDK`, and buat symlinks `.env`, `.venv`, dan `sessions` ke development workspace.

---

## 🧩 Decisions Made
| Tarikh | Decision | Reason |
|--------|----------|--------|
| 2026-07-11 | VPS: Tencent Cloud | Sudah sedia ada |
| 2026-07-11 | Stack: Python + agy SDK | Sesuai dengan Gemini ecosystem |
| 2026-07-11 | Symlink .env/.venv | Memastikan development folder di `projects/AURA-SDK` boleh run secara standalone dengan config yang betul |

---

## 🎯 Next Actions
- [ ] Suggest user to update systemd `aura.service` pointing to `~/projects/AURA-SDK/AuraOne`
- [ ] Build first custom tool in `tools.py`
- [ ] Start building skill modules


---

## 💡 Khairulshafiq Working Style Notes
- Prefer casual BM/English
- Direct executor — tak suka tunggu lama
- Focus pada practical results
