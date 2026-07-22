import time
import logging
import httpx
from config import APIFY_API_TOKEN

logger = logging.getLogger("aura.tools.apify_service")

def run_apify_actor(actor_id: str, run_input: dict) -> dict:
    """Run an Apify actor, wait for completion, and return dataset items."""
    token = APIFY_API_TOKEN
    if not token:
        return {"status": "error", "error": "APIFY_API_TOKEN is not configured in .env"}

    logger.info(f"Running Apify actor '{actor_id}'...")

    actor_id_url = actor_id.replace("/", "~")

    resolved_input = run_input.copy()
    if "location" in resolved_input and isinstance(resolved_input["location"], str) and resolved_input["location"].startswith("http"):
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                resp = client.get(resolved_input["location"])
                resolved_url = str(resp.url)
                logger.info(f"Resolved redirect for location URL: {resolved_input['location']} -> {resolved_url}")
                resolved_input["location"] = resolved_url
        except Exception as e:
            logger.warning(f"Could not resolve redirect: {e}")

    elif "startUrls" in resolved_input and isinstance(resolved_input["startUrls"], list):
        for idx, entry in enumerate(resolved_input["startUrls"]):
            if isinstance(entry, dict) and "url" in entry and entry["url"].startswith("http"):
                try:
                    with httpx.Client(timeout=10, follow_redirects=True) as client:
                        resp = client.get(entry["url"])
                        resolved_url = str(resp.url)
                        logger.info(f"Resolved redirect for startUrls[{idx}]: {entry['url']} -> {resolved_url}")
                        resolved_input["startUrls"][idx]["url"] = resolved_url
                except Exception as e:
                    logger.warning(f"Could not resolve redirect: {e}")

    # 1. Trigger Actor run
    url_run = f"https://api.apify.com/v2/acts/{actor_id_url}/runs"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url_run, params={"token": token}, json=resolved_input)
            resp.raise_for_status()
            run_data = resp.json()["data"]
    except Exception as e:
        return {"status": "error", "error": f"Failed to trigger Apify actor: {str(e)}"}

    run_id = run_data["id"]
    dataset_id = run_data["defaultDatasetId"]
    logger.info(f"Actor run started. Run ID: {run_id}, Dataset ID: {dataset_id}")

    # 2. Poll for completion
    url_status = f"https://api.apify.com/v2/actor-runs/{run_id}"
    max_retries = 30  # 5 minutes max
    for attempt in range(max_retries):
        time.sleep(10)
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url_status, params={"token": token})
                resp.raise_for_status()
                status_data = resp.json()["data"]
                status = status_data["status"]
                logger.info(f"Attempt {attempt+1}: Run status = {status}")
                if status == "SUCCEEDED":
                    break
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    return {"status": "error", "error": f"Actor run failed with status: {status}"}
        except Exception as e:
            logger.warning(f"Error checking run status: {str(e)}")
    else:
        return {"status": "error", "error": "Actor run timed out"}

    # 3. Fetch Dataset items
    url_dataset = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(url_dataset, params={"token": token})
            resp.raise_for_status()
            items = resp.json()
            return {
                "status": "success",
                "actorId": actor_id,
                "runId": run_id,
                "datasetId": dataset_id,
                "items": items,
                "count": len(items)
            }
    except Exception as e:
        return {"status": "error", "error": f"Failed to fetch dataset items: {str(e)}"}
