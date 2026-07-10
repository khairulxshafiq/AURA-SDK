# Google Drive Integration Blueprint

Below is the verified code from AURA v5 for listing, reading, searching, and uploading text or files to Google Drive using a Google Service Account.

```python
import os
import io
import json
import logging
import base64
import httpx
from typing import Optional

logger = logging.getLogger("aura.gdrive")

DEFAULT_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "1Apv70Qwp2iF0405kn4mmzaB1UmXkWwqM")

GDRIVE_API = "https://www.googleapis.com/drive/v3"
GDRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def _get_access_token() -> Optional[str]:
    """Get short-lived access token using Service Account JSON."""
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json_str:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON not set in env")
        return None

    try:
        sa_info = json.loads(sa_json_str)
    except json.JSONDecodeError:
        logger.error("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON")
        return None

    try:
        import time
        import json as _json

        # Build JWT for Service Account auth using google-auth if available
        try:
            from google.oauth2 import service_account
            import google.auth.transport.requests

            credentials = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            return credentials.token

        except ImportError:
            # Manual JWT fallback (requires cryptography & PyJWT)
            import jwt

            now = int(time.time())
            payload = {
                "iss": sa_info["client_email"],
                "scope": "https://www.googleapis.com/auth/drive",
                "aud": TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            }

            private_key = sa_info["private_key"]
            token = jwt.encode(payload, private_key, algorithm="RS256")

            with httpx.Client(timeout=10) as client:
                resp = client.post(TOKEN_URL, data={
                    "grant_type": "urn:ietf:params:oauth2:grant-type:jwt-bearer",
                    "assertion": token,
                })
                resp.raise_for_status()
                return resp.json().get("access_token")

    except Exception as e:
        logger.error(f"Failed to get access token: {e}")
        return None

def list_drive_files(folder_id: str = None, max_files: int = 20) -> dict:
    """List files in the AURA Google Drive folder.
    """
    folder_id = folder_id or DEFAULT_FOLDER_ID
    token = _get_access_token()

    if not token:
        return {
            "status": "error",
            "error": "Google Drive tidak dikonfigurasi. GOOGLE_SERVICE_ACCOUNT_JSON diperlukan dalam .env"
        }

    try:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
            "pageSize": max_files,
            "orderBy": "modifiedTime desc",
        }

        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{GDRIVE_API}/files", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        files = data.get("files", [])
        file_list = []
        for f in files:
            size_kb = int(f.get("size", 0)) // 1024 if f.get("size") else None
            file_list.append({
                "name": f["name"],
                "id": f["id"],
                "type": f.get("mimeType", "").split(".")[-1],
                "modified": f.get("modifiedTime", "")[:10],
                "size_kb": size_kb,
                "link": f.get("webViewLink", ""),
            })

        return {
            "status": "success",
            "total": len(file_list),
            "folder_id": folder_id,
            "files": file_list,
        }

    except Exception as e:
        logger.error(f"list_drive_files error: {e}")
        return {"status": "error", "error": str(e)}

def read_drive_file(file_id: str, max_chars: int = 8000) -> dict:
    """Read the text content of a Google Drive file (Docs, plain text, CSV).
    """
    token = _get_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive tidak dikonfigurasi"}

    try:
        headers = {"Authorization": f"Bearer {token}"}

        # Get file metadata
        with httpx.Client(timeout=15) as client:
            meta = client.get(f"{GDRIVE_API}/files/{file_id}",
                              headers=headers,
                              params={"fields": "name,mimeType"})
            meta.raise_for_status()
            file_meta = meta.json()

        mime = file_meta.get("mimeType", "")
        name = file_meta.get("name", "unknown")

        # Choose export format
        if "google-apps.document" in mime:
            export_url = f"{GDRIVE_API}/files/{file_id}/export"
            params = {"mimeType": "text/plain"}
        elif "google-apps.spreadsheet" in mime:
            export_url = f"{GDRIVE_API}/files/{file_id}/export"
            params = {"mimeType": "text/csv"}
        elif "text" in mime or name.endswith((".txt", ".md", ".py", ".js", ".csv")):
            export_url = f"{GDRIVE_API}/files/{file_id}"
            params = {"alt": "media"}
        else:
            return {
                "status": "unsupported",
                "name": name,
                "mime": mime,
                "error": f"Jenis fail '{mime}' tidak boleh dibaca sebagai teks. Hanya Google Docs, Sheets, .txt, .md, .csv disokong."
            }

        with httpx.Client(timeout=20) as client:
            resp = client.get(export_url, headers=headers, params=params)
            resp.raise_for_status()
            content = resp.text[:max_chars]

        return {
            "status": "success",
            "name": name,
            "mime": mime,
            "chars_read": len(content),
            "content": content,
        }

    except Exception as e:
        logger.error(f"read_drive_file error: {e}")
        return {"status": "error", "error": str(e)}

def upload_to_drive(
    content_bytes: bytes,
    filename: str,
    mime_type: str = "text/plain",
    folder_id: str = None
) -> dict:
    """Upload a file (text, image, etc.) to the AURA Google Drive folder.
    """
    folder_id = folder_id or DEFAULT_FOLDER_ID
    token = _get_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive tidak dikonfigurasi"}

    try:
        headers = {"Authorization": f"Bearer {token}"}

        # Multipart upload
        metadata = json.dumps({
            "name": filename,
            "parents": [folder_id],
        })

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GDRIVE_UPLOAD_API}/files",
                params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                content=_build_multipart(metadata, content_bytes, mime_type),
                headers={
                    **headers,
                    "Content-Type": f"multipart/related; boundary=aura_boundary"
                }
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "status": "success",
            "file_id": data.get("id"),
            "name": data.get("name"),
            "link": data.get("webViewLink"),
            "message": f"Fail '{filename}' berjaya diupload ke Google Drive!"
        }

    except Exception as e:
        logger.error(f"upload_to_drive error: {e}")
        return {"status": "error", "error": str(e)}

def save_text_to_drive(text: str, filename: str, folder_id: str = None) -> dict:
    """Save a text string as a .txt or .md file to Google Drive.
    """
    mime = "text/markdown" if filename.endswith(".md") else "text/plain"
    return upload_to_drive(
        content_bytes=text.encode("utf-8"),
        filename=filename,
        mime_type=mime,
        folder_id=folder_id
    )

def search_drive_files(query: str, folder_id: str = None, max_results: int = 10) -> dict:
    """Search for files by name in the AURA Google Drive folder.
    """
    folder_id = folder_id or DEFAULT_FOLDER_ID
    token = _get_access_token()
    if not token:
        return {"status": "error", "error": "Google Drive tidak dikonfigurasi"}

    try:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": f"'{folder_id}' in parents and name contains '{query}' and trashed=false",
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
            "pageSize": max_results,
        }

        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{GDRIVE_API}/files", headers=headers, params=params)
            resp.raise_for_status()
            files = resp.json().get("files", [])

        return {
            "status": "success",
            "query": query,
            "total": len(files),
            "files": [{"name": f["name"], "id": f["id"], "link": f.get("webViewLink", "")} for f in files]
        }

    except Exception as e:
        logger.error(f"search_drive_files error: {e}")
        return {"status": "error", "error": str(e)}

def _build_multipart(metadata_json: str, file_bytes: bytes, mime_type: str) -> bytes:
    boundary = b"aura_boundary"
    body = (
        b"--" + boundary + b"\r\n"
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n" +
        metadata_json.encode() + b"\r\n"
        b"--" + boundary + b"\r\n"
        b"Content-Type: " + mime_type.encode() + b"\r\n\r\n" +
        file_bytes + b"\r\n"
        b"--" + boundary + b"--"
    )
    return body
```
