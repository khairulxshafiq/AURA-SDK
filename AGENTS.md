# AGENTS.md — Global Guide for Agent Aura

Welcome, Agent! This repository powers **Agent Aura** running on Antigravity SDK over a Linux VPS.

## 🗂️ Core Architecture & Index
- `AuraOne/`: Core application workspace.
  - `main.py`: Entry point for Aura execution.
  - `tools.py` & `memory.py`: Native tools and memory handlers.
  - `persona.txt`: System persona configuration.
- `AuraOne/skills/`: Individual modular skills (contains `SKILL.md` per skill).
- `AuraOne/reference_blueprints/`: Specialized documentation for tools & APIs (`airtable_tools.md`, `antigravity_alignment.md`, etc.).
- `LUMA_MEMORY.md`: Persistence & memory state tracking.

## 🛑 Rules for Modifying Code
1. **Never edit `main.py` directly** without testing. Keep backups or feature branches.
2. **Adding Tools:** If you build a new tool, define it in `AuraOne/tools.py` and create/update its respective blueprint in `AuraOne/reference_blueprints/`.
3. **VPS Sync:** Always make sure changes work smoothly with `sync_vps.sh`.
4. **Environment Variables:** Never commit secrets! Update `.env.example` if new keys are added.
