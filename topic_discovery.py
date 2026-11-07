"""Trend-aware, repeat-safe topic discovery for pharmacy short videos.

Sources are deliberately public and optional. Google Trends RSS is the default;
YouTube Data API can be enabled with YOUTUBE_API_KEY for richer ranking.
"""
from __future__ import annotations
import hashlib, json, os, re, time
from pathlib import Path
from urllib.parse import quote
import requests
import xml.etree.ElementTree as ET

STATE_PATH = Path(os.getenv("TOPIC_STATE_FILE", "state/topic_history.json"))
DEFAULT_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=IR"

def normalize(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
    text = re.sub(r"[\u200c\u200f\u200eـ]", "", text)
    return re.sub(r"[^\w\sآ-ی]", " ", text, flags=re.UNICODE).strip()

def _load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"topics": {}}

def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)

def _rss_titles(url: str):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "pharma-agent-topic-discovery/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        return [e.text.strip() for e in root.findall(".//item/title") if e.text and e.text.strip()]
    except Exception as exc:
        print(f"trend source unavailable: {url} ({exc})")
        return []

def _youtube_titles(query: str):
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        return []
    try:
        data = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "part": "snippet", "q": query, "type": "video", "order": "viewCount",
            "publishedAfter": time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time()-14*86400)),
            "maxResults": 10, "regionCode": "IR", "relevanceLanguage": "fa", "key": key
        }, timeout=20).json()
        return [x.get("snippet", {}).get("title", "") for x in data.get("items", [])]
    except Exception as exc:
        print(f"YouTube trend source unavailable: {exc}")
        return []

def _is_pharma_related(title: str) -> bool:
    words = "دارو دارویی پزشکی سلامت قرص مکمل ویتامین دیابت فشار خون لاغری عوارض درمان pharmacy medicine drug health vitamin diabetes" 
    return any(w in normalize(title) for w in words.split())

def choose_topic(custom_topic: str, fallback_topics: list[str]):
    if custom_topic:
        return custom_topic.strip(), "telegram"
    state = _load_state()
    used = state.setdefault("topics", {})
    now = time.time()
    # Keep a 180-day memory; old topics may eventually return if trends revive.
    for key, ts in list(used.items()):
        if now - float(ts) > 180 * 86400:
            used.pop(key, None)
    urls = [u.strip() for u in os.getenv("TREND_RSS_URLS", DEFAULT_TRENDS_RSS).split(",") if u.strip()]
    candidates = []
    for url in urls:
        candidates.extend(_rss_titles(url))
    candidates.extend(_youtube_titles(os.getenv("TREND_QUERY", "دارو سلامت پزشکی")))
    candidates = [c for c in candidates if _is_pharma_related(c)]
    # Preserve source order (usually ranking order), then remove near duplicates.
    unique = []
    seen = set()
    for item in candidates + list(fallback_topics):
        key = normalize(item)
        if len(key) < 8 or key in seen or key in used:
            continue
        seen.add(key); unique.append(item.strip())
    topic = unique[0] if unique else fallback_topics[int(time.time()) % len(fallback_topics)]
    used[normalize(topic)] = now
    _save_state(state)
    return topic, ("google-trends/rss-or-youtube" if candidates else "fallback")
