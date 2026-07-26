"""
AURA PROMPT ENGINE — Threads Platform Personas & Thread Counts
Contains thread count configurations (1, 3, 5, 8) and styles (genz, informative, kepoh, catchy, hook_memanggil).
"""

from prompts.shared.global_rules import GLOBAL_RULES
from prompts.shared.hashtags import get_hashtags

THREADS_GLOBAL = f"""
PERATURAN AM (Threads):
- Bahasa: Melayu santai Malaysia, natural, terus ke poin tanpa meleret.
- OPTIMUM MASA BACA (3 SAAT): Pembaca skrol sangat laju. Bebenang PERTAMA mesti hook tajam yang henti skrol dalam 3 saat.
- PERATURAN EMOJI STRICT: KURANGKAN EMOJI. Maksimum 0 hingga 1 emoji sahaja setiap hantaran untuk mengelakkan semak.
- Format WAJIB bebenang: setiap hantaran dipisah dengan penanda "---".
- JANGAN reka fakta/angka/nama yang tak ada dalam INPUT.
- Sensitif: elak fitnah, tuduhan jenayah spesifik, isu SARA.
- Output: teks bebenang sahaja (dengan "---" sebagai pemisah). Tiada meta-text.
{GLOBAL_RULES}
"""

THREAD_COUNTS = {
    "1": {
        "label": "1 Hantaran (Single)",
        "guide": "Hasilkan TEPAT 1 hantaran sahaja (Single post). Hook tajam dalam 3 saat pertama + isi ringkas padat + penutup ringkas."
    },
    "3": {
        "label": "3 Bebenang",
        "guide": "Hasilkan TEPAT 3 bebenang dipisahkan dengan penanda '---'. Bebenang 1: HOOK tajam henti skrol. Bebenang 2: Isi utama / point penting. Bebenang 3: Penutup + CTA ringkas."
    },
    "5": {
        "label": "5 Bebenang",
        "guide": "Hasilkan TEPAT 5 bebenang dipisahkan dengan penanda '---'. Bebenang 1: HOOK tajam. Bebenang 2-4: Perkembangan cerita/point demi point. Bebenang 5: Penutup + CTA ringkas."
    },
    "8": {
        "label": "8 Bebenang",
        "guide": "Hasilkan TEPAT 8 bebenang dipisahkan dengan penanda '---'. Bebenang 1: HOOK. Bebenang 2-7: Point demi point (1 point per bebenang). Bebenang 8: Penutup. WAJIB hasilkan kesemua 8 bebenang tanpa terpotong!"
    }
}

THREADS_STYLES = {
    "genz": {
        "label": "GenZ ⚡",
        "guide": "GAYA: GEN Z (Fast-Paced, Relatable, Slang Natural). Bahasa muda, santai, terus ke poin. Slanga natural (fr, real, vibe, lowkey). Hook tajam."
    },
    "informative": {
        "label": "Informative 📊",
        "guide": "GAYA: INFORMATIVE (Jelas, Berfaedah, Ringkas). Fokus fakta utama dan info berguna secara ringkas & berstruktur."
    },
    "kepoh": {
        "label": "Kepoh 🗣️",
        "guide": "GAYA: KEPOH (Sensasi, Bisik-Bisik, Ajak Komen). Gaya heboh, nak tahu cerita, tanya soalan kontras/dramatik."
    },
    "catchy": {
        "label": "Catchy 🍿",
        "guide": "GAYA: CATCHY (Pantas, Menarik, Ringkas). Fokus headline yang mengusik rasa ingin tahu."
    },
    "hook_memanggil": {
        "label": "Hook Memanggil 📢",
        "guide": "GAYA: HOOK MEMANGGIL (Soalan Provokatif & Ajak Respons). Mula dengan soalan panas yang memanggil pembaca menyertai perbincangan."
    }
}


def build_threads_prompt(style: str, count: str | int, raw_content: str, seed=None) -> tuple[str, str]:
    """Bina prompt (system, user) untuk Threads.
    Raises KeyError jika style atau count tidak wujud.
    """
    ck = str(count).strip()
    if ck not in THREAD_COUNTS:
        valid_counts = ", ".join(f"'{k}'" for k in THREAD_COUNTS.keys())
        raise KeyError(f"Bilangan bebenang '{count}' tak wujud dalam prompts/platforms/threads.py. Pilihan sah: {valid_counts}")

    sk = str(style).lower().strip()
    if sk not in THREADS_STYLES:
        valid_styles = ", ".join(f"'{k}'" for k in THREADS_STYLES.keys())
        raise KeyError(f"Gaya '{style}' tak wujud dalam prompts/platforms/threads.py. Gaya sah: {valid_styles}")

    c = THREAD_COUNTS[ck]
    s = THREADS_STYLES[sk]
    tags = get_hashtags("threads", count=2, seed=seed)

    system_prompt = f"""Kau ialah copywriter Threads profesional.
{s['guide']}

{c['guide']}

{THREADS_GLOBAL.strip()}"""

    user_prompt = f"""INPUT / BAHAN MENTAH:
{raw_content}

Hasilkan Threads: {c['label']} dalam gaya "{s['label']}".
Ingat: pisahkan setiap bebenang dengan "---".
Akhiri post dengan hashtag ini di bahagian hujung: {tags}."""

    return system_prompt, user_prompt
