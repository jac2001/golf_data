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

import time
import threading
from collections import deque
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

DG_BASE    = "https://feeds.datagolf.com"
DG_API_KEY = "299bc52db9d01131b23e9d299639"

_WINDOW_SECS  = 60          # sliding window duration
_MAX_REQUESTS = 40          # stay 5 under the hard 45 limit

# ── Rate limiter (thread-safe sliding window) ─────────────────────────────────

_lock      = threading.Lock()
_timestamps: deque[float] = deque()


def _throttle() -> None:
    """Block if needed to stay within _MAX_REQUESTS per _WINDOW_SECS."""
    with _lock:
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
) -> dict:
    """GET a DataGolf endpoint, injecting the API key and respecting rate limits.

    Args:
        endpoint: Path like "/field-updates" or "/preds/in-play".
        params:   Extra query parameters (do NOT include 'key').
        timeout:  Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    _throttle()

    all_params = {"key": DG_API_KEY, **(params or {})}
    url = f"{DG_BASE}{endpoint}"

    resp = requests.get(url, params=all_params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
