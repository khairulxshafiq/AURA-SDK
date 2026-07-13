import os
import sqlite3
from typing import Dict, List

# Database stored in sessions folder (ignored by git)
DB_PATH = os.path.join(os.path.dirname(__file__), "sessions", "aura_memory.db")

def init_db():
    """Initialize the SQLite memory database and create tables if they do not exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for key-value preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            val TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table for unstructured facts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT UNIQUE,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Recreate drafts table with support for active platform draft selections and interactive state
    cursor.execute("DROP TABLE IF EXISTS drafts")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            user_id INTEGER PRIMARY KEY,
            title TEXT,
            master_article TEXT,
            hashtags TEXT,
            image_url TEXT,
            source_url TEXT,
            selected_platform TEXT,
            platform_draft TEXT,
            state TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert default preferences if empty
    cursor.execute("SELECT COUNT(*) FROM preferences")
    if cursor.fetchone()[0] == 0:
        default_prefs = [
            ("owner_name", "Matrol (Khairulshafiq)"),
            ("primary_brand", "Sakluma"),
            ("working_style", "Clean, modular, BM/EN rojak mix")
        ]
        cursor.executemany("INSERT INTO preferences (key, val) VALUES (?, ?)", default_prefs)
        
    conn.commit()
    conn.close()


def save_draft(
    user_id: int,
    title: str,
    master_article: str,
    hashtags: str,
    image_url: str,
    source_url: str,
    selected_platform: str = "",
    platform_draft: str = "",
    state: str = ""
) -> None:
    """Save or overwrite the active draft for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO drafts (
            user_id, title, master_article, hashtags, image_url, source_url, 
            selected_platform, platform_draft, state, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET 
            title=excluded.title, 
            master_article=excluded.master_article, 
            hashtags=excluded.hashtags, 
            image_url=excluded.image_url, 
            source_url=excluded.source_url, 
            selected_platform=excluded.selected_platform, 
            platform_draft=excluded.platform_draft, 
            state=excluded.state,
            created_at=CURRENT_TIMESTAMP
    """, (
        user_id, title, master_article, hashtags, image_url, source_url,
        selected_platform, platform_draft, state
    ))
    conn.commit()
    conn.close()


def update_platform_draft(user_id: int, platform: str, draft_text: str, state: str = "") -> None:
    """Update only the selected platform, draft text, and state for an existing draft."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE drafts 
        SET selected_platform = ?, platform_draft = ?, state = ?
        WHERE user_id = ?
    """, (platform, draft_text, state, user_id))
    conn.commit()
    conn.close()


def update_draft_state(user_id: int, state: str) -> None:
    """Update only the state column for a draft."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE drafts 
        SET state = ?
        WHERE user_id = ?
    """, (state, user_id))
    conn.commit()
    conn.close()


def get_draft(user_id: int) -> dict | None:
    """Retrieve the active draft for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            title, master_article, hashtags, image_url, source_url, 
            selected_platform, platform_draft, state 
        FROM drafts WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "title": row[0],
            "master_article": row[1],
            "hashtags": row[2],
            "image_url": row[3],
            "source_url": row[4],
            "selected_platform": row[5],
            "platform_draft": row[6],
            "state": row[7]
        }
    return None





def clear_draft(user_id: int) -> None:
    """Clear the active draft for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()



def get_preferences() -> Dict[str, str]:
    """Retrieve all preferences as a key-value dictionary."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, val FROM preferences")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def update_preference(key: str, val: str) -> None:
    """Update or insert a key-value preference."""
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    conn.close()


def get_all_facts() -> List[Dict]:
    """Retrieve all saved facts ordered by creation date (newest first)."""
    conn = sqlite3.connect(DB_PATH)
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
        summary += f"- {k}: {v}\n"
    
    if facts:
        summary += "\nFakta penting yang telah dipelajari:\n"
        for f in facts:
            summary += f"- {f['content']} (Kategori: {f['category']})\n"
            
    summary += "\n(Gunakan maklumat di atas untuk menyesuaikan konteks jawapan dan tindakan anda.)"
    return summary
