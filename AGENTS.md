# AGENTS.md — Global Guide for Agent Aura

Welcome, Agent! This repository powers **Agent Aura** running on Antigravity SDK over a Linux VPS.

## 🗂️ Core Architecture & Index
- `AuraOne/`: Core application workspace.
  - `main.py`: Entry point for Aura execution.
  - `tools.py` & `memory.py`: Native tools and memory handlers.
  - `persona.txt`: System persona configuration.
- `AuraOne/skills/`: Individual modular skills (contains `SKILL.md` per skill).
- `AuraOne/reference_blueprints/`: Specialized documentation for tools & APIs (`airtable_tools.md`, `antigravity_alignment.md`, etc.).
- `AuraOne/LUMA_MEMORY.md`: Persistence & memory state tracking.

## 🔀 Git & Branching Rules (STRICT)
1. **NEVER push directly to `main` branch.**
2. **Feature Branches:** Every code modification, new feature, or bug fix MUST be made on a dedicated branch using the following naming convention:
   - `feature/description-yyyy-mm-dd` (e.g., `feature/airtable-sync-2026-07-22`)
   - `fix/issue-description-yyyy-mm-dd`
3. **Pull Request & Merge:**
   - Always commit changes to the feature branch first.
   - Only merge to `main` after testing and verification.
4. **Versioning / Restoration:**
   - Create a clean git tag or descriptive commit before merging so code can easily be restored/reverted to any previous state (e.g., 5 days ago).

## 🛑 Rules for Modifying Code
1. **Never edit `main.py` directly** without testing on a feature branch.
2. **Adding Tools:** If you build a new tool, define it in `AuraOne/tools.py` and create/update its respective blueprint in `AuraOne/reference_blueprints/`.
3. **VPS Sync:** Always make sure changes work smoothly with `sync_vps.sh`.
4. **Environment Variables:** Never commit secrets! Update `.env.example` if new keys are added.
