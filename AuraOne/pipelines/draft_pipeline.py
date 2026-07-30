"""
Draft Pipeline — Platform draft generation, cleaning, and confirm & push to Airtable.
Extracted from ui/telegram_bot.py (_clean_platform_draft_output, _call_draft_generator_model,
_generate_all_platform_drafts, confirm_command, confirm_platform_push).
"""
import re
import json
import logging
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import storage.draft_repository as draft_repo
from tools.publisher_service import save_draft_to_airtable, _prepare_drive_image_for_airtable
from ui.formatters import _send_telegram_msg
from pipelines.llm_caller import call_llm
from config import USE_ADELIA_SERVICE
import tools.adelia_client as adelia_client

logger = logging.getLogger("aura.pipelines.draft_pipeline")


def clean_platform_draft_output(text: str) -> str:
    """Post-process and clean platform draft text output to guarantee 100% pure caption content."""
    if not text:
        return ""

    from prompts import sanitize_hashtags

    # 1. Remove visual/GIF recommendations
    cleaned = re.sub(r"\[?(?:Gambar|Media|Visual|Cadangan GIF|GIF):\s*.*?\]?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\((?:Gambar|Media|Visual|Cadangan GIF|GIF):\s*.*?\)", "", cleaned, flags=re.IGNORECASE)

    # 2. Remove structural header labels & conversational intro lines line-by-line
    lines = []
    for line in cleaned.split("\n"):
        line_strip = line.strip()
        # Skip intro conversational fluff lines
        if re.match(r"^(?:Baiklah|Tentu|Berikut|Ini|Semoga|Cadangan|Kapsyen)\b.*", line_strip, re.IGNORECASE) and len(line_strip) < 70 and ("draf" in line_strip.lower() or "hantaran" in line_strip.lower() or "berikut" in line_strip.lower() or "sakluma" in line_strip.lower()):
            continue
        # Strip structural prefixes
        line_clean = re.sub(r"^(?:FACEBOOK POST|FB POST|THREADS POST|X POST|TWITTER POST|LEMON8 POST|KAPSYEN|TAJUK|TITLE|POST):\s*", "", line, flags=re.IGNORECASE)
        lines.append(line_clean)

    cleaned_text = "\n".join(lines).strip()
    return sanitize_hashtags(cleaned_text)


async def call_draft_generator_model(plat: str, draft: dict, fb_style: str = "", thread_length: int = 0, fb_len: str = "panjang", fb_show_title: bool = False, tx_style: str = "genz") -> str:
    """Generate a platform-specific draft from master article using prompt registry and LLM."""
    from prompts import build_prompt, enforce_fb_length_limits

    plat_lower = plat.lower()
    seed_val = draft.get("counter_val", 0)
    try:
        if plat_lower in ["facebook", "fb"] or (fb_style and plat_lower not in ["threads", "x", "twitter"]):
            style_key = fb_style or "viral_santai"
            sys_p, usr_p = build_prompt(
                platform="facebook",
                style=style_key,
                length=fb_len,
                show_title=fb_show_title,
                raw=draft.get("master_article", ""),
                seed=seed_val
            )
            prompt = f"{sys_p}\n\n{usr_p}"
        elif plat_lower == "threads":
            count_key = str(thread_length) if thread_length in [1, 3, 5, 8] else "5"
            style_key = tx_style or "genz"
            sys_p, usr_p = build_prompt(
                platform="threads",
                style=style_key,
                count=count_key,
                raw=draft.get("master_article", ""),
                seed=seed_val
            )
            prompt = f"{sys_p}\n\n{usr_p}"
        elif plat_lower in ["x", "twitter"]:
            count_key = str(thread_length) if thread_length in [1, 3, 5, 8] else "1"
            style_key = tx_style or "genz"
            sys_p, usr_p = build_prompt(
                platform="x",
                style=style_key,
                count=count_key,
                raw=draft.get("master_article", ""),
                seed=seed_val
            )
            prompt = f"{sys_p}\n\n{usr_p}"
        else:
            sys_p, usr_p = build_prompt(
                platform=plat_lower,
                style=fb_style or "estetik",
                raw=draft.get("master_article", ""),
                seed=seed_val
            )
            prompt = f"{sys_p}\n\n{usr_p}"
    except KeyError as k_err:
        logger.error(f"Prompt registry KeyError for platform {plat}: {k_err}")
        raise k_err

    text = await call_llm(prompt, timeout=10.0)
    if text:
        cleaned = clean_platform_draft_output(text)
        if plat_lower in ["facebook", "fb"]:
            cleaned = enforce_fb_length_limits(cleaned, fb_len=fb_len, show_title=fb_show_title)
        return cleaned

    # Fallback to master article text if all model calls fail
    style_label = f" ({fb_style})" if fb_style else ""
    fallback_txt = clean_platform_draft_output(f"📰 *{draft['title']}*{style_label}\n\n{draft['master_article'][:1200]}\n\n{draft.get('hashtags', '')}")
    if plat_lower in ["facebook", "fb"]:
        fallback_txt = enforce_fb_length_limits(fallback_txt, fb_len=fb_len, show_title=fb_show_title)
    return fallback_txt


async def generate_all_platform_drafts(user_id: int, chat_id: int, selected_platforms: list, options: dict, draft: dict, context, message):
    """Generate drafts for all selected platforms and present review with confirm buttons."""
    generated_drafts = {}
    for plat in selected_platforms:
        fb_style = options.get("facebook", "viral_santai")
        fb_len = options.get("fb_len", "panjang")
        fb_show_title = options.get("fb_show_title", False)
        tx_style = options.get("tx_style", "genz")
        thread_length = options.get("thread_len", 5) if plat in ["x", "threads"] else 0
        try:
            draft_text = await asyncio.wait_for(call_draft_generator_model(plat, draft, fb_style, thread_length, fb_len, fb_show_title, tx_style), timeout=15.0)
        except Exception as err:
            logger.error(f"Draft generation timeout/error for {plat}: {err}")
            style_label = f" ({fb_style})" if fb_style else ""
            draft_text = f"📰 *{draft['title']}*{style_label}\n\n{draft['master_article'][:1200]}\n\n{draft.get('hashtags', '')}"

        if not draft_text:
            draft_text = f"📰 *{draft['title']}*\n\n{draft['master_article'][:1200]}\n\n{draft.get('hashtags', '')}"

        draft_text = clean_platform_draft_output(draft_text)
        generated_drafts[plat] = draft_text

    draft_repo.update_platform_draft(user_id, ",".join(selected_platforms), json.dumps(generated_drafts), state="")

    review_text = "✨ *DRAF MEDIA SOSIAL YANG DIJANA* ✨\n\n"
    keyboard = []
    for plat, text in generated_drafts.items():
        review_text += f"📱 *{plat.upper()}*:\n{text}\n\n"
        keyboard.append([InlineKeyboardButton(f"Confirm & Push {plat.upper()} ✅", callback_data=f"confirm_platform:{plat}")])

    review_text += "Sila klik butang di bawah untuk muat naik ke Google Drive & tolak ke Airtable."
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(review_text, parse_mode="Markdown", reply_markup=reply_markup)


async def confirm_platform_push(user_id: int, draft: dict, plat_to_confirm: str, context, query_message):
    """Execute confirm & push for a specific platform draft to Airtable."""
    try:
        platform_drafts = json.loads(draft.get("platform_draft") or "{}")
    except Exception:
        platform_drafts = {}

    specific_draft = platform_drafts.get(plat_to_confirm, "")
    if not specific_draft:
        specific_draft = draft.get("master_article", "")

    telegram_direct_cdn_url = await _prepare_drive_image_for_airtable(
        draft["image_url"], draft.get("telegram_file_id", ""), draft.get("counter_val", 0), context
    )

    target_airtable_img = telegram_direct_cdn_url or draft.get("image_url", "")
    if target_airtable_img and target_airtable_img.startswith("http://"):
        target_airtable_img = "https://" + target_airtable_img[7:]

    # Microservice routing vs In-process fallback
    if USE_ADELIA_SERVICE:
        logger.info("[DraftPipeline] Routing confirm & push to ADELIA microservice...")
        draft_payload = {
            "platform": plat_to_confirm,
            "caption": specific_draft,
            "image_url": target_airtable_img,
        }
        extra_fields = {
            "title": draft["title"],
            "source_url": draft.get("source_url", ""),
            "hashtags": draft.get("hashtags", ""),
            "status": "Draft",
        }
        try:
            pub_res = await adelia_client.publish(draft=draft_payload, content_type="Post", extra_fields=extra_fields)
            res = {"status": "success" if pub_res.get("status") in ["published", "queued"] else "error", "error": pub_res.get("error")}
        except Exception as exc:
            logger.error(f"[DraftPipeline] ADELIA publish failed, falling back to in-process path: {exc}")
            res = save_draft_to_airtable(
                title=draft["title"],
                caption=specific_draft,
                platform=plat_to_confirm,
                source_url=draft["source_url"],
                image_url=target_airtable_img,
                status="Draft",
                hashtags=draft["hashtags"]
            )
    else:
        res = save_draft_to_airtable(
            title=draft["title"],
            caption=specific_draft,
            platform=plat_to_confirm,
            source_url=draft["source_url"],
            image_url=target_airtable_img,
            status="Draft",
            hashtags=draft["hashtags"]
        )

    if res["status"] == "success":
        draft_repo.clear_draft(user_id)
        await query_message.reply_text(
            f"✅ *Draf Hantaran {plat_to_confirm.upper()} Berjaya Disahkan!*\n\n"
            f"• *Tajuk*: {draft['title']}\n"
            f"• *Platform*: {plat_to_confirm.upper()}\n"
            f"• *Telegram Direct CDN*: `{telegram_direct_cdn_url}` 📸\n"
            f"• *Airtable Record*: Berjaya disimpan [Content Station] 🎉",
            parse_mode="Markdown"
        )
    else:
        await query_message.reply_text(f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")


async def handle_confirm_command(update, context):
    """Handle /confirm text command — push active draft to Airtable."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    draft = draft_repo.get_draft(user_id)
    if not draft:
        await update.message.reply_text("⚠️ Tiada draf aktif dijumpai.")
        return

    title = draft["title"]
    hashtags = draft["hashtags"]
    image_url = draft["image_url"]
    source_url = draft["source_url"]
    selected_platform = draft["selected_platform"]
    platform_draft = draft["platform_draft"]

    if not selected_platform or not platform_draft:
        await update.message.reply_text("⚠️ Sila pilih platform draf terlebih dahulu.")
        return

    telegram_file_id = draft.get("telegram_file_id", "")
    counter = draft.get("counter_val", 0)
    final_image_url = await _prepare_drive_image_for_airtable(image_url, telegram_file_id, counter, context)

    specific_draft = platform_draft
    try:
        draft_dict = json.loads(platform_draft)
        if isinstance(draft_dict, dict):
            specific_draft = draft_dict.get(selected_platform, platform_draft)
    except Exception:
        pass

    # Microservice routing vs In-process fallback
    if USE_ADELIA_SERVICE:
        logger.info("[DraftPipeline] Routing /confirm command to ADELIA microservice...")
        draft_payload = {
            "platform": selected_platform,
            "caption": specific_draft,
            "image_url": final_image_url,
        }
        extra_fields = {
            "title": title,
            "source_url": source_url,
            "hashtags": hashtags,
            "status": "Draft",
        }
        try:
            pub_res = await adelia_client.publish(draft=draft_payload, content_type="Post", extra_fields=extra_fields)
            res = {"status": "success" if pub_res.get("status") in ["published", "queued"] else "error", "error": pub_res.get("error")}
        except Exception as exc:
            logger.error(f"[DraftPipeline] ADELIA publish failed, falling back to in-process path: {exc}")
            res = save_draft_to_airtable(
                title=title,
                caption=specific_draft,
                platform=selected_platform,
                source_url=source_url,
                image_url=final_image_url,
                status="Draft",
                hashtags=hashtags
            )
    else:
        res = save_draft_to_airtable(
            title=title,
            caption=specific_draft,
            platform=selected_platform,
            source_url=source_url,
            image_url=final_image_url,
            status="Draft",
            hashtags=hashtags
        )

    if res["status"] == "success":
        draft_repo.clear_draft(user_id)
        reply_msg = (
            f"✅ *Draf Hantaran {selected_platform.upper()} Berjaya Disahkan!*\n\n"
            f"• *Tajuk*: {title}\n"
            f"• *Platform*: {selected_platform.upper()}\n"
            f"• *Airtable Record*: Berjaya disimpan [Content Station]\n\n"
            f"Sedia untuk fasa posting!"
        )
        await _send_telegram_msg(update, reply_msg, parse_mode="Markdown")
    else:
        await _send_telegram_msg(update, f"⚠️ Gagal menyimpan ke Airtable: {res.get('error')}")
