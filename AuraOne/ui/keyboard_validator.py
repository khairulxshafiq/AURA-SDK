"""
Inline Keyboard Validator module.
Validates Telegram InlineKeyboardMarkup before sending messages.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Set, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

# Registry of valid callback prefixes/exact strings, their handlers, and whether state updates exist
REGISTERED_CALLBACK_HANDLERS: Dict[str, Dict[str, bool]] = {
    "hashtag_on": {"handler_exists": True, "state_update_exists": True},
    "hashtag_off": {"handler_exists": True, "state_update_exists": True},
    "toggle:": {"handler_exists": True, "state_update_exists": True},
    "platform_next": {"handler_exists": True, "state_update_exists": True},
    "sub:": {"handler_exists": True, "state_update_exists": True},
    "sub_next": {"handler_exists": True, "state_update_exists": True},
    "confirm_platform:": {"handler_exists": True, "state_update_exists": True},
    "gnews_cat:": {"handler_exists": True, "state_update_exists": True},
    "viral_menu:": {"handler_exists": True, "state_update_exists": True},
    "gnews_back": {"handler_exists": True, "state_update_exists": True},
    "loc_action:": {"handler_exists": True, "state_update_exists": True},
    "do_scrape:": {"handler_exists": True, "state_update_exists": True},
    "do_summarize:": {"handler_exists": True, "state_update_exists": True},
}

def _find_matching_handler(callback_data: str) -> Tuple[bool, bool]:
    """Finds if a callback_data has a registered handler and state update logic."""
    for pattern, info in REGISTERED_CALLBACK_HANDLERS.items():
        if pattern.endswith(":") and callback_data.startswith(pattern):
            return info["handler_exists"], info["state_update_exists"]
        elif callback_data == pattern:
            return info["handler_exists"], info["state_update_exists"]
    return False, False

def validate_inline_keyboard(keyboard: InlineKeyboardMarkup) -> bool:
    """
    Validates an InlineKeyboardMarkup.
    Checks:
    1. Callback exists for non-URL buttons.
    2. Callback data is unique for every button.
    3. Callback handler exists for callback data.
    4. State update logic exists for callback data.

    Raises ValueError if validation fails.
    """
    if not keyboard or not hasattr(keyboard, "inline_keyboard"):
        return True

    seen_callbacks: Set[str] = set()

    for row_idx, row in enumerate(keyboard.inline_keyboard):
        for col_idx, button in enumerate(row):
            # URL buttons don't have callback_data
            if getattr(button, "url", None):
                continue

            callback_data = getattr(button, "callback_data", None)

            # 1. Check callback exists
            if not callback_data:
                err_msg = f"Keyboard validation failed at row {row_idx}, col {col_idx}: button text '{button.text}' has no callback_data!"
                logger.error(err_msg)
                raise ValueError(err_msg)

            # 2. Check callback data uniqueness
            if callback_data in seen_callbacks:
                err_msg = f"Keyboard validation failed at row {row_idx}, col {col_idx}: duplicate callback_data '{callback_data}' found!"
                logger.error(err_msg)
                raise ValueError(err_msg)

            seen_callbacks.add(callback_data)

            # 3. Check callback handler exists & 4. state update exists
            handler_exists, state_update_exists = _find_matching_handler(callback_data)
            if not handler_exists:
                err_msg = f"Keyboard validation failed: no callback handler registered for callback_data '{callback_data}'!"
                logger.error(err_msg)
                raise ValueError(err_msg)

            if not state_update_exists:
                err_msg = f"Keyboard validation failed: no state update logic registered for callback_data '{callback_data}'!"
                logger.error(err_msg)
                raise ValueError(err_msg)

    return True
