"""
youtube_monitor.py
Monitors official YouTube channels for new video uploads
using YouTube's public RSS feeds — no API key required.

Channels monitored:
  Epic Seven  → UCa1C3tWzsn4FFRR7t3LqU5w
  CZN         → UCQ7YAXPdiccbFBmwuGvO3Jg
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import config
import telegram_client
import database

# YouTube RSS feed base URL
YT_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="

# Headers that mimic a real browser more closely
YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control":   "no-cache",
}

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

# XML namespaces used by YouTube RSS feeds
NS = {
    "atom":  "http://www.w3.org/2005/Atom",
    "yt":    "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def _fetch_feed(channel_id: str) -> list[dict]:
    """
    Fetch a YouTube RSS feed and return a list of video dicts.
    Tries two different URL formats in case one is blocked.
    """
    urls_to_try = [
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}&hl=en",
    ]

    for url in urls_to_try:
        try:
            r = requests.get(url, headers=YT_HEADERS, timeout=20)
            r.raise_for_status()

            # Check we actually got XML not a block/redirect page
            if "<feed" not in r.text and "<rss" not in r.text:
                print(f"[YouTube] Got non-XML response from {url} — may be blocked")
                continue

            root = ET.fromstring(r.text)
            videos = []

            for entry in root.findall("atom:entry", NS):
                vid_id    = entry.findtext("yt:videoId",     namespaces=NS) or ""
                title     = entry.findtext("atom:title",     namespaces=NS) or "(no title)"
                published = entry.findtext("atom:published", namespaces=NS) or ""
                link_el   = entry.find("atom:link", NS)
                url_link  = link_el.get("href", "") if link_el is not None else ""

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
                        "url":       url_link or f"https://www.youtube.com/watch?v={vid_id}",
                        "published": published,
                        "thumbnail": thumbnail,
                    })

            if videos:
                return videos

        except ET.ParseError as e:
            print(f"[YouTube] XML parse error for {channel_id}: {e}")
        except Exception as e:
            print(f"[YouTube] Fetch error for {channel_id}: {e}")

    print(f"[YouTube] All attempts failed for channel {channel_id}")
    return []


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
        print(f"[YouTube] Pre-loaded {len(videos)} videos for {channel['name']}")
    print(f"[YouTube] Total pre-loaded: {total} video IDs.")


def check_youtube() -> None:
    """
    Poll each channel's RSS feed for new videos.
    Broadcast an alert to all subscribers if a new video is found.
    """
    for game_key, channel in YOUTUBE_CHANNELS.items():
        videos = _fetch_feed(channel["channel_id"])

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
    return (datetime.now(timezone.utc) + timedelta(minutes=15)).strftime("%d %b %Y %H:%M UTC")
