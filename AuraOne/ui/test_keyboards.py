import unittest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui.keyboard_validator import validate_inline_keyboard, REGISTERED_CALLBACK_HANDLERS
from ui.keyboards import (
    _get_platform_keyboard,
    _get_sub_options_keyboard,
    _get_gnews_keyboard,
    _get_viral_confessions_keyboard,
    _get_direct_confirm_keyboard,
)

class TestTelegramInlineKeyboards(unittest.TestCase):

    def test_valid_keyboards_pass_validation(self):
        """Ensure built-in keyboards pass validation successfully."""
        state_data = {"selected": ["facebook"], "options": {"hashtags": True}}
        kb_sub = _get_sub_options_keyboard(state_data)
        self.assertTrue(validate_inline_keyboard(kb_sub))

        kb_plat = _get_platform_keyboard(state_data)
        self.assertTrue(validate_inline_keyboard(kb_plat))

        kb_gnews = _get_gnews_keyboard()
        self.assertTrue(validate_inline_keyboard(kb_gnews))

        kb_viral = _get_viral_confessions_keyboard(0)
        self.assertTrue(validate_inline_keyboard(kb_viral))

        kb_confirm = _get_direct_confirm_keyboard(["facebook"])
        self.assertTrue(validate_inline_keyboard(kb_confirm))

    def test_sub_options_keyboard_hashtag_toggle_buttons(self):
        """Verify hashtag_on and hashtag_off buttons are rendered with unique callback_data."""
        state_on = {"selected": ["facebook"], "hashtags": True, "options": {}}
        kb_on = _get_sub_options_keyboard(state_on)
        buttons_on = [btn for row in kb_on.inline_keyboard for btn in row]
        callbacks_on = [b.callback_data for b in buttons_on if b.callback_data]

        self.assertIn("hashtag_on", callbacks_on)
        self.assertIn("hashtag_off", callbacks_on)
        self.assertEqual(len(callbacks_on), len(set(callbacks_on)), "Callback data must be unique!")

        state_off = {"selected": ["facebook"], "hashtags": False, "options": {}}
        kb_off = _get_sub_options_keyboard(state_off)
        buttons_off = [btn for row in kb_off.inline_keyboard for btn in row]
        callbacks_off = [b.callback_data for b in buttons_off if b.callback_data]

        self.assertIn("hashtag_on", callbacks_off)
        self.assertIn("hashtag_off", callbacks_off)

    def test_reject_duplicate_callback_data(self):
        """Reject keyboard if duplicate callback_data exists."""
        dup_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Button A", callback_data="hashtag_on"),
                InlineKeyboardButton("Button B", callback_data="hashtag_on")
            ]
        ])
        with self.assertRaises(ValueError) as ctx:
            validate_inline_keyboard(dup_kb)
        self.assertIn("duplicate callback_data", str(ctx.exception))

    def test_reject_missing_callback_data(self):
        """Reject keyboard if a non-URL button has empty callback_data."""
        empty_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Button A", callback_data="")]
        ])
        with self.assertRaises(ValueError) as ctx:
            validate_inline_keyboard(empty_kb)
        self.assertIn("no callback_data", str(ctx.exception))

    def test_reject_unregistered_callback_handler(self):
        """Reject keyboard if callback_data has no registered handler."""
        unreg_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Button Unknown", callback_data="unknown_action_xyz")]
        ])
        with self.assertRaises(ValueError) as ctx:
            validate_inline_keyboard(unreg_kb)
        self.assertIn("no callback handler registered", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
