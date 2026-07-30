import httpx
import logging
from config import AMIRA_SERVICE_URL

logger = logging.getLogger("aura.tools.amira_client")

def delegate_to_amira(symbol: str, user_prompt: str = "", market: str = "MY") -> str:
    url = f"{AMIRA_SERVICE_URL}/api/v1/analyze" if AMIRA_SERVICE_URL else "http://amira-app:8000/api/v1/analyze"
        
    payload = {
        "symbol": symbol,
        "user_prompt": user_prompt,
        "market": market
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("report", str(data))
    except Exception as e:
        logger.error(f"Failed to delegate to AMIRA: {e}")
        return f"⚠️ Gagal menghubungi sistem AMIRA Trading Engine.\n\nRalat: {str(e)}"
