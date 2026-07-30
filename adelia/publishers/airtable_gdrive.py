"""
ADELIA Publisher — Airtable Content Station & Google Drive Storage.

Ported from AuraOne/tools/publisher_service.py.
Pure I/O layer — NO Telegram dependencies, NO file_id handling.
Accepts only resolved image URLs or raw bytes.

Env vars consumed:
    AIRTABLE_API_KEY             – Airtable personal access token
    AIRTABLE_BASE_ID             – Base ID
    AIRTABLE_TABLE_NAME          – Main table (default: Content Station)
    DEFAULT_BRAND                – Default brand (default: Sakluma)
    GDRIVE_IMAGE_FOLDER_ID       – Image folder ID on Drive
    GDRIVE_DUMP_FOLDER_ID        – Article dump (.txt) folder ID on Drive
    GOOGLE_SERVICE_ACCOUNT_JSON  – Google service account JSON string
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any

import httpx

from adelia.inference.exceptions import HFDisabled

if TYPE_CHECKING:
    from adelia.inference.hf_client import HFClient

logger = logging.getLogger("adelia.publishers.airtable_gdrive")

# ── API Endpoints ──────────────────────────────────────────────────────

GDRIVE_API = "https://www.googleapis.com/drive/v3"
GDRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"

# ── Configuration (env-injected) ───────────────────────────────────────

_AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
_AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
_AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Content Station")
_DEFAULT_BRAND = os.getenv("DEFAULT_BRAND", "Sakluma")
_GDRIVE_IMAGE_FOLDER_ID = os.getenv(
    "GDRIVE_IMAGE_FOLDER_ID", "1ntdhPOq3Z7oNXLDqQgVyVQS6tIMoArc3"
)
_GDRIVE_DUMP_FOLDER_ID = os.getenv(
    "GDRIVE_DUMP_FOLDER_ID", "1Ybx7mBAKksI2VcagHAqOuKkf8pjbvYwa"
)


# ── Google Drive Helpers ───────────────────────────────────────────────


def _get_gdrive_access_token() -> str | None:
    """Obtain Google Drive access token using service account credentials."""
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json_str:
        return None
    try:
        sa_info = json.loads(sa_json_str)
        import google.auth.transport.requests
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        return credentials.token
    except Exception as e:
        logger.error("Failed to get Google Drive access token: %s", e)
        return None


def upload_file_to_drive(
    file_bytes: bytes,
    filename: str,
    mime_type: str = "image/jpeg",
    folder_id: str | None = None,
) -> dict[str, Any]:
    """Upload file bytes directly to Google Drive folder and set public read permission."""
    if not folder_id:
        folder_id = (
            _GDRIVE_DUMP_FOLDER_ID
            if mime_type.startswith("text/")
            else _GDRIVE_IMAGE_FOLDER_ID
        )

    token = _get_gdrive_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive credentials not set"}

    try:
        headers = {"Authorization": f"Bearer {token}"}
        metadata = json.dumps(
            {
                "name": filename,
                "parents": [folder_id],
            }
        )
        boundary = b"adelia_boundary"
        body = (
            b"--" + boundary + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata.encode()
            + b"\r\n"
            b"--" + boundary + b"\r\n"
            b"Content-Type: " + mime_type.encode() + b"\r\n\r\n"
            + file_bytes
            + b"\r\n"
            b"--" + boundary + b"--"
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GDRIVE_UPLOAD_API}/files",
                params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                content=body,
                headers={
                    **headers,
                    "Content-Type": "multipart/related; boundary=adelia_boundary",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            file_id = data.get("id")

            # Set public read permission
            perm_url = f"{GDRIVE_API}/files/{file_id}/permissions"
            perm_payload = {"role": "reader", "type": "anyone"}
            client.post(perm_url, json=perm_payload, headers=headers)

        dl_link = f"https://docs.google.com/uc?export=download&id={file_id}"
        return {
            "status": "success",
            "file_id": file_id,
            "name": data.get("name"),
            "link": dl_link,
        }
    except Exception as e:
        logger.error("upload_file_to_drive error: %s", e)
        return {"status": "error", "error": str(e)}


def upload_article_dump_to_drive(
    title: str,
    master_article: str,
    hashtags: str,
    source_url: str,
    response_text: str,
    counter: int,
    folder_id: str | None = None,
) -> dict[str, Any]:
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
        return upload_file_to_drive(
            dump_content.encode("utf-8"),
            filename,
            mime_type="text/plain",
            folder_id=folder_id,
        )
    except Exception as e:
        logger.error("Error in upload_article_dump_to_drive: %s", e)
        return {"status": "error", "error": str(e)}


# ── Image Fallback Hook (FLUX image generation) ─────────────────────────


def ensure_image_url(
    image_url: str | None,
    prompt: str,
    hf_client: HFClient | None = None,
    counter: int = 1,
) -> str | None:
    """Ensure a valid image URL exists.

    If image_url is missing or invalid:
    1. Attempts to generate a synthetic image via HFClient (FLUX.1-schnell).
    2. Uploads generated PNG bytes to Google Drive.
    3. Returns the public Google Drive URL.

    If HF is disabled or fails, returns original image_url (or None).
    """
    if image_url and image_url.startswith("http"):
        return image_url

    if not os.getenv("USE_HF_INFERENCE", "false").lower() == "true":
        logger.info("USE_HF_INFERENCE is off — skipping synthetic image fallback.")
        return image_url

    if hf_client is None:
        from adelia.inference.hf_client import HFClient

        hf_client = HFClient()

    try:
        logger.info("Generating synthetic image fallback via FLUX: %.60s…", prompt)
        img_bytes = hf_client.generate_image(prompt)
        filename = f"web-{counter}-flux.png"
        res = upload_file_to_drive(img_bytes, filename, mime_type="image/png")
        if res.get("status") == "success":
            drive_link = res.get("link")
            logger.info("Uploaded synthetic image to Drive: %s", drive_link)
            return drive_link
    except (HFDisabled, Exception) as err:
        logger.warning("Image fallback generation failed: %s", err)

    return image_url


# ── Airtable Publisher ──────────────────────────────────────────────────


def save_draft_to_airtable(
    title: str,
    caption: str,
    platform: str = "facebook",
    style: str = "santai_bercerita",
    source_url: str = "",
    image_url: str = "",
    brand: str = "",
    created_by: str = "ADELIA (SDK)",
    status: str = "Draft",
    hashtags: str = "",
    scheduled_time: str = "",
    content_type: str = "Article",
    original_price: str = "",
    seller_location: str = "",
    hf_client: HFClient | None = None,
) -> dict[str, Any]:
    """Publish a draft to Airtable Content Station with self-healing 422 retry.

    Byte-for-byte identical Content Station schema mapping to AuraOne.
    """
    api_key = os.getenv("AIRTABLE_API_KEY", _AIRTABLE_API_KEY)
    base_id = os.getenv("AIRTABLE_BASE_ID", _AIRTABLE_BASE_ID)
    table_name = os.getenv("AIRTABLE_TABLE_NAME", _AIRTABLE_TABLE_NAME)

    if not api_key or not base_id:
        return {"status": "error", "error": "Airtable credentials missing"}

    if not brand:
        brand = os.getenv("DEFAULT_BRAND", _DEFAULT_BRAND)

    # Ensure image_url exists via FLUX fallback if missing
    resolved_image_url = ensure_image_url(
        image_url=image_url,
        prompt=f"Editorial banner image for: {title}",
        hf_client=hf_client,
    )

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    plat_name = "X" if platform.lower() in ["twitter", "x"] else platform.title()

    clean_caption = caption
    if clean_caption:
        clean_caption = clean_caption.replace("**", "").replace("*", "")

    # Byte-for-byte schema mapping matching AuraOne publisher_service.py
    fields: dict[str, Any] = {
        "Title": title,
        "Caption": clean_caption,
        "Platform": [plat_name],
        "Post Status": status,
        "Brand": brand,
        "Content Type": content_type,
        "Created By": created_by,
        "Hashtags": hashtags,
        "Image file": [{"url": resolved_image_url}] if resolved_image_url else None,
        "Original Price": original_price if original_price else None,
        "Seller Location": seller_location if seller_location else None,
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    try:
        with httpx.Client(timeout=15) as client:
            while True:
                resp = client.post(
                    url,
                    headers=headers,
                    json={"fields": fields, "typecast": True},
                )
                if resp.status_code == 200:
                    break
                elif resp.status_code == 422 and "UNKNOWN_FIELD_NAME" in resp.text:
                    # Self-healing 422 retry: remove invalid fields and retry
                    err_msg = resp.text
                    removed = False
                    for k in list(fields.keys()):
                        if k in err_msg:
                            logger.info("Field '%s' not in Airtable schema, removing for retry.", k)
                            fields.pop(k, None)
                            removed = True
                    if not removed:
                        resp.raise_for_status()
                else:
                    resp.raise_for_status()

            data = resp.json()
            return {"status": "success", "record_id": data.get("id")}

    except Exception as e:
        logger.error("Airtable save error: %s", e)
        return {"status": "error", "error": str(e)}


def save_thread_posts_to_airtable(
    parent_record_id: str,
    posts: list[str],
    platform: str,
) -> dict[str, Any]:
    """Save individual thread posts linked to the parent Content Station record in Airtable."""
    api_key = os.getenv("AIRTABLE_API_KEY", _AIRTABLE_API_KEY)
    base_id = os.getenv("AIRTABLE_BASE_ID", _AIRTABLE_BASE_ID)
    table_name = "Thread Posts"

    if not api_key or not base_id:
        return {"status": "error", "error": "Airtable credentials missing"}

    url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    records = []
    for idx, post_text in enumerate(posts, start=1):
        records.append(
            {
                "fields": {
                    "Content Station": [parent_record_id],
                    "Post Text": post_text,
                    "Sequence": idx,
                    "Platform": "X" if platform.lower() in ["x", "twitter"] else platform.title(),
                }
            }
        )

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                url,
                headers=headers,
                json={"records": records, "typecast": True},
            )
            resp.raise_for_status()
            return {"status": "success"}
    except Exception as e:
        logger.error("Error saving thread posts to Airtable: %s", e)
        return {"status": "error", "error": str(e)}
