"""
Location Pipeline — Location handling, weather, saved places.
Extracted from ui/telegram_bot.py (handle_location, sethome_command, sethq_command).
"""
import re
import logging

import storage.location_repository as location_repo
from tools.location_service import reverse_geocode_location, _get_weather_forecast
from ui.keyboards import _get_location_keyboard

logger = logging.getLogger("aura.pipelines.location_pipeline")


async def handle_location(update, context):
    """Process incoming location messages — reverse geocode, save, display card with quick actions."""
    user_id = update.effective_user.id
    message = update.message or update.edited_message
    if not message or not message.location:
        return

    lat = message.location.latitude
    lon = message.location.longitude

    address = await reverse_geocode_location(lat, lon)
    location_repo.save_user_location(user_id, lat, lon, address)

    if update.edited_message:
        logger.info(f"Quietly updated live location in database: {address}")
        return

    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    weather_info = await _get_weather_forecast(lat, lon)
    reply_markup = _get_location_keyboard(user_id, lat, lon)

    reply_text = (
        f"📍 *LOCATION UPDATE;*\n"
        f"───────────────\n\n"
        f"🏢 *Alamat Semasa*:\n`{address}`\n\n"
        f"📌 *Koordinat GPS*:\n`{lat}, {lon}`\n\n"
        f"🌤️ *Ramalan Cuaca Hari Ini*:\n{weather_info}\n\n"
        f"🗺️ *Pautan Peta*:\n[Buka Dalam Google Maps]({maps_url})\n\n"
        f"───────────────\n"
        f"💡 *Pilihan Pantas (Tekan butang di bawah)*:"
    )

    import html
    escaped = html.escape(reply_text)
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.*?)\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[(.*?)\]\((https?://.*?)\)", r'<a href="\2">\1</a>', escaped)

    thread_id = getattr(update.message, "message_thread_id", None) if update.message else None
    await update.message.reply_text(escaped, parse_mode="HTML", reply_markup=reply_markup, message_thread_id=thread_id)


async def handle_sethome(update, context):
    """Handle /sethome command — save current location as home."""
    user_id = update.effective_user.id
    loc = location_repo.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda tempat Rumah.")
        return
    location_repo.save_user_place(user_id, "home", loc["latitude"], loc["longitude"], loc["address"])
    await update.message.reply_text(
        f"🏠 *LOKASI RUMAH BERJAYA DISIMPAN!*\n"
        f"───────────────\n\n"
        f"• *Alamat*: `{loc['address']}`\n"
        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
        f"Kini setiap kali anda menghantar lokasi di Telegram, butang *[🏠 Navigasi Ke Rumah]* akan dipaparkan secara automatik!",
        parse_mode="Markdown"
    )


async def handle_sethq(update, context):
    """Handle /sethq command — save current location as HQ/work."""
    user_id = update.effective_user.id
    loc = location_repo.get_user_location(user_id)
    if not loc:
        await update.message.reply_text("⚠️ Sila hantar lokasi (location pin) anda di Telegram terlebih dahulu sebelum menanda HQ Sakluma.")
        return
    location_repo.save_user_place(user_id, "hq", loc["latitude"], loc["longitude"], loc["address"])
    await update.message.reply_text(
        f"🏢 *LOKASI HQ SAKLUMA BERJAYA DISIMPAN!*\n"
        f"───────────────\n\n"
        f"• *Alamat*: `{loc['address']}`\n"
        f"• *Koordinat*: `{loc['latitude']}, {loc['longitude']}`\n\n"
        f"Kini setiap kali anda menghantar lokasi di Telegram, butang *[🏢 Navigasi Ke HQ]* akan dipaparkan secara automatik!",
        parse_mode="Markdown"
    )
