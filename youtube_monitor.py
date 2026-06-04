"""
youtube_monitor.py
Monitors official YouTube channels for new video uploads
using the YouTube Data API v3.

Uses playlistItems.list on the channel's uploads playlist —
only costs 1 quota unit per call vs 100 for search.list.

Requires YOUTUBE_API_KEY in Railway environment variables.

Channels monitored:
  Epic Seven  -> UCa1C3tWzsn4FFRR7t3LqU5w
  CZN         -> UCQ7YAXPdiccbFBmwuGvO3Jg
"""

import os
import requests
from datetime import datetime, timezone, timedelta

import config
import telegram_client
import database

YT_API_BASE = "https://www.googleapis.com/youtube/v3"

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

# Tracks video IDs already alerted on
_seen_video_ids: set[str] = set()

# Cache uploads playlist IDs so we don't re-fetch them every time
_uploads_playlist_cache: dict[str, str] = {}


def _get_api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        print("[YouTube] WARNING: YOUTUBE_API_KEY not set!")
    return key


def _get_uploads_playlist_id(channel_id: str, api_key: str) -> str | None:
    """
    Get the uploads playlist ID for a channel.
    The uploads playlist ID is always 'UU' + channel_id[2:]
    This is a YouTube convention — no API call needed!
    """
    # YouTube uploads playlist = replace first 2 chars 'UC' with 'UU'
    if channel_id.startswith("UC"):
        playlist_id = "UU" + channel_id[2:]
        print(f"[YouTube] Uploads playlist for {channel_id}: {playlist_id}")
        return playlist_id

    # Fallback: fetch via API if channel ID format is unexpected
    if channel_id in _uploads_playlist_cache:
        return _uploads_playlist_cache[channel_id]

    try:
        r = requests.get(
            f"{YT_API_BASE}/channels",
            params={
                "key":  api_key,
                "id":   channel_id,
                "part": "contentDetails",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        items = data.get("items", [])
        if not items:
            print(f"[YouTube] No channel found for ID: {channel_id}")
            return None

        playlist_id = (
            items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if playlist_id:
            _uploads_playlist_cache[channel_id] = playlist_id
        return playlist_id

    except Exception as e:
        print(f"[YouTube] Error fetching uploads playlist for {channel_id}: {e}")
        return None


def _fetch_latest_videos(channel_id: str, max_results: int = 5) -> list[dict]:
    """
    Fetch latest videos using playlistItems.list on the uploads playlist.
    Only costs 1 quota unit per call.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    playlist_id = _get_uploads_playlist_id(channel_id, api_key)
    if not playlist_id:
        return []

    try:
        r = requests.get(
            f"{YT_API_BASE}/playlistItems",
            params={
                "key":        api_key,
                "playlistId": playlist_id,
                "part":       "snippet",
                "maxResults": max_results,
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            err = data["error"]
            print(f"[YouTube] API error {err.get('code')}: {err.get('message')}")
            return []

        videos = []
        for item in data.get("items", []):
            snippet   = item.get("snippet", {})
            vid_id    = snippet.get("resourceId", {}).get("videoId", "")
            title     = snippet.get("title", "(no title)")
            published = snippet.get("publishedAt", "")

            # Skip deleted/private videos
            if title in ("[Deleted video]", "[Private video]"):
                continue

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

        print(f"[YouTube] Fetched {len(videos)} videos for channel {channel_id}")
        return videos

    except Exception as e:
        print(f"[YouTube] Fetch error for {channel_id}: {e}")
        return []


def preload_seen_videos() -> None:
    """Pre-load existing videos on startup to avoid re-alerting."""
    api_key = _get_api_key()
    if not api_key:
        print("[YouTube] Skipping preload — no API key.")
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
    """Poll each channel for new videos and alert subscribers."""
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

            _seen_video_ids.add(video["id"])
            print(f"[YouTube] New video from {channel['name']}: {video['title']}")

            date_str = f"\n\U0001f4c5 {video['published']}" if video["published"] else ""
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
    """Return latest N videos for a game. Used by /videos command."""
    channel = YOUTUBE_CHANNELS.get(game_key)
    if not channel:
        return []
    return _fetch_latest_videos(channel["channel_id"], max_results=limit)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _next_check_time() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")
