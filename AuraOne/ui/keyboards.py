from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import storage.location_repository as location_repo

def _get_direct_confirm_keyboard(platform_drafts: list) -> InlineKeyboardMarkup:
    keyboard = []
    for plat in platform_drafts:
        keyboard.append([
            InlineKeyboardButton(f"✅ Confirm & Post {plat.upper()}", callback_data=f"confirm_platform:{plat}")
        ])
    return InlineKeyboardMarkup(keyboard)

def _get_platform_keyboard(state_data: dict) -> InlineKeyboardMarkup:
    selected = state_data.get("selected", [])
    platforms = [
        ("Facebook", "facebook"),
        ("X (Twitter)", "x"),
        ("Threads", "threads"),
        ("Lemon8", "lemon8"),
        ("Instagram", "instagram")
    ]

    keyboard = []
    row = []
    for label, val in platforms:
        status = "✅ " if val in selected else "⬜ "
        row.append(InlineKeyboardButton(f"{status}{label}", callback_data=f"toggle:{val}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("Next ➡️", callback_data="platform_next")])
    return InlineKeyboardMarkup(keyboard)

def _get_sub_options_keyboard(state_data: dict) -> InlineKeyboardMarkup:
    selected = state_data.get("selected", [])
    options = state_data.get("options", {})

    keyboard = []

    if "facebook" in selected:
        curr_fb = options.get("facebook", "viral_santai")
        personas = [
            ("berita", "FB: Berita 📰"),
            ("pemerhati", "FB: Pemerhati 👀"),
            ("kedai_kopi", "FB: Kedai Kopi ☕"),
            ("viral_santai", "FB: Viral Santai 🍿"),
            ("makcik_bawang", "FB: Makcik Bawang 🗣️"),
            ("kisah_inspirasi", "FB: Kisah Inspirasi ✨")
        ]

        row = []
        for code, label in personas:
            status = "✅ " if curr_fb == code else "⬜ "
            row.append(InlineKeyboardButton(f"{status}{label}", callback_data=f"sub:facebook:{code}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        curr_fb_len = options.get("fb_len", "panjang")
        keyboard.append([
            InlineKeyboardButton(f"{'✅ ' if curr_fb_len == 'pendek' else '⬜ '}FB: Pendek (8-15)", callback_data="sub:fb_len:pendek"),
            InlineKeyboardButton(f"{'✅ ' if curr_fb_len == 'biasa' else '⬜ '}FB: Biasa (36-50)", callback_data="sub:fb_len:biasa"),
            InlineKeyboardButton(f"{'✅ ' if curr_fb_len == 'panjang' else '⬜ '}FB: Panjang", callback_data="sub:fb_len:panjang")
        ])

    if "x" in selected or "threads" in selected:
        curr_len = options.get("thread_len", 5)
        keyboard.append([
            InlineKeyboardButton(f"{'✅ ' if curr_len == 3 else '⬜ '}Bebenang: 3 Post", callback_data="sub:thread_len:3"),
            InlineKeyboardButton(f"{'✅ ' if curr_len == 5 else '⬜ '}Bebenang: 5 Post", callback_data="sub:thread_len:5"),
            InlineKeyboardButton(f"{'✅ ' if curr_len == 8 else '⬜ '}Bebenang: 8 Post", callback_data="sub:thread_len:8")
        ])

    keyboard.append([InlineKeyboardButton("Generate Drafts ⚡", callback_data="sub_next")])
    return InlineKeyboardMarkup(keyboard)

def _get_gnews_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("💻 Gajet & Tech", callback_data="gnews_cat:gajet"),
            InlineKeyboardButton("💼 Korporat", callback_data="gnews_cat:korporat")
        ],
        [
            InlineKeyboardButton("🎭 Artis & Hiburan", callback_data="gnews_cat:artis"),
            InlineKeyboardButton("⚽ Sukan", callback_data="gnews_cat:sukan")
        ],
        [
            InlineKeyboardButton("🔥 Viral & Confession", callback_data="viral_menu:0"),
            InlineKeyboardButton("⚡ Isu Semasa", callback_data="gnews_cat:nasional")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def _get_viral_confessions_keyboard(offset: int = 0) -> InlineKeyboardMarkup:
    next_offset = offset + 6
    keyboard = [
        [
            InlineKeyboardButton("🔥 More Confessions", callback_data=f"viral_menu:{next_offset}"),
            InlineKeyboardButton("◀️ Back Ke Menu News", callback_data="gnews_back")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def _get_location_keyboard(user_id: int, current_lat: float, current_lon: float) -> InlineKeyboardMarkup:
    places = location_repo.get_user_places(user_id)

    if "home" in places:
        h_lat = places["home"]["lat"]
        h_lon = places["home"]["lon"]
        home_nav_url = f"https://www.google.com/maps/dir/?api=1&origin={current_lat},{current_lon}&destination={h_lat},{h_lon}"
        home_btn = InlineKeyboardButton("🏠 Home", url=home_nav_url)
    else:
        home_btn = InlineKeyboardButton("🏠 Set Home", callback_data="loc_action:set_home")

    if "hq" in places:
        hq_lat = places["hq"]["lat"]
        hq_lon = places["hq"]["lon"]
        work_nav_url = f"https://www.google.com/maps/dir/?api=1&origin={current_lat},{current_lon}&destination={hq_lat},{hq_lon}"
        work_btn = InlineKeyboardButton("🏢 Work", url=work_nav_url)
    else:
        work_btn = InlineKeyboardButton("🏢 Set Work", callback_data="loc_action:set_hq")

    makan_url = f"https://www.google.com/maps/search/Kedai+Makan+Sedap/@{current_lat},{current_lon},15z"
    cafe_url = f"https://www.google.com/maps/search/Cafe/@{current_lat},{current_lon},15z"
    petrol_url = f"https://www.google.com/maps/search/Stesen+Minyak/@{current_lat},{current_lon},15z"
    hardware_url = f"https://www.google.com/maps/search/Kedai+Hardware/@{current_lat},{current_lon},15z"

    keyboard = [
        [
            home_btn,
            work_btn,
            InlineKeyboardButton("🎉 Events", callback_data="loc_action:events_nearby")
        ],
        [
            InlineKeyboardButton("🍽️ Makan Best", url=makan_url),
            InlineKeyboardButton("☕ Cafe Lepak", url=cafe_url),
        ],
        [
            InlineKeyboardButton("⛽ Stesen Minyak", url=petrol_url),
            InlineKeyboardButton("🛠️ Hardware", url=hardware_url)
        ]
    ]

    return InlineKeyboardMarkup(keyboard)
