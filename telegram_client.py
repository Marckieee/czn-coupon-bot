"""
telegram_client.py
Handles all communication with the Telegram Bot API.
"""

import requests
import config

BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"


def send(chat_id: int, text: str) -> None:
    """Send a plain-text message, auto-splitting if over 4000 chars."""
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            requests.post(
                f"{BASE_URL}/sendMessage",
                data={"chat_id": chat_id, "text": chunk},
                timeout=10,
            )
        except Exception as e:
            print(f"[Telegram] Send error: {e}")


def send_admin(text: str) -> None:
    """Shortcut to send a message to the admin chat."""
    send(config.ADMIN_CHAT_ID, text)


def get_updates(offset: int | None = None) -> list[dict]:
    """
    Fetch new Telegram updates (long-poll, 10s timeout).
    Returns a list of update dicts, or empty list on error.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/getUpdates",
            params={"offset": offset, "timeout": 10},
            timeout=15,
        ).json()
        return response.get("result", [])
    except Exception as e:
        print(f"[Telegram] getUpdates error: {e}")
        return []
