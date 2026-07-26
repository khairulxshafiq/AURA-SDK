"""
Trade Pipeline — AURA-Trade Bursa Malaysia Co-Pilot commands.
Extracted from ui/telegram_bot.py (stock_command, screener_command).
"""
import json
import logging
import asyncio

from pipelines.llm_caller import call_supervisor_chat_model
from ui.formatters import _clean_response, _send_telegram_msg

logger = logging.getLogger("aura.pipelines.trade_pipeline")


async def handle_stock_command(update, context):
    """Handle /stock, /trade, /swing, or /position command using AURA-Trade engine."""
    chat_id = update.effective_chat.id
    raw_args = " ".join(context.args).strip() if context.args else ""
    cmd_name = update.message.text.split()[0].replace("/", "").lower() if update.message and update.message.text else "stock"

    if not raw_args:
        await _send_telegram_msg(
            update,
            "🏷️ *AURA-Trade Bursa Malaysia Co-Pilot*\n\n"
            "Sila masukkan simbol atau nama syarikat. Contoh:\n"
            "• `/stock 0181` (atau `/swing Aemulus` untuk Mode Swing)\n"
            "• `/position 1155` (untuk Mode Position / DCA)\n"
            "• `/screener swing` (untuk tapis shortlist)",
            parse_mode="Markdown"
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    from tools.trading_service import (
        resolve_symbol, get_live_quote, get_fundamentals,
        get_news_catalyst, compute_trade_plan
    )

    resolved_res = resolve_symbol(raw_args)
    symbol = resolved_res["matches"][0]["symbol"] if resolved_res.get("matches") else raw_args

    quote = await asyncio.to_thread(get_live_quote, symbol)
    if isinstance(quote, dict) and "error" in quote:
        await _send_telegram_msg(update, f"⚠️ {quote['error']}", parse_mode="Markdown")
        return

    fundamentals = await asyncio.to_thread(get_fundamentals, symbol)
    catalyst = await asyncio.to_thread(get_news_catalyst, symbol, sector=quote.get("sector"))

    # Calculate deterministic trade plan
    entry = quote.get("price", 0.0)
    atr = quote.get("atr14", 0.02)
    sl = round(max(0.01, entry - (1.5 * atr)), 3)
    tp1 = round(entry + (1.2 * (entry - sl)), 3)
    tp2 = round(entry + (2.2 * (entry - sl)), 3)

    trade_plan = compute_trade_plan(entry=entry, cut_loss=sl, targets=[tp1, tp2], capital=3000.0, symbol=symbol)

    mode = "POSITION" if cmd_name == "position" else ("SWING" if cmd_name == "swing" else "AUTO")

    prompt = (
        f"Anda adalah AURA-Trade. Sila analisis kaunter {symbol} ({quote.get('name')}) dalam MODE {mode} "
        f"berdasarkan data pasaran live di bawah.\n\n"
        f"DATA PASARAN LIVE:\n"
        f"- LIVE QUOTE: {json.dumps(quote, ensure_ascii=False)}\n"
        f"- FUNDAMENTALS: {json.dumps(fundamentals, ensure_ascii=False)}\n"
        f"- NEWS/CATALYST: {json.dumps(catalyst, ensure_ascii=False)}\n"
        f"- TRADE PLAN (DETERMINISTIC MATH): {json.dumps(trade_plan, ensure_ascii=False)}\n\n"
        f"Sila keluarkan Laporan 'BEST EYE-VIEW' mengikut gaya Bahasa Melayu santai AURA-Trade & template 8-bahagian rasmi."
    )

    try:
        response_text = await call_supervisor_chat_model(prompt)
        clean = _clean_response(response_text)
        await _send_telegram_msg(update, clean, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in stock_command: {e}")
        await _send_telegram_msg(update, f"⚠️ Gagal menjana laporan AURA-Trade untuk {symbol}.", parse_mode="Markdown")


async def handle_screener_command(update, context):
    """Handle /screener command to scan Bursa shortlist."""
    chat_id = update.effective_chat.id
    mode_arg = context.args[0].lower() if context.args else "swing"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    from tools.trading_service import screen_stocks

    shariah = True if "shariah" in [a.lower() for a in context.args] else False
    screener_res = screen_stocks(mode=mode_arg, shariah_only=shariah, limit=8)

    prompt = (
        f"Anda adalah AURA-Trade. User meminta screener saham Bursa Malaysia mode '{mode_arg}'.\n\n"
        f"HASIL SCREENER DATA LIVE:\n"
        f"{json.dumps(screener_res, ensure_ascii=False)}\n\n"
        f"Sila formatkan output sebagai jadual Shortlist Screener AURA-Trade berserta justifikasi Top-Down."
    )

    try:
        response_text = await call_supervisor_chat_model(prompt)
        clean = _clean_response(response_text)
        await _send_telegram_msg(update, clean, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in screener_command: {e}")
        await _send_telegram_msg(update, f"⚠️ Gagal menjana screener AURA-Trade.", parse_mode="Markdown")
