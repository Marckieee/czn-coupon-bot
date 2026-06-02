"""
config.py
Loads all settings from .env and exposes them as constants.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_CHAT_ID  = int(os.getenv("ADMIN_CHAT_ID", "0"))

# --- Game definitions ---
GAMES = {
    "epic7": {
        "name":       "Epic Seven",
        "codes_url":  "https://ucngame.com/codes/epic-seven-codes/",
        "redeem_url": "https://epic7.onstove.com/en/coupon",
    },
    "czn": {
        "name":       "Chaos Zero Nightmare",
        "codes_url":  "https://game8.co/games/Chaos-Zero-Nightmare/archives/557967",
        "redeem_url": "https://page.onstove.com/chaoszeronightmare/en",
    },
}

# --- Scraper headers ---
SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# --- How often background checks run (in 60s loops) ---
SCRAPE_CHECK_INTERVAL = 15  # every 15 minutes


def validate():
    """Check required config values are set. Print warnings if not."""
    missing = []
    for key, val in [
        ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
        ("ADMIN_CHAT_ID",  ADMIN_CHAT_ID),
    ]:
        if not val or val == 0:
            missing.append(key)
    if missing:
        print(f"[Config] ⚠️  Missing values in .env: {', '.join(missing)}")
    else:
        print("[Config] ✅ All config values loaded.")
