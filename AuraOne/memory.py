# Façade module for backward compatibility
# Re-exports all storage repository functions from storage.*

from config import DB_PATH
from storage.db import init_db, get_db_connection
from storage.memory_repository import (
    get_preferences,
    update_preference,
    save_fact,
    delete_fact,
    get_all_facts,
    get_memory_summary,
    set_key_cooldown,
    is_key_on_cooldown,
    get_key_cooldown_remaining,
)
from storage.location_repository import (
    save_user_location,
    get_user_location,
    save_user_place,
    get_user_places,
)
from storage.draft_repository import (
    save_draft,
    update_platform_draft,
    update_draft_state,
    get_draft,
    clear_draft,
)

__all__ = [
    "DB_PATH",
    "init_db",
    "get_db_connection",
    "get_preferences",
    "update_preference",
    "save_fact",
    "delete_fact",
    "get_all_facts",
    "get_memory_summary",
    "set_key_cooldown",
    "is_key_on_cooldown",
    "get_key_cooldown_remaining",
    "save_user_location",
    "get_user_location",
    "save_user_place",
    "get_user_places",
    "save_draft",
    "update_platform_draft",
    "update_draft_state",
    "get_draft",
    "clear_draft",
]
