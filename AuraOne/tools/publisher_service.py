import os
import re
import json
import time
import logging
import httpx
from typing import Optional

from config import (
    AIRTABLE_API_KEY,
    AIRTABLE_BASE_ID,
    AIRTABLE_TABLE_NAME,
    DEFAULT_BRAND,
    GDRIVE_IMAGE_FOLDER_ID,
    GDRIVE_DUMP_FOLDER_ID
)

logger = logging.getLogger("aura.tools.publisher_service")

GDRIVE_API = "https://www.googleapis.com/drive/v3"
GDRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"

def _get_gdrive_access_token() -> Optional[str]:
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json_str:
        return None
    try:
        sa_info = json.loads(sa_json_str)
        from google.oauth2 import service_account
        import google.auth.transport.requests
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception as e:
        logger.error(f"Failed to get Google Drive access token: {e}")
        return None

def upload_file_to_drive(file_bytes: bytes, filename: str, mime_type: str = "image/jpeg", folder_id: str = None) -> dict:
    """Upload file bytes directly to Google Drive folder and set public read permission."""
    if not folder_id:
        folder_id = GDRIVE_DUMP_FOLDER_ID if mime_type.startswith("text/") else GDRIVE_IMAGE_FOLDER_ID

    token = _get_gdrive_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive credentials not set"}
    try:
        headers = {"Authorization": f"Bearer {token}"}
        metadata = json.dumps({
            "name": filename,
            "parents": [folder_id],
        })
        boundary = b"aura_boundary"
        body = (
            b"--" + boundary + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n" +
            metadata.encode() + b"\r\n"
            b"--" + boundary + b"\r\n"
            b"Content-Type: " + mime_type.encode() + b"\r\n\r\n" +
            file_bytes + b"\r\n"
            b"--" + boundary + b"--"
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GDRIVE_UPLOAD_API}/files",
                params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                content=body,
                headers={
                    **headers,
                    "Content-Type": f"multipart/related; boundary=aura_boundary"
                }
            )
            resp.raise_for_status()
            data = resp.json()
            file_id = data.get("id")

            perm_url = f"{GDRIVE_API}/files/{file_id}/permissions"
            perm_payload = {"role": "reader", "type": "anyone"}
            client.post(perm_url, json=perm_payload, headers=headers)

        return {
            "status": "success",
            "file_id": file_id,
            "name": data.get("name"),
            "link": f"https://docs.google.com/uc?export=download&id={file_id}"
        }
    except Exception as e:
        logger.error(f"upload_file_to_drive error: {e}")
        return {"status": "error", "error": str(e)}

def upload_to_drive(content_bytes: bytes, filename: str, mime_type: str = "image/jpeg", folder_id: str = None) -> dict:
    """Wrapper / alias for upload_file_to_drive for backwards compatibility."""
    return upload_file_to_drive(content_bytes, filename, mime_type=mime_type, folder_id=folder_id)

def delete_file_from_drive(file_id: str) -> dict:
    """Delete a file from Google Drive given its file_id."""
    token = _get_gdrive_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive credentials not set"}
    try:
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(timeout=15) as client:
            resp = client.delete(f"{GDRIVE_API}/files/{file_id}", headers=headers)
            resp.raise_for_status()
        return {"status": "success", "file_id": file_id}
    except Exception as e:
        logger.error(f"delete_file_from_drive error: {e}")
        return {"status": "error", "error": str(e)}

def update_file_on_drive(file_id: str, new_bytes: bytes, mime_type: str = "application/octet-stream") -> dict:
    """Update existing file content on Google Drive."""
    token = _get_gdrive_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive credentials not set"}
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": mime_type
        }
        with httpx.Client(timeout=30) as client:
            resp = client.patch(
                f"{GDRIVE_UPLOAD_API}/files/{file_id}",
                params={"uploadType": "media"},
                content=new_bytes,
                headers=headers
            )
            resp.raise_for_status()
        return {"status": "success", "file_id": file_id}
    except Exception as e:
        logger.error(f"update_file_on_drive error: {e}")
        return {"status": "error", "error": str(e)}

def upload_article_dump_to_drive(
    title: str,
    master_article: str,
    hashtags: str,
    source_url: str,
    response_text: str,
    counter: int,
    folder_id: str = None
) -> dict:
    """Formulate full article dump (.txt) and upload it directly to Google Drive."""
    try:
        fb_match = re.search(r"\[DRAFT_FB:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        threads_match = re.search(r"\[DRAFT_THREADS:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        twitter_match = re.search(r"\[DRAFT_TWITTER:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)
        lemon8_match = re.search(r"\[DRAFT_LEMON8:\s*(.+?)\]", response_text, re.IGNORECASE | re.DOTALL)

        fb_draft = fb_match.group(1).strip() if fb_match else "N/A"
        threads_draft = threads_match.group(1).strip() if threads_match else "N/A"
        twitter_draft = twitter_match.group(1).strip() if twitter_match else "N/A"
        lemon8_draft = lemon8_match.group(1).strip() if lemon8_match else "N/A"

        dump_content = (
            f"SOURCE URL: {source_url}\n"
            f"TITLE: {title}\n"
            f"HASHTAGS: {hashtags}\n\n"
            f"=========================================\n"
            f"MASTER ARTICLE:\n{master_article}\n\n"
            f"=========================================\n"
            f"FACEBOOK DRAFT:\n{fb_draft}\n\n"
            f"=========================================\n"
            f"THREADS DRAFT:\n{threads_draft}\n\n"
            f"=========================================\n"
            f"X / TWITTER DRAFT:\n{twitter_draft}\n\n"
            f"=========================================\n"
            f"LEMON8 DRAFT:\n{lemon8_draft}\n"
        )

        filename = f"web-{counter}.txt"
        return upload_file_to_drive(dump_content.encode("utf-8"), filename, mime_type="text/plain", folder_id=folder_id)
    except Exception as e:
        logger.error(f"Error in upload_article_dump_to_drive: {e}")
        return {"status": "error", "error": str(e)}

_upload_article_dump_to_github = upload_article_dump_to_drive

def save_draft_to_airtable(
    title: str,
    caption: str,
    platform: str = "facebook",
    style: str = "santai_bercerita",
    source_url: str = "",
    image_url: str = "",
    brand: str = "",
    created_by: str = "AURA (SDK)",
    status: str = "Draft",
    hashtags: str = "",
    scheduled_time: str = "",
    content_type: str = "Article",
    original_price: str = "",
    seller_location: str = ""
) -> dict:
    api_key = AIRTABLE_API_KEY
    base_id = AIRTABLE_BASE_ID
    table_name = AIRTABLE_TABLE_NAME
    if not api_key or not base_id:
        return {"status": "error", "error": "Airtable credentials missing"}
    if not brand:
        brand = DEFAULT_BRAND
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    plat_name = "X" if platform.lower() in ["twitter", "x"] else platform.title()

    clean_caption = caption
    if clean_caption:
        clean_caption = clean_caption.replace("**", "").replace("*", "")

    fields = {
        "Title": title,
        "Caption": clean_caption,
        "Platform": [plat_name],
        "Post Status": status,
        "Brand": brand,
        "Content Type": content_type,
        "Created By": created_by,
        "Hashtags": hashtags,
        "Scheduled Date": scheduled_time,
        "Image file": [{"url": image_url}] if image_url else None,
        "Gambar": [{"url": image_url}] if image_url else None,
        "Original Price": original_price if original_price else None,
        "Seller Location": seller_location if seller_location else None,
        "Source URL": source_url if source_url else None,
        "Product Link": source_url if source_url else None
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    try:
        with httpx.Client(timeout=15) as client:
            while True:
                resp = client.post(url, headers=headers, json={"fields": fields, "typecast": True})
                if resp.status_code == 200:
                    break
                elif resp.status_code == 422 and "UNKNOWN_FIELD_NAME" in resp.text:
                    err_msg = resp.text
                    removed = False
                    for k in list(fields.keys()):
                        if k in err_msg:
                            logger.info(f"Field '{k}' not found in Airtable schema, removing it.")
                            fields.pop(k, None)
                            removed = True
                    if not removed:
                        resp.raise_for_status()
                else:
                    resp.raise_for_status()

            data = resp.json()
            return {"status": "success", "record_id": data.get("id")}

    except Exception as e:
        logger.error(f"Airtable error: {e}")
        return {"status": "error", "error": str(e)}

def save_thread_posts_to_airtable(parent_record_id: str, posts: list[str], platform: str) -> dict:
    """Save individual thread posts linked to the main Content Station record in Airtable."""
    api_key = AIRTABLE_API_KEY
    base_id = AIRTABLE_BASE_ID
    table_name = "Thread Posts"

    if not api_key or not base_id:
        return {"status": "error", "error": "Airtable credentials missing"}

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    records = []
    for idx, post_text in enumerate(posts, start=1):
        records.append({
            "fields": {
                "Content Station": [parent_record_id],
                "Post Text": post_text,
                "Sequence": idx,
                "Platform": "X" if platform.lower() in ["x", "twitter"] else platform.title()
            }
        })

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json={"records": records, "typecast": True})
            resp.raise_for_status()
            return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving thread posts to Airtable: {e}")
        return {"status": "error", "error": str(e)}

def _get_next_image_filename(image_url: str, counter: int) -> tuple[str, str]:
    """Return a standardized filename (e.g. web-1.jpg) and its mime type for given counter."""
    ext = "jpg"
    mime = "image/jpeg"

    url_lower = image_url.lower()
    if ".png" in url_lower:
        ext = "png"
        mime = "image/png"
    elif ".webp" in url_lower:
        ext = "webp"
        mime = "image/webp"

    filename = f"web-{counter}.{ext}"
    return filename, mime

async def _prepare_drive_image_for_airtable(image_url: str, telegram_file_id: str, counter: int, context) -> str:
    """Download image (via Telegram cache if available, or direct fallback) and upload to Google Drive to return a direct public URL for Airtable."""
    if not image_url and not telegram_file_id:
        return ""
    try:
        img_bytes = None

        if telegram_file_id and context:
            try:
                logger.info(f"Downloading image from Telegram cache using file_id: {telegram_file_id}")
                telegram_file = await context.bot.get_file(telegram_file_id)
                file_bytearray = await telegram_file.download_as_bytearray()
                img_bytes = bytes(file_bytearray)
                logger.info(f"Downloaded {len(img_bytes)} bytes from Telegram cache.")
            except Exception as tg_err:
                logger.warning(f"Telegram file download failed, falling back to HTTP: {tg_err}")

        if not img_bytes and image_url:
            logger.info(f"Downloading image via direct HTTP request: {image_url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            with httpx.Client(timeout=30) as client:
                resp = client.get(image_url, headers=headers)
                resp.raise_for_status()
                img_bytes = resp.content

        if not img_bytes:
            return image_url

        filename, mime = _get_next_image_filename(image_url, counter)
        logger.info(f"Standardized filename for Google Drive: {filename}")

        drive_res = upload_file_to_drive(img_bytes, filename, mime_type=mime)
        if drive_res.get("status") == "success" and drive_res.get("link"):
            return drive_res.get("link")
        else:
            logger.warning(f"Drive image upload returned non-success: {drive_res.get('error')}")
    except Exception as e:
        logger.error(f"Failed to process image Drive upload: {e}")
    return image_url
