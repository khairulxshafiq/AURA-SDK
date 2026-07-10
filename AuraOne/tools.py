import os
import requests

def scrape_web(url: str) -> str:
    """Scrapes the content of a given web page URL using Firecrawl and returns the markdown text.

    Args:
        url: The web page URL to scrape, e.g. "https://news.ycombinator.com".
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key or api_key == "your_firecrawl_api_key_here":
        return "Error: FIRECRAWL_API_KEY is not configured in the .env file."
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": url,
        "formats": ["markdown"]
    }
    
    try:
        response = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            json=payload,
            headers=headers,
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            # Try to get markdown format
            markdown_content = data.get("data", {}).get("markdown")
            if markdown_content:
                return markdown_content
            # Fallback to whole data structure as string
            return str(data)
        else:
            return f"Error: Firecrawl API request failed with status code {response.status_code}. Response: {response.text}"
    except Exception as e:
        return f"Error occurred while scraping: {str(e)}"
