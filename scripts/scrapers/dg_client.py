"""
DataGolf API client with rate limiting.
========================================
Centralises all requests to feeds.datagolf.com.

Rate limit: 45 requests/minute (DG policy).
We stay safely under by enforcing a sliding-window cap of 40 req/min.

Usage:
    from scripts.scrapers.dg_client import dg_get

    data = dg_get("/field-updates", {"tour": "pga"})
"""

from __future__ import annotations

import os
import time
import threading
from collections import deque
from pathlib import Path

import requests

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────

DG_BASE    = "https://feeds.datagolf.com"
DG_API_KEY = os.environ.get("DG_API_KEY", "")

_WINDOW_SECS  = 60          # sliding window duration
_MAX_REQUESTS = 30          # conservative: DG bursts at ~30/min in practice
_MIN_INTERVAL = 1.5         # minimum seconds between any two requests

# ── Rate limiter (thread-safe sliding window) ─────────────────────────────────

_lock      = threading.Lock()
_timestamps: deque[float] = deque()


def _throttle() -> None:
    """Block if needed to stay within _MAX_REQUESTS per _WINDOW_SECS and _MIN_INTERVAL."""
    with _lock:
        now = time.monotonic()

        # Enforce minimum inter-request interval
        if _timestamps:
            elapsed = now - _timestamps[-1]
            if elapsed < _MIN_INTERVAL:
                time.sleep(_MIN_INTERVAL - elapsed)
                now = time.monotonic()

        # Drop timestamps outside the window
        while _timestamps and _timestamps[0] < now - _WINDOW_SECS:
            _timestamps.popleft()

        if len(_timestamps) >= _MAX_REQUESTS:
            # Sleep until the oldest request ages out of the window
            sleep_for = _WINDOW_SECS - (now - _timestamps[0]) + 0.05
            if sleep_for > 0:
                print(f"[dg_client] Rate limit approached — sleeping {sleep_for:.2f}s")
                time.sleep(sleep_for)
            # Re-prune after sleep
            now = time.monotonic()
            while _timestamps and _timestamps[0] < now - _WINDOW_SECS:
                _timestamps.popleft()

        _timestamps.append(time.monotonic())


# ── Public request function ───────────────────────────────────────────────────

def dg_get(
    endpoint: str,
    params: dict | None = None,
    timeout: int = 20,
    max_retries: int = 4,
) -> dict:
    """GET a DataGolf endpoint, injecting the API key and respecting rate limits.

    Args:
        endpoint:    Path like "/field-updates" or "/preds/in-play".
        params:      Extra query parameters (do NOT include 'key').
        timeout:     Request timeout in seconds.
        max_retries: Number of retry attempts on 429 responses.

    Returns:
        Parsed JSON response as a dict (empty dict if server returns no body).

    Raises:
        requests.HTTPError on non-2xx responses after retries exhausted.
    """
    all_params = {"key": DG_API_KEY, **(params or {})}
    url = f"{DG_BASE}{endpoint}"

    for attempt in range(max_retries + 1):
        _throttle()
        resp = requests.get(url, params=all_params, timeout=timeout)

        if resp.status_code == 429:
            wait = 65  # flat 65s — let the server's 60s window fully expire
            print(f"[dg_client] 429 received — waiting {wait}s before retry {attempt + 1}/{max_retries}")
            time.sleep(wait)
            continue

        resp.raise_for_status()

        # Empty body = endpoint returned no data (e.g. archive not available for year)
        if not resp.text.strip():
            return {}

        return resp.json()

    # All retries exhausted
    resp.raise_for_status()
    return {}
