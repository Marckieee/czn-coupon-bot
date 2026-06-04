"""
youtube_monitor.py
Monitors official YouTube channels for new video uploads
using the YouTube Data API v3.

Requires YOUTUBE_API_KEY in your .env / Railway environment variables.

Channels monitored:
  Epic Seven  → UCa1C3tWzsn4FFRR7t3LqU5w
  CZN         → UCQ7YAXPdiccbFBmwuGvO3Jg
"""

import requests
from datetime import datetime, timezone, timedelta

import config
import telegram_client
import database

# YouTube Data API v3 endpoint
YT_API_BASE = "https://www.googleapis.com/youtube/v3"

# Channel IDs for each game
YOUTUBE_CHANNELS = {
    "epic7": {
        "channel_id":  "UCa1C3tWzsn4FFRR7t3LqU5w",
        "name":        "Epic Seven",
        "channel_url": "https://www.youtube.com/channel/UCa1C3tWzsn4FFRR7t3LqU5w",
    },
    "czn": {
        "channel_id":  "UCQ7YAXPdiccbFBmwuGvO3Jg",
        "name":        "Chaos Zero Nightmare",
        "channel_url": "https://www.youtube.com/@ChaosZeroNightmare_EN",
    },
}

# Tracks video IDs we've already alerted on
_seen_video_ids: set[str] = set()


def _get_api_key() -> str:
    """Get YouTube API key from environment."""
    import os
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        print("[YouTube] ⚠️ YOUTUBE_API_KEY not set in environment variables!")
    return key


def _fetch_latest_videos(channel_id: str, max_results: int = 5) -> list[dict]:
    """
    Fetch latest videos for a channel using YouTube Data API v3.
    Returns list of video dicts: { id, title, url, published }.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    try:
        # Use search.list to get latest videos from channel
        r = requests.get(
            f"{YT_API_BASE}/search",
            params={
                "key":        api_key,
                "channelId":  channel_id,
                "part":       "snippet",
                "order":      "date",
                "type":       "video",
                "maxResults": max_results,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            print(f"[YouTube] API error: {data['error'].get('message', 'unknown')}")
            return []

        videos = []
        for item in data.get("items", []):
            vid_id    = item["id"].get("videoId", "")
            snippet   = item.get("snippet", {})
            title     = snippet.get("title", "(no title)")
            published = snippet.get("publishedAt", "")

            # Format published date nicely
            date_str = ""
            if published:
                try:
                    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    date_str = dt.strftime("%d %b %Y")
                except Exception:
                    date_str = published[:10]

            if vid_id:
                videos.append({
                    "id":        vid_id,
                    "title":     title,
                    "url":       f"https://www.youtube.com/watch?v={vid_id}",
                    "published": date_str,
                })

        return videos

    except Exception as e:
        print(f"[YouTube] Fetch error for {channel_id}: {e}")
        return []


def preload_seen_videos() -> None:
    """
    Fetch current videos on startup so we don't alert for
    videos that were already uploaded before the bot started.
    """
    api_key = _get_api_key()
    if not api_key:
        print("[YouTube] Skipping preload — no API key set.")
        return

    total = 0
    for game_key, channel in YOUTUBE_CHANNELS.items():
        videos = _fetch_latest_videos(channel["channel_id"], max_results=10)
        for v in videos:
            _seen_video_ids.add(v["id"])
        total += len(videos)
        print(f"[YouTube] Pre-loaded {len(videos)} videos for {channel['name']}")
    print(f"[YouTube] Total pre-loaded: {total} video IDs.")


def check_youtube() -> None:
    """
    Poll each channel for new videos via the API.
    Broadcast an alert to all subscribers if a new video is found.
    """
    api_key = _get_api_key()
    if not api_key:
        return

    for game_key, channel in YOUTUBE_CHANNELS.items():
        videos = _fetch_latest_videos(channel["channel_id"], max_results=5)

        if not videos:
            database.update_monitor_state(
                key        = f"{game_key}_youtube",
                last_check = _now(),
                next_check = _next_check_time(),
                status     = "error"
            )
            continue

        for video in videos:
            if video["id"] in _seen_video_ids:
                continue

            # New video found!
            _seen_video_ids.add(video["id"])
            print(f"[YouTube] New video from {channel['name']}: {video['title']}")

            date_str = f"\n\U0001f4c5 {video['published']}" if video['published'] else ""
            alert = (
                f"\U0001f534 New {channel['name']} Video!\n\n"
                f"\U0001f3ac {video['title']}{date_str}\n\n"
                f"\U0001f517 {video['url']}"
            )

            subscribers = database.get_all_subscribers()
            if subscribers:
                ok, fail = telegram_client.broadcast(subscribers, alert)
                print(f"[YouTube] Alert sent to {ok} subscribers ({fail} failed)")
            else:
                telegram_client.send_admin(alert)

        database.update_monitor_state(
            key        = f"{game_key}_youtube",
            last_check = _now(),
            next_check = _next_check_time(),
            status     = "ok"
        )


def get_latest_videos(game_key: str, limit: int = 5) -> list[dict]:
    """Return the latest N videos for a game. Used by /videos command."""
    channel = YOUTUBE_CHANNELS.get(game_key)
    if not channel:
        return []
    return _fetch_latest_videos(channel["channel_id"], max_results=limit)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _next_check_time() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")
