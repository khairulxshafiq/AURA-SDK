import re
import json
import html as _html_mod
import logging
from telegram import Update, LinkPreviewOptions
from telegram.error import BadRequest
import storage.memory_repository as memory_repo
import storage.draft_repository as draft_repo
from tools.publisher_service import _upload_article_dump_to_github
from ui.keyboards import _get_platform_keyboard

logger = logging.getLogger("aura.ui.formatters")

_REASONING_PATTERN = re.compile(
    r"^#{1,3}\s*(Ringkasan Penaakulan|Proses Delegasi|Analisis|Reasoning|"
    r"Keputusan|Delegation|Tool Call|Internal Analysis|Chain.of.Thought|"
    r"Debug|Langkah|Delegasi)[^\n]*\n?",
    re.IGNORECASE | re.MULTILINE
)

def _clean_response(text: str) -> str:
    """Strip internal reasoning headers for normal (non-debug) users."""
    cleaned = _REASONING_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def _send_safe_message(text: str, max_length: int = 4000) -> str:
    """Guard Telegram message length to avoid BadRequest text too long errors."""
    if len(text) > max_length:
        return text[:max_length] + "\n\n⚠️ *(Respon dipotong kerana melebihi had Telegram)*"
    return text

async def _send_telegram_msg(update: Update, text: str, parse_mode: str = None, reply_markup=None, disable_preview: bool = False):
    """Send Telegram message with markdown/HTML support, automatically falling back to plain text if parsing fails."""
    if reply_markup and hasattr(reply_markup, "inline_keyboard"):
        from ui.keyboard_validator import validate_inline_keyboard
        validate_inline_keyboard(reply_markup)

    target_parse_mode = parse_mode
    target_text = text

    link_preview_opts = LinkPreviewOptions(is_disabled=True) if disable_preview else None

    if parse_mode == "HTML":
        target_parse_mode = "HTML"
        target_text = text
    elif parse_mode in ["Markdown", "MarkdownV2", "markdown", "markdownv2"]:
        placeholder_map = {}
        counter = 0

        def store_link(match):
            nonlocal counter
            key = f"___LINK_PLACEHOLDER_{counter}___"
            counter += 1
            link_text = _html_mod.escape(match.group(1))
            url = match.group(2)
            placeholder_map[key] = f'<a href="{url}">{link_text}</a>'
            return key

        text_with_placeholders = re.sub(r"\[(.*?)\]\((https?://[^\s\)]+)\)", store_link, text)
        escaped = _html_mod.escape(text_with_placeholders)

        for key, val in placeholder_map.items():
            escaped = escaped.replace(key, val)

        escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"\*(.*?)\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"_(.*?)_", r"<i>\1</i>", escaped)
        escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)

        target_text = escaped
        target_parse_mode = "HTML"

    thread_id = None
    if update.message:
        thread_id = getattr(update.message, "message_thread_id", None)
    elif update.callback_query and update.callback_query.message:
        thread_id = getattr(update.callback_query.message, "message_thread_id", None)

    try:
        if update.message:
            await update.message.reply_text(target_text, parse_mode=target_parse_mode, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(target_text, parse_mode=target_parse_mode, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
    except BadRequest as e:
        logger.warning(f"Telegram parse mode {target_parse_mode} failed. Falling back. Error: {e}")
        plain = re.sub(r"<[^>]+>", "", target_text)
        plain = re.sub(r"\[(.*?)\]\(https?://[^\s\)]+\)", r"\1", plain)
        plain = re.sub(r"https?://\S+", "", plain)
        plain = _html_mod.unescape(plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        try:
            if update.message:
                await update.message.reply_text(plain, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(plain, reply_markup=reply_markup, message_thread_id=thread_id, link_preview_options=link_preview_opts)
        except Exception as fallback_err:
            logger.error(f"Fallback text send failed: {fallback_err}")

async def _process_response_draft(user_id: int, chat_id: int, response_text: str, context, update) -> str:
    """Parse draft metadata tags from response_text, save the draft in SQLite,
    send preview image to Telegram, and return cleaned response text."""
    image_match = re.search(r"\[DRAFT_IMAGE:\s*(https?://[^\s\]]+)\]", response_text, re.IGNORECASE)
    title_match = re.search(r"\[DRAFT_TITLE:\s*(.+?)\]", response_text, re.IGNORECASE)
    source_match = re.search(r"\[DRAFT_SOURCE_URL:\s*(https?://[^\s\]]+)\]", response_text, re.IGNORECASE)
    master_match = re.search(r"\[DRAFT_MASTER_ARTICLE:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
    hashtags_match = re.search(r"\[DRAFT_HASHTAGS:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
    type_match = re.search(r"\[DRAFT_CONTENT_TYPE:\s*(.+?)\]", response_text, re.IGNORECASE)
    price_match = re.search(r"\[DRAFT_ORIGINAL_PRICE:\s*(.+?)\]", response_text, re.IGNORECASE)
    location_match = re.search(r"\[DRAFT_SELLER_LOCATION:\s*(.+?)\]", response_text, re.IGNORECASE)

    # Extract clean response text without [DRAFT_*] metadata tags as actual master article body fallback
    raw_body = re.sub(r"\[DRAFT_[A-Z_]+:\s*.+?\]", "", response_text, flags=re.IGNORECASE | re.DOTALL).strip()

    if title_match or master_match or (raw_body and len(raw_body) > 30):
        image_url = image_match.group(1).strip() if image_match else ""
        title = title_match.group(1).strip() if title_match else "Artikel Tanpa Tajuk"
        source_url = source_match.group(1).strip() if source_match else ""
        master_article = master_match.group(1).strip() if master_match else ""

        # Fallback to raw LLM response body if master_article tag is empty or static placeholder
        if not master_article or "Teks Master Article" in master_article or len(master_article) < 20:
            if raw_body and len(raw_body) > 20:
                master_article = raw_body

        hashtags = hashtags_match.group(1).strip() if hashtags_match else ""

        prefs = memory_repo.get_preferences()
        counter_str = prefs.get("image_counter", "0")
        try:
            counter = int(counter_str)
        except ValueError:
            counter = 0
        counter += 1
        memory_repo.update_preference("image_counter", str(counter))

        telegram_file_id = ""
        tg_cdn_url = ""
        if update.message and update.message.photo:
            telegram_file_id = update.message.photo[-1].file_id
            logger.info(f"Using incoming Telegram photo file_id: {telegram_file_id}")

        reply_markup = _get_platform_keyboard(state_dict)
        sent_photo_with_buttons = False

        # Telegram Preview Rule: If article_image_url exists, send image first using sendPhoto with Caption (Title, Source, Summary) + Inline Buttons. Do not send text-only message if image exists.
        if image_url and not telegram_file_id:
            try:
                title_part = f"📌 *{title}*"
                source_part = f"\n🌐 *Source:* `{source_url}`" if source_url else ""
                header_len = len(title_part) + len(source_part) + 80
                avail_summary_len = max(100, 1000 - header_len)
                summary_text = master_article[:avail_summary_len] if master_article else ""
                summary_part = f"\n📝 *Summary:*\n{summary_text}..." if summary_text else ""

                caption = f"{title_part}{source_part}{summary_part}\n\n👇 *Pilih platform & gaya penulisan di bawah untuk diolah:*"

                photo_msg = None
                if update.message:
                    photo_msg = await update.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                elif update.callback_query and update.callback_query.message:
                    photo_msg = await update.callback_query.message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )

                if photo_msg and photo_msg.photo:
                    telegram_file_id = photo_msg.photo[-1].file_id
                    sent_photo_with_buttons = True
                    logger.info(f"Successfully sent photo preview with caption & inline buttons. Cached Telegram file_id: {telegram_file_id}")
            except Exception as photo_err:
                logger.warning(f"Could not send photo preview ({image_url}): {photo_err}")

        if telegram_file_id:
            try:
                from tools.publisher_service import stage_image_telegram
                tg_cdn_url = await stage_image_telegram(context, telegram_file_id)
            except Exception as cdn_err:
                logger.warning(f"Could not resolve Telegram CDN URL: {cdn_err}")

        draft_repo.save_draft(
            user_id=user_id,
            title=title,
            master_article=master_article,
            hashtags=hashtags,
            image_url=image_url,
            telegram_file_id=telegram_file_id,
            counter_val=counter,
            source_url=source_url,
            state=initial_state,
            tg_cdn_url=tg_cdn_url
        )
        logger.info(f"Saved content draft for user {user_id}: {title} (counter_val={counter}, tg_cdn_url={tg_cdn_url[:30]}...)")

        import threading
        threading.Thread(
            target=_upload_article_dump_to_github,
            args=(title, master_article, hashtags, source_url, response_text, counter),
            daemon=True
        ).start()

        # If photo with caption and inline buttons was sent successfully, skip text-only message
        if sent_photo_with_buttons:
            return "[DRAFT_SENT_WITH_KEYBOARD]"

        # Fallback to text message + inline buttons if image does not exist or photo send failed
        display_article = master_article[:3500] if master_article else ""
        formatted_display = (
            f"📰 *MASTER ARTICLE (NEUTRAL CORE CONTEXT & STORY HUB)*\n\n"
            f"*{title}*\n\n"
            f"{display_article}\n\n"
            f"👇 *Sila pilih platform & gaya penulisan di bawah untuk diolah:*"
        )

        try:
            if update.message:
                await update.message.reply_text(
                    formatted_display,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(
                    formatted_display,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
        except Exception as msg_err:
            logger.warning(f"Markdown reply failed ({msg_err}), falling back to plain text delivery...")
            try:
                plain_display = (
                    f"📰 MASTER ARTICLE (NEUTRAL CORE CONTEXT & STORY HUB)\n\n"
                    f"{title}\n\n"
                    f"{display_article}\n\n"
                    f"👇 Sila pilih platform & gaya penulisan di bawah untuk diolah:"
                )
                if update.message:
                    await update.message.reply_text(
                        plain_display,
                        reply_markup=reply_markup
                    )
                elif update.callback_query and update.callback_query.message:
                    await update.callback_query.message.reply_text(
                        plain_display,
                        reply_markup=reply_markup
                    )
            except Exception as fallback_err:
                logger.error(f"Failed to send master article text message completely: {fallback_err}")

        return "[DRAFT_SENT_WITH_KEYBOARD]"

    return response_text
