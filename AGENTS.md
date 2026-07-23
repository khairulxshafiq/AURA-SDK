# AGENTS.md — Rules & Constraints for Agent Aura

Welcome, Agent! You are working inside the AURA-SDK repository. 
Refer to `README.md` for high-level system architecture and systemd services.

---

## 🗂️ Codebase Index
- `AuraOne/`: Core application workspace (`main.py`, `config.py`, `tools.py`, `memory.py`).
- `AuraOne/config.py`: Centralized environment configurations & project constants.
- `AuraOne/storage/`: SQLite Repository Pattern layer (`db.py`, `memory_repository.py`, `location_repository.py`, `draft_repository.py`).
- `AuraOne/tools/`: Atomic modular tools (`web_scraper.py`, `search_engine.py`, `location_service.py`, `apify_service.py`, `publisher_service.py`).
- `AuraOne/skills/`: Modular agent skills. Each skill contains a `SKILL.md`.
- `AuraOne/reference_blueprints/`: Architectural blueprints and API schemas.
- `AuraOne/LUMA_MEMORY.md`: Persistence state tracking.

---

## ⚙️ Environment & Storage Specifications
- **Google Drive API Folder Split Storage**:
  - `GDRIVE_IMAGE_FOLDER_ID` (`1ntdhPOq3Z7oNXLDqQgVyVQS6tIMoArc3`): Folder khas muat naik fail imej (`web-*.jpg`/`png`).
  - `GDRIVE_DUMP_FOLDER_ID` (`1Ybx7mBAKksI2VcagHAqOuKkf8pjbvYwa`): Folder khas muat naik draf/dump artikel teks (`web-*.txt`).

---

## 🔀 Git & Branching Rules (STRICT)

1. **NEVER push or commit directly to the `main` branch.**
2. **Feature Branching Mandatory:** Create a dedicated branch before making modifications:
   - `feature/description-yyyy-mm-dd`
   - `fix/issue-description-yyyy-mm-dd`
3. **Merging:** Verify code functionality locally/isolated before submitting a PR or merging to `main`.
4. **Clean Commits:** Provide detailed commit messages so revisions can easily be reverted (e.g., restoring state from 5 days ago).

## 🔁 Pull Request Policy for LLMs / Agents / LUMA

Any change made by an LLM, agent, or automation tool in this repository must follow this workflow:

1. **Create or switch to a dedicated branch first** before editing files.
2. **Do not commit directly to `main`.**
3. **Do not merge directly to `main`.** If a change is ready, create a Pull Request and wait for review/approval.
4. **If the agent is asked to merge**, it must first open or update a PR, then stop unless explicit approval is given.
5. **If branch creation is not possible, the agent must stop and ask for human confirmation instead of forcing a direct push/merge.**
6. **Every PR should include a short summary of what changed, why it changed, and any validation performed.**

This rule applies to all automation workflows, including LUMA, Copilot, Cline, or any other agent that touches the repository.

---

## 🛑 Code Modification Guardrails

1. **Isolation:** Do NOT modify `main.py` directly without testing inside a feature branch.
2. **Secrets:** NEVER hardcode API keys or secrets into source files. Ensure new key variables are mapped in `.env.example`.
3. **Tool Registration:** When adding new tools, register them in `AuraOne/tools.py` and document the blueprint in `AuraOne/reference_blueprints/`.
4. **System Protection:** Do not run dangerous shell/terminal commands (`rm -rf`, system-wide `chmod 777`).
