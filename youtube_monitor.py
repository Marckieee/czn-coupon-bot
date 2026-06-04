"""
youtube_monitor.py
Monitors official YouTube channels for new video uploads
using YouTube's public RSS feeds — no API key required.

Channels monitored:
  Epic Seven  → UCa1C3tWzsn4FFRR7t3LqU5w
  CZN         → UCmzdpIDekCvB6dooVPAVzqw
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import config
import telegram_client
import database

# YouTube RSS feed base URL
YT_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="

# Channel IDs for each game
YOUTUBE_CHANNELS = {
    "epic7": {
        "channel_id": "UCa1C3tWzsn4FFRR7t3LqU5w",
        "name":       "Epic Seven",
    },
    "czn": {
        "channel_id": "UCmzdpIDekCvB6dooVPAVzqw",
        "name":       "Chaos Zero Nightmare",
    },
}

# Tracks video IDs we've already alerted on
_seen_video_ids: set[str] = set()

# XML namespace used by YouTube RSS feeds
NS = {
    "atom":   "http://www.w3.org/2005/Atom",
    "yt":     "http://www.youtube.com/xml/schemas/2015",
    "media":  "http://search.yahoo.com/mrss/",
}


def _fetch_feed(channel_id: str) -> list[dict]:
    """
    Fetch a YouTube RSS feed and return a list of video dicts:
      { id, title, url, published, thumbnail }
    Returns empty list on error.
    """
    url = YT_RSS_BASE + channel_id
    try:
        r = requests.get(url, headers=config.SCRAPE_HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[YouTube] Failed to fetch feed for {channel_id}: {e}")
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"[YouTube] Failed to parse feed XML: {e}")
        return []

    videos = []
    for entry in root.findall("atom:entry", NS):
        vid_id    = entry.findtext("yt:videoId",   namespaces=NS) or ""
        title     = entry.findtext("atom:title",   namespaces=NS) or "(no title)"
        published = entry.findtext("atom:published", namespaces=NS) or ""
        link_el   = entry.find("atom:link",        NS)
        url       = link_el.get("href", "") if link_el is not None else ""

        # Thumbnail from media:group/media:thumbnail
        thumbnail = ""
        media_grp = entry.find("media:group", NS)
        if media_grp is not None:
            thumb_el = media_grp.find("media:thumbnail", NS)
            if thumb_el is not None:
                thumbnail = thumb_el.get("url", "")

        if vid_id:
            videos.append({
                "id":        vid_id,
                "title":     title,
                "url":       url,
                "published": published,
                "thumbnail": thumbnail,
            })

    return videos


def preload_seen_videos() -> None:
    """
    Fetch current videos on startup so we don't alert for
    videos that were already uploaded before the bot started.
    """
    total = 0
    for game_key, channel in YOUTUBE_CHANNELS.items():
        videos = _fetch_feed(channel["channel_id"])
        for v in videos:
            _seen_video_ids.add(v["id"])
        total += len(videos)
    print(f"[YouTube] Pre-loaded {total} existing video IDs.")


def check_youtube() -> None:
    """
    Poll each channel's RSS feed for new videos.
    Broadcast an alert to all subscribers if a new video is found.
    """
    for game_key, channel in YOUTUBE_CHANNELS.items():
        videos = _fetch_feed(channel["channel_id"])

        for video in videos:
            if video["id"] in _seen_video_ids:
                continue

            # New video found!
            _seen_video_ids.add(video["id"])
            print(f"[YouTube] New video from {channel['name']}: {video['title']}")

            alert = (
                f"\U0001f534 New {channel['name']} Video!\n\n"
                f"\U0001f3ac {video['title']}\n\n"
                f"\U0001f517 {video['url']}"
            )

            subscribers = database.get_all_subscribers()
            if subscribers:
                ok, fail = telegram_client.broadcast(subscribers, alert)
                print(f"[YouTube] Alert sent to {ok} subscribers ({fail} failed)")
            else:
                telegram_client.send_admin(alert)

            # Update monitor state
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
    return _fetch_feed(channel["channel_id"])[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def _next_check_time() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")
