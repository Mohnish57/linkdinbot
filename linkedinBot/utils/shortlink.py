"""Tiny URL shortener via tinyurl.com (no auth, no rate limits in practice).

Results are persisted to `linkedinBot/output/shortlinks.json` so the same long
URL always maps to the same short URL (no extra API calls).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output",
    "shortlinks.json",
)


def _load_cache() -> dict:
    if not os.path.exists(_CACHE_PATH):
        return {}
    try:
        with open(_CACHE_PATH) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    try:
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def shorten(url: str, force: bool = False) -> str:
    """Return a TinyURL-shortened version of `url`. Caches per long URL.

    If the request fails for any reason, returns the original `url` unchanged
    so the bot still has a usable link.
    """
    if not url or not url.startswith(("http://", "https://")):
        return url
    if "tinyurl.com" in url or len(url) <= 30:
        return url

    cache = _load_cache()
    if not force and url in cache:
        return cache[url]

    api = f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url, safe='')}"
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "linkedinbot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            short = resp.read().decode("utf-8").strip()
        if short.startswith("http"):
            cache[url] = short
            _save_cache(cache)
            return short
    except Exception as e:
        print(f"[shortlink] TinyURL failed for {url[:60]}…: {e}")
    return url
