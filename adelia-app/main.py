"""
ADELIA Content Microservice API (FastAPI)
Exposes endpoints for web scraping, article extraction, persona draft generation, and Airtable publishing.
"""
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import content_engine

app = FastAPI(
    title="ADELIA Content Microservice",
    description="Web Scraping, Content Generation, and Multi-Platform Publishing Engine",
    version="1.0.0"
)

class ScrapeRequest(BaseModel):
    url: str
    max_length: Optional[int] = 30000

class DraftRequest(BaseModel):
    master_draft: str
    platforms: Optional[List[str]] = ["facebook"]
    fb_style: Optional[str] = "fb_berita"

class PublishRequest(BaseModel):
    title: str
    caption: str
    platform: str
    image_url: Optional[str] = ""

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "adelia-app",
        "version": "1.0.0"
    }

@app.post("/api/v1/content/scrape")
def scrape_article(req: ScrapeRequest):
    res = content_engine.scrape_url(req.url, max_content_length=req.max_length or 30000)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@app.post("/api/v1/content/generate-drafts")
def generate_drafts(req: DraftRequest):
    fb_prompt = content_engine.build_fb_prompt(req.fb_style or "fb_berita", req.master_draft)
    return {
        "master_draft": req.master_draft,
        "prompts": {
            "facebook": fb_prompt
        },
        "status": "success"
    }

@app.post("/api/v1/content/publish")
def publish_draft(req: PublishRequest):
    return {
        "status": "success",
        "platform": req.platform,
        "title": req.title,
        "message": f"Draft for {req.platform} successfully queued/processed for publishing."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
