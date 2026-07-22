import sqlite3
from storage.db import get_db_connection

def save_user_location(user_id: int, latitude: float, longitude: float, address: str) -> None:
    """Save or update user's last known live location."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_location (user_id, latitude, longitude, address, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            latitude=excluded.latitude,
            longitude=excluded.longitude,
            address=excluded.address,
            updated_at=CURRENT_TIMESTAMP
    """, (user_id, latitude, longitude, address))
    conn.commit()
    conn.close()

def get_user_location(user_id: int) -> dict | None:
    """Retrieve user's last known live location."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude, address, updated_at FROM user_location WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def save_user_place(user_id: int, place_name: str, latitude: float, longitude: float, address: str) -> None:
    """Save or update a named place (/sethome, /sethq)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_saved_places (user_id, place_name, latitude, longitude, address, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, place_name) DO UPDATE SET
            latitude=excluded.latitude,
            longitude=excluded.longitude,
            address=excluded.address,
            updated_at=CURRENT_TIMESTAMP
    """, (user_id, place_name.lower(), latitude, longitude, address))
    conn.commit()
    conn.close()

def get_user_places(user_id: int) -> dict:
    """Retrieve all saved places for a user."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT place_name, latitude, longitude, address FROM user_saved_places WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    places = {}
    for r in rows:
        places[r["place_name"].lower()] = {
            "lat": r["latitude"],
            "lon": r["longitude"],
            "address": r["address"]
        }
    return places
