# Airtable Content Station Blueprint

Below is the verified code from AURA v5 for saving and listing drafts in the Airtable "Content Station" database table.

```python
import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("aura.tools.airtable")

AIRTABLE_BASE_URL = "https://api.airtable.com/v0"

def save_draft_to_airtable(
    title: str,
    caption: str,
    platform: str,
    style: str,
    source_url: str = "",
    image_url: str = "",
    brand: str = "",
    created_by: str = "AURA (SDK)",
    status: str = "Draft"
) -> dict:
    """Save a content draft to Airtable Content Station.
    """
    api_key = os.environ.get("AIRTABLE_API_KEY", "")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME", "Content Station")

    if not api_key or not base_id:
        return {
            "status": "error",
            "error": "AIRTABLE_API_KEY atau AIRTABLE_BASE_ID tidak ditemui dalam .env"
        }

    if not brand:
        brand = os.environ.get("DEFAULT_BRAND", "Sakluma")

    url = f"{AIRTABLE_BASE_URL}/{base_id}/{table_name}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    fields = {
        "Title": title,
        "Caption": caption,
        "Platform": [platform.title()],
        "Status": status,
        "Brand": brand,
        "Post Link": source_url,
        "Image URL": image_url,
        "Content Type": "Article",
        "Created By": created_by,
    }
    # Remove empty fields
    fields = {k: v for k, v in fields.items() if v}

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, json={"fields": fields})
            resp.raise_for_status()
            data = resp.json()
            record_id = data.get("id", "")
            return {
                "status": "success",
                "record_id": record_id,
                "message": f"Draft '{title}' saved to Airtable — {platform.title()} | {style}"
            }
    except httpx.HTTPStatusError as e:
        logger.error(f"Airtable HTTP error: {e.response.status_code} — {e.response.text}")
        return {
            "status": "error",
            "error": f"Airtable API error {e.response.status_code}: {e.response.text[:200]}"
        }
    except Exception as e:
        logger.error(f"Airtable error: {e}")
        return {"status": "error", "error": str(e)}

def list_airtable_drafts(limit: int = 10) -> dict:
    """List recent draft records from Airtable Content Station.
    """
    api_key = os.environ.get("AIRTABLE_API_KEY", "")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "")
    table_name = os.environ.get("AIRTABLE_TABLE_NAME", "Content Station")

    if not api_key or not base_id:
        return {
            "status": "error",
            "error": "Airtable credentials missing."
        }

    url = f"{AIRTABLE_BASE_URL}/{base_id}/{table_name}"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "pageSize": min(limit, 100),
        "sort[0][field]": "Created By",
        "sort[0][direction]": "desc",
        "filterByFormula": "({Status} = 'Draft')"
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("records", [])
            result = []
            for r in records:
                f = r.get("fields", {})
                result.append({
                    "id": r.get("id"),
                    "title": f.get("Title", ""),
                    "platform": f.get("Platform", ""),
                    "style": f.get("Style", ""),
                    "status": f.get("Status", ""),
                    "brand": f.get("Brand", ""),
                })
            return {"status": "success", "drafts": result, "count": len(result)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```
