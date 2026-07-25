# 📚 AURA-SDK — Prompts Registry Documentation

Folder ini mengandungi **single source of truth** untuk semua prompt persona, gaya bahasa, dan pengubah suai (modifiers) bagi pipeline automasi kandungan AuraOne.

---

## 📁 Struktur Folder

```
AuraOne/prompts/
├── __init__.py                 # REGISTRY utama + fungsi build_prompt()
├── README.md                   # Dokumentasi ini
├── shared/
│   └── global_rules.py         # Peraturan am merentasi semua platform
├── platforms/
│   ├── facebook.py             # 6 persona FB (berita, pemerhati, kedai_kopi, viral_santai, makcik_bawang, kisah_inspirasi)
│   ├── threads.py              # Bebenang 1/3/5/8 + gaya Threads
│   ├── x.py                    # Gaya & thread count X (Twitter)
│   └── lemon8.py               # Gaya & susun atur Lemon8
└── modifiers/
    └── length.py               # Modifier panjang (PENDEK 8-18 patah / BIASA 25-40 patah / PANJANG) bagi FB
```

---

## 🛠️ Panduan Menyunting & Menambah Persona

### 1. Nak Tambah Persona Baru Facebook?
Edit fail `prompts/platforms/facebook.py`:
- Tambah entri baru dalam kamus `FB_PERSONAS`:
  ```python
  "nama_persona": {
      "label": "FB: Label Butang 🎨",
      "hashtag": "#SaklumaHashtag",
      "systemPrompt": f"""..."""
  }
  ```
- Tiada perubahan pada logik kod UI diperlukan!

### 2. Nak Tambah Gaya / Bebenang Threads atau X?
- Edit fail `prompts/platforms/threads.py` untuk Threads.
- Edit fail `prompts/platforms/x.py` untuk X (Twitter).

### 3. Nak Ubah Syarat / Modifier Panjang (Section Length)?
Edit fail `prompts/modifiers/length.py`:
- Ubah definisi perkataan atau panduan dalam `LENGTH_OPTIONS`.
- Ubah fungsi `enforce_fb_length_limits()` jika perlu mengetatkan kawalan pemotongan perkataan.

---

## 🚀 Penggunaan Kod (Python API)

```python
from prompts import build_prompt, enforce_fb_length_limits

# FB Draft Generation
system_prompt, user_prompt = build_prompt(
    platform="facebook",
    style="viral_santai",
    length="pendek",          # 'pendek', 'biasa', atau 'panjang'
    show_title=False,
    raw=master_article_text
)

# Threads Draft Generation
system_prompt, user_prompt = build_prompt(
    platform="threads",
    style="genz",
    count="5",                 # '1', '3', '5', atau '8'
    raw=master_article_text
)
```

Jika `platform`, `style`, `length`, atau `count` yang dimohon tidak wujud, `build_prompt()` akan membuang **`KeyError`** yang jelas secara langsung.
