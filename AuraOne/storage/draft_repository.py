from storage.db import get_db_connection

def save_draft(
    user_id: int,
    title: str,
    master_article: str,
    hashtags: str,
    image_url: str,
    telegram_file_id: str,
    counter_val: int,
    source_url: str,
    selected_platform: str = "",
    platform_draft: str = "",
    state: str = ""
) -> None:
    """Save or overwrite the active draft for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO drafts (
            user_id, title, master_article, hashtags, image_url, telegram_file_id, counter_val, source_url, 
            selected_platform, platform_draft, state, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET 
            title=excluded.title, 
            master_article=excluded.master_article, 
            hashtags=excluded.hashtags, 
            image_url=excluded.image_url, 
            telegram_file_id=excluded.telegram_file_id, 
            counter_val=excluded.counter_val, 
            source_url=excluded.source_url, 
            selected_platform=excluded.selected_platform, 
            platform_draft=excluded.platform_draft, 
            state=excluded.state,
            created_at=CURRENT_TIMESTAMP
    """, (
        user_id, title, master_article, hashtags, image_url, telegram_file_id, counter_val, source_url,
        selected_platform, platform_draft, state
    ))
    conn.commit()
    conn.close()

def update_platform_draft(user_id: int, platform: str, draft_text: str, state: str = "") -> None:
    """Update selected platform, draft text, and state for an existing draft."""
    conn = get_db_connection()
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
    conn = get_db_connection()
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
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            title, master_article, hashtags, image_url, telegram_file_id, counter_val, source_url, 
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
            "telegram_file_id": row[4],
            "counter_val": row[5],
            "source_url": row[6],
            "selected_platform": row[7],
            "platform_draft": row[8],
            "state": row[9]
        }
    return None

def clear_draft(user_id: int) -> None:
    """Clear the active draft for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
