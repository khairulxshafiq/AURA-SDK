"""
ADELIA PROMPT ENGINE — Length Modifiers (Facebook Exclusive)
Defines rules and post-processing handlers for section length options: Pendek, Biasa, Panjang.
"""

LENGTH_OPTIONS = {
    "pendek": {
        "label": "Pendek (8–18 patah perkataan)",
        "guide": "Hasilkan HANYA 1 AYAT HOOK SANGAT RINGKAS antara 8 hingga 18 patah perkataan SAHAJA secara keseluruhan. Satu punchline padat, 1 idea sahaja, macam status pendek. DILARANG SAMA SEKALI melebihi 18 patah perkataan!"
    },
    "biasa": {
        "label": "Biasa (25–40 patah perkataan)",
        "guide": "Hasilkan 1-2 perenggan pendek antara 25 hingga 40 patah perkataan secara keseluruhan. Ringkas, padat dengan konteks yang mencukupi."
    },
    "panjang": {
        "label": "Panjang (Penuh)",
        "guide": "Hasilkan hantaran penceritaan penuh secara terperinci antara 3 hingga 5 perenggan pendek mengalir mengikut persona."
    }
}

def get_length_instruction(length_option: str = "panjang") -> str:
    """Return prompt instruction string for given length option.
    Raises KeyError if invalid length_option is passed.
    """
    key = str(length_option).lower().strip()
    if key not in LENGTH_OPTIONS:
        valid_keys = ", ".join(f"'{k}'" for k in LENGTH_OPTIONS.keys())
        raise KeyError(f"Pilihan length '{length_option}' tidak wujud dalam prompts/modifiers/length.py. Pilihan sah: {valid_keys}")
    
    info = LENGTH_OPTIONS[key]
    return f"\n\nSYARAT PANJANG ({key.upper()}): {info['guide']}"

def enforce_fb_length_limits(text: str, fb_len: str = "panjang", show_title: bool = False) -> str:
    """Strictly truncate output text if fb_len == 'pendek' to guarantee 8-18 word limit."""
    if not text or fb_len != "pendek":
        return text

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return text

    hashtag_lines = [l for l in lines if l.startswith("#")]
    content_lines = [l for l in lines if not l.startswith("#")]

    if not content_lines:
        return text

    hashtag_str = " ".join(hashtag_lines)

    if show_title and len(content_lines) > 1:
        title_part = content_lines[0]
        body_part = " ".join(content_lines[1:])
    else:
        title_part = ""
        body_part = " ".join(content_lines)

    words = body_part.split()
    if len(words) > 18:
        body_part = " ".join(words[:18])
        if not body_part.endswith((".", "!", "?")):
            body_part += "!"

    res_lines = []
    if title_part:
        res_lines.append(title_part)
    res_lines.append(body_part)

    res = "\n\n".join(res_lines)
    if hashtag_str:
        res += f"\n\n{hashtag_str}"

    return res
