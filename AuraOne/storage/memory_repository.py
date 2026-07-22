import time
import sqlite3
from typing import Dict, List
from storage.db import get_db_connection, init_db

def get_preferences() -> Dict[str, str]:
    """Retrieve all preferences as a key-value dictionary."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, val FROM preferences")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def update_preference(key: str, val: str) -> None:
    """Update or insert a key-value preference."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO preferences (key, val, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=CURRENT_TIMESTAMP
    """, (key, val))
    conn.commit()
    conn.close()

def save_fact(content: str, category: str = "general") -> bool:
    """Save a new fact about the user or system. Returns True if saved, False if duplicate."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO facts (content, category) VALUES (?, ?)", (content, category))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_fact(fact_id: int) -> None:
    """Delete a fact by its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    conn.close()

def get_all_facts() -> List[Dict]:
    """Retrieve all saved facts ordered by creation date (newest first)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, content, category FROM facts ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "content": row[1], "category": row[2]} for row in rows]

def get_memory_summary() -> str:
    """Compile a text block of all memories to inject into the system prompt."""
    init_db()
    prefs = get_preferences()
    facts = get_all_facts()

    summary = "═══════════════════════════════════════════\n"
    summary += "LONG-TERM MEMORY (MAKLUMAT KEKAL TENTANG BOS KAMU)\n"
    summary += "═══════════════════════════════════════════\n\n"

    summary += "Preferensi:\n"
    for k, v in prefs.items():
        if not k.startswith("cooldown:"):
            summary += f"- {k}: {v}\n"

    if facts:
        summary += "\nFakta penting yang telah dipelajari:\n"
        for f in facts:
            summary += f"- {f['content']} (Kategori: {f['category']})\n"

    summary += "\n(Gunakan maklumat di atas untuk menyesuaikan konteks jawapan dan tindakan anda.)"
    return summary

# ─── API Key Cooldown Tracking (Gemini F1-F10 429 rate limit management) ──────

def set_key_cooldown(api_key: str, cooldown_duration_seconds: float = 600.0) -> None:
    """Set persistent cooldown timestamp for a rate-limited Gemini API key."""
    expiry_time = time.time() + cooldown_duration_seconds
    update_preference(f"cooldown:{api_key}", str(expiry_time))

def is_key_on_cooldown(api_key: str) -> bool:
    """Check if an API key is currently under active cooldown."""
    prefs = get_preferences()
    cooldown_expiry_str = prefs.get(f"cooldown:{api_key}", "0.0")
    try:
        cooldown_expiry = float(cooldown_expiry_str)
    except ValueError:
        cooldown_expiry = 0.0
    return cooldown_expiry > time.time()

def get_key_cooldown_remaining(api_key: str) -> float:
    """Return remaining cooldown seconds for an API key, or 0.0 if expired."""
    prefs = get_preferences()
    cooldown_expiry_str = prefs.get(f"cooldown:{api_key}", "0.0")
    try:
        cooldown_expiry = float(cooldown_expiry_str)
    except ValueError:
        cooldown_expiry = 0.0
    remaining = cooldown_expiry - time.time()
    return max(0.0, remaining)
