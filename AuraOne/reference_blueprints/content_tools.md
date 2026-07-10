# Content Rewriting Blueprint

Below is the verified code from AURA v5 for OpenRouter-powered content rewriting using custom prompts tailored for Malaysian social media writing styles.

```python
import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("aura.tools.content")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

STYLE_PROMPTS = {
    "affiliate": """SISTEM: Kau adalah pakar Copywriting Affiliate yang power buat soft-sell.

CIRI-CIRI WAJIB:
- Highlight masalah (pain point) yang diselesaikan oleh produk ini.
- Nyatakan kelebihan atau spesifikasi penting dengan cara yang menarik.
- Ayat nampak natural macam kawan recommend barang baik.
- WAJIB sediakan tempat kosong "[LINK SHOPEE]" atau "[LINK AFFILIATE]" di bahagian bawah (Call-to-Action).
- ANTI-HALLUCINATION: Fakta produk mesti berdasarkan artikel/data.

TUGAS: Tulis semula info berikut kepada Content Affiliate untuk platform {platform}.
Panjang: 120-180 patah perkataan.""",

    "hook_pembeli": """SISTEM: Kau adalah pakar Direct Response Marketing (Hard Sell) untuk High-Intent Buyers.

CIRI-CIRI WAJIB:
- Ayat PERTAMA mesti wujudkan FOMO (Fear of Missing Out) atau Offer Gila.
- Gunakan psikologi urgency: "Stok terhad", "Jangan lepaskan peluang".
- Ayat pendek, punchy, dan laju.
- Letakkan "[HARGA]" atau info diskaun jika ada.
- Call-to-action yang sangat jelas di akhir post.

TUGAS: Tulis semula info berikut dalam gaya Hook Cari Pembeli untuk platform {platform}.
Panjang: 100-150 patah perkataan.""",

    "update_berita": """SISTEM: Kau adalah wartawan media sosial yang melaporkan isu semasa atau gosip secara padat dan mudah dibaca.

CIRI-CIRI WAJIB:
- Gaya penulisan formal sedikit tapi mesra media sosial.
- Susun isi penting dalam bentuk Bullet Points supaya orang senang scan.
- Tiada pandangan peribadi (neutral).
- ANTI-HALLUCINATION: JANGAN tokok tambah fakta yang tiada dalam teks asal.

TUGAS: Tulis semula artikel berikut dalam gaya Update Berita untuk platform {platform}.
Panjang: 130-180 patah perkataan.""",

    "santai_bercerita": """SISTEM: Kau adalah penulis konten gaya Santai Bercerita (Storytelling) — kawan yang lepak kedai kopi dan pandai bercerita.

CIRI-CIRI WAJIB:
- Bercakap seperti kawan kepada kawan — informal, direct, real.
- Guna slang Malaysia yang natural: "weh", "korang", "memang", "beb", "lah", "kau", "aku".
- Mulakan dengan hook cerita pengalaman atau situasi yang orang boleh relate.
- JANGAN guna bahasa formal atau academic.

TUGAS: Tulis semula info berikut dalam gaya Santai Bercerita untuk platform {platform}.
Panjang: 150-200 patah perkataan.""",

    "cikgu_fadhli": """SISTEM: Kau meniru GAYA penulisan Cikgu Fadhli (Malaysia educator style).

CIRI-CIRI WAJIB:
- Kau adalah cikgu sekolah yang bijak relate isu semasa kepada kehidupan masyarakat.
- JANGAN OVER-RELIGIOUS - Boleh guna "ingatlah", "renung", tapi JANGAN jadi khutbah.
- LIMIT HIKMAH: Maksimum 1 idea pengajaran sahaja.
- Struktur: Opening (Salam) -> Context ringkas -> Reflection -> Closing lembut.
- ANTI-HALLUCINATION: Berpandukan isu sebenar.

TUGAS: Tulis semula artikel berikut dalam gaya Cikgu Fadhli untuk platform {platform}.
Panjang: 140-200 patah perkataan.""",
}

DEFAULT_STYLE = "santai_bercerita"

STYLE_DISPLAY_NAMES = {
    "affiliate": "Affiliate (Soft Sell)",
    "hook_pembeli": "Hook Pembeli (Hard Sell)",
    "update_berita": "Update Berita",
    "santai_bercerita": "Santai Bercerita",
    "cikgu_fadhli": "Cikgu Fadhli",
}

def rewrite_content(
    article_title: str,
    article_content: str,
    style: str = "santai_malaysia",
    platform: str = "facebook"
) -> dict:
    """Rewrite article content in a specific Malaysian writing style for social media.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    system_prompt_template = STYLE_PROMPTS.get(style, STYLE_PROMPTS[DEFAULT_STYLE])
    system_prompt = system_prompt_template.replace("{platform}", platform.title())

    user_message = f"Title: {article_title}\n\nContent:\n{article_content[:3000]}"

    if not api_key:
        return {
            "status": "error",
            "error": "OPENROUTER_API_KEY tidak ditemui. Set dalam .env untuk menggunakan content rewriting."
        }

    try:
        with httpx.Client(timeout=35) as client:
            resp = client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/matrol/aura-sdk",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 700,
                }
            )
            resp.raise_for_status()
            rewritten = resp.json()["choices"][0]["message"]["content"].strip()

            return {
                "status": "success",
                "rewritten": rewritten,
                "style": style,
                "style_name": STYLE_DISPLAY_NAMES.get(style, style),
                "platform": platform,
                "model_used": model,
            }
    except httpx.HTTPStatusError as e:
        logger.error(f"OpenRouter HTTP error: {e.response.status_code} — {e.response.text[:200]}")
        return {"status": "error", "error": f"LLM API error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Content rewrite error: {e}")
        return {"status": "error", "error": str(e)}

def list_available_styles() -> dict:
    """List all available content writing styles for AURA content pipeline.
    """
    return {
        "status": "success",
        "styles": [
            {"key": k, "name": v, "description": STYLE_PROMPTS[k][:80] + "..."}
            for k, v in STYLE_DISPLAY_NAMES.items()
        ],
        "default": DEFAULT_STYLE
    }
```
