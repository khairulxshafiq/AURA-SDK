# AI Image Generation Blueprint

Below is the verified code from AURA v5 for generating images using Replicate (with the Flux Schnell model), prompt optimization, and Pollinations.ai fallback.

```python
import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger("aura.tools.image")

PLATFORM_DIMS = {
    "instagram": {"width": 1024, "height": 1024, "aspect_ratio": "1:1"},
    "facebook": {"width": 1200, "height": 630, "aspect_ratio": "1.91:1"},
    "twitter": {"width": 1200, "height": 675, "aspect_ratio": "16:9"},
    "linkedin": {"width": 1200, "height": 627, "aspect_ratio": "1.91:1"},
    "threads": {"width": 1080, "height": 1080, "aspect_ratio": "1:1"},
}

QUALITY_MODIFIERS = [
    "high quality", "professional", "detailed",
    "sharp focus", "high resolution", "studio lighting"
]

NEGATIVE_PROMPT = (
    "blurry, low quality, distorted face, extra limbs, watermark, "
    "text overlay, cartoon, anime, oversaturated, deformed, "
    "bad anatomy, ugly, disfigured, noisy, grainy"
)

def generate_image(
    description: str,
    style: str = "photorealistic",
    platform: str = "instagram",
    brand_colors: str = ""
) -> dict:
    """Generate an image using AI based on a description.
    """
    dims = PLATFORM_DIMS.get(platform.lower(), PLATFORM_DIMS["instagram"])

    # Build prompt
    prompt_parts = [description.strip()]
    if brand_colors:
        prompt_parts.append(f"color palette: {brand_colors}")

    lighting = "studio lighting" if style == "photorealistic" else "artistic lighting"
    quality = QUALITY_MODIFIERS.copy()
    quality[quality.index("studio lighting")] = lighting
    prompt_parts.extend(quality)

    full_prompt = ", ".join(prompt_parts)

    replicate_token = os.environ.get("REPLICATE_API_TOKEN", "")

    if not replicate_token:
        # Fallback to Pollinations.ai (Free, no token required)
        logger.info("No REPLICATE_API_TOKEN found. Falling back to Pollinations.ai")
        import urllib.parse
        encoded_prompt = urllib.parse.quote(full_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={dims['width']}&height={dims['height']}&nologo=true"
        
        return {
            "status": "success",
            "image_url": image_url,
            "prompt": full_prompt,
            "style": style,
            "dimensions": f"{dims['width']}x{dims['height']}",
            "aspect_ratio": dims["aspect_ratio"],
            "message": f"Gambar dijana (Pollinations Fallback)! Dimensi: {dims['width']}x{dims['height']}"
        }

    # Call Replicate Flux Schnell
    try:
        headers = {
            "Authorization": f"Token {replicate_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": "black-forest-labs/flux-schnell",
            "input": {
                "prompt": full_prompt,
                "width": dims["width"],
                "height": dims["height"],
                "num_inference_steps": 4,
                "negative_prompt": NEGATIVE_PROMPT,
            }
        }

        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            prediction = resp.json()
            poll_url = prediction.get("urls", {}).get("get", "")

        if not poll_url:
            return {"status": "error", "error": "No polling URL from Replicate"}

        for attempt in range(30):  # max 60s
            time.sleep(2)
            with httpx.Client(timeout=10) as client:
                poll_resp = client.get(poll_url, headers=headers)
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()

            poll_status = poll_data.get("status")
            if poll_status == "succeeded":
                output_urls = poll_data.get("output", [])
                image_url = output_urls[0] if output_urls else ""
                return {
                    "status": "success",
                    "image_url": image_url,
                    "prompt": full_prompt,
                    "style": style,
                    "dimensions": f"{dims['width']}x{dims['height']}",
                    "aspect_ratio": dims["aspect_ratio"],
                    "message": f"Gambar berjaya dijana! Dimensions: {dims['width']}x{dims['height']}"
                }
            elif poll_status == "failed":
                error = poll_data.get("error", "Unknown error")
                return {"status": "error", "error": f"Replicate generation failed: {error}"}

        return {"status": "error", "error": "Image generation timed out after 60 seconds."}

    except httpx.HTTPStatusError as e:
        logger.error(f"Replicate HTTP error: {e.response.status_code}")
        return {"status": "error", "error": f"Replicate API error {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return {"status": "error", "error": str(e)}

def build_image_prompt(
    topic: str,
    style: str = "photorealistic",
    platform: str = "instagram"
) -> dict:
    """Build an optimised AI image prompt from a topic without generating the actual image.
    """
    dims = PLATFORM_DIMS.get(platform.lower(), PLATFORM_DIMS["instagram"])
    quality = ", ".join(QUALITY_MODIFIERS)
    prompt = f"{topic}, {style}, {quality}"

    return {
        "status": "success",
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "style": style,
        "platform": platform,
        "dimensions": f"{dims['width']}x{dims['height']}",
        "aspect_ratio": dims["aspect_ratio"]
    }
```
