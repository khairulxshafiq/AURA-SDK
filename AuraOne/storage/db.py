import os
import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger("aura.storage.db")

def get_db_connection() -> sqlite3.Connection:
    """Create and return a connection to the SQLite database with 20s lock timeout."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    return conn

def init_db() -> None:
    """Initialize the SQLite database and create all tables if they do not exist."""
    conn = get_db_connection()
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

    # Table for storing user live location
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_location (
            user_id INTEGER PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            address TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Table for storing user saved places (/sethome, /sethq)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_saved_places (
            user_id INTEGER,
            place_name TEXT,
            latitude REAL,
            longitude REAL,
            address TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, place_name)
        )
    """)

    # Table for active content drafts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            user_id INTEGER PRIMARY KEY,
            title TEXT,
            master_article TEXT,
            hashtags TEXT,
            image_url TEXT,
            telegram_file_id TEXT,
            counter_val INTEGER,
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
    logger.info("SQLite database tables initialized.")
