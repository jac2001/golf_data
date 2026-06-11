"""
Golf Data API — FastAPI backend
================================
Serves the same data the Streamlit dashboard reads, as clean JSON endpoints.
The Next.js frontend calls these endpoints to render pages.

Run:
    cd /Users/jacklegnon/Desktop/golf_data
    uvicorn api.main:app --reload --port 8000

Endpoints:
    GET  /api/tournament          → current tournament info
    GET  /api/bets                → recommended bets (latest)
    GET  /api/odds/comparison     → multi-book odds table (for Value Bets page)
    GET  /api/predictions         → latest player predictions
    GET  /api/leaderboard         → live leaderboard
    POST /api/refresh-bets        → trigger recommend_bets.py
    POST /api/refresh-odds        → trigger refresh_odds.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from narwhals import col
from scipy import stats

# Load .env from project root (picks up ANTHROPIC_API_KEY, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── Project paths (same as dashboard.py) ────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from config import (  # noqa: E402
    SEASON, schedule_csv, usage_tracker_json, leaderboards_csv
)
_SCHED_CSV   = schedule_csv()
_TRACKER_JSON = usage_tracker_json()
_LB_CSV      = leaderboards_csv()
ODDS_DIR     = DATA_DIR / "odds"
DG_DIR       = DATA_DIR / "datagolf"
REASONS_CACHE_PATH = DATA_DIR / "betting_reasons_cache.json"

# ── DuckDB helper ────────────────────────────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
try:
    from db import get_conn as _get_db_conn
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

# ── Supabase helper ───────────────────────────────────────────────────────────
_sb_client = None

def _get_sb():
    """Return a cached Supabase client, or None if not configured."""
    global _sb_client
    if _sb_client is not None:
        return _sb_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _sb_client = create_client(url, key)
    except Exception:
        pass
    return _sb_client

app = FastAPI(title="Golf Data API", version="1.0.0")

# Allow the Next.js dev server (localhost:3000) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Chat rate limiter ─────────────────────────────────────────────────────────
# In-memory store: {ip: [unix_timestamps]}. Resets on server restart (fine for small use).
_rl_lock  = threading.Lock()
_rl_store: dict[str, list[float]] = defaultdict(list)
_RL_MAX    = 20     # requests allowed per window
_RL_WINDOW = 86400  # 24 hours in seconds

def _rate_limit_ok(ip: str) -> bool:
    now    = time.time()
    cutoff = now - _RL_WINDOW
    with _rl_lock:
        _rl_store[ip] = [t for t in _rl_store[ip] if t > cutoff]
        if len(_rl_store[ip]) >= _RL_MAX:
            return False
        _rl_store[ip].append(now)
        return True


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_odds(v) -> str:
    try:
        n = int(float(v))
        return f"+{n}" if n >= 0 else str(n)
    except Exception:
        return "—"


def _flip_to_last_first(n: str) -> str:
    s = str(n).strip()
    if "," in s:
        return s
    parts = s.split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) >= 2 else s


def _flip_to_first_last(n: str) -> str:
    s = str(n).strip()
    return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s


def _name_key(n: str) -> str:
    return " ".join(sorted(str(n).strip().lower().split()))


# ── Live alert engine ────────────────────────────────────────────────────────
#
# How it works:
#   1. get_inplay() calls _detect_alerts() only when fresh data arrives (not cache hits).
#   2. _detect_alerts() compares the new leaderboard to alerts_state.json (last-seen positions).
#   3. Events are deduplicated via a set of fired_keys so nothing fires twice.
#   4. Each new event is pushed to alerts_pending.json (for the web UI) AND sent
#      as a macOS desktop notification via osascript (so you hear it even off-screen).
#   5. GET /api/alerts drains the pending list so the web UI can show toasts.

_ALERTS_STATE_PATH   = PROJECT_ROOT / "logs" / "alerts_state.json"
_ALERTS_PENDING_PATH = PROJECT_ROOT / "logs" / "alerts_pending.json"
_SETTINGS_PATH       = DATA_DIR / "settings.json"
_ALERT_MAX_PENDING   = 50

# Default settings — written to settings.json on first run if the file is absent.
# Every key here is user-configurable via PATCH /api/settings.
_DEFAULT_SETTINGS: dict = {
    "alerts": {
        "mac_notifications": True,
        "web_toasts":        True,
        "events": {
            "my_pick_leads":    True,
            "my_pick_top5":     True,
            "my_pick_top10":    True,
            "my_pick_bigmove":  True,
            "leader_change":    True,
        },
        "bigmove_threshold": 5,     # positions gained to count as a "big move"
        "min_severity":      "low", # "low" | "normal" | "high"
    },
    "live": {
        "default_tab":      "leaderboard",
        "default_sg_round": "event_avg",
        "poll_interval_secs": 60,
    },
}


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge patch into base — only overwrites leaf values."""
    result = dict(base)
    for k, v in patch.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result



def _load_reasons_cache() -> dict:
    try:
        with open(REASONS_CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_reasons_cache(cache: dict) -> None:
    REASONS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REASONS_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def _get_live_player_stats(tid: str, player: str) -> dict:
    """Pull current-tournament live stats for a player: position, round scores, SG by round."""
    result: dict = {}
    tid_lower = tid.lower()

    def _norm(name: str) -> str:
        """Normalize to lowercase first+last tokens for fuzzy matching."""
        s = str(name).strip().lower()
        if "," in s:
            parts = s.split(",", 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return s

    player_norm = _norm(player)
    player_last = player.split(",")[0].strip().lower()

    # ── Leaderboard: position + round scores ──────────────────────────────────
    lb_path = DATA_DIR / "live" / f"leaderboard_{tid_lower}.csv"
    if lb_path.exists():
        try:
            lb = pd.read_csv(lb_path, dtype=str)
            # Leaderboard uses "First Last" format
            lb["_norm"] = lb["player_name"].apply(_norm)
            row = lb[lb["_norm"].str.contains(player_last, na=False)]
            if not row.empty:
                r = row.iloc[0]
                result["position"]    = r.get("position", "")
                result["total"]       = r.get("total", "")
                result["thru"]        = r.get("thru", "")
                result["status"]      = r.get("status", "")
                for rnd in ("R1", "R2", "R3", "R4"):
                    val = r.get(rnd, "")
                    if val and str(val).strip() not in ("", "-", "nan"):
                        result[rnd.lower()] = val
        except Exception:
            pass

    # ── DG R1 SG breakdown ────────────────────────────────────────────────────
    r1_path = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_1.csv"
    if r1_path.exists():
        try:
            r1 = pd.read_csv(r1_path, dtype=str)
            r1["_norm"] = r1["player_name"].apply(_norm)
            row = r1[r1["_norm"].str.contains(player_last, na=False)]
            if not row.empty:
                r = row.iloc[0]
                result["r1_sg_ott"]   = r.get("sg_ott", "")
                result["r1_sg_app"]   = r.get("sg_app", "")
                result["r1_sg_arg"]   = r.get("sg_arg", "")
                result["r1_sg_putt"]  = r.get("sg_putt", "")
                result["r1_sg_total"] = r.get("sg_total", "")
                result["r1_pos"]      = r.get("position", "")
        except Exception:
            pass

    # ── DG event-avg SG (full tournament so far) ──────────────────────────────
    avg_path = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_event_avg.csv"
    if avg_path.exists():
        try:
            avg = pd.read_csv(avg_path, dtype=str)
            avg["_norm"] = avg["player_name"].apply(_norm)
            row = avg[avg["_norm"].str.contains(player_last, na=False)]
            if not row.empty:
                r = row.iloc[0]
                result["tourn_sg_total"] = r.get("sg_total", "")
                result["tourn_sg_ott"]   = r.get("sg_ott", "")
                result["tourn_sg_app"]   = r.get("sg_app", "")
                result["tourn_sg_putt"]  = r.get("sg_putt", "")
        except Exception:
            pass

    return result


def _generate_bet_reason(player: str, market: str, stats: dict) -> str:
    """Call Claude Haiku to generate a 2-3 sentence betting reason grounded in golf form and results."""
    import anthropic

    def _f(v, default=0.0):
        try: return float(v)
        except (TypeError, ValueError): return default

    def _fmtv(v) -> str:
        """Return a clean string or empty string if missing."""
        if v is None or str(v).strip() in ("", "nan", "None", "N/A"): return ""
        try:
            f = float(v)
            return f"{f:+.2f}"
        except (TypeError, ValueError):
            return str(v).strip()

    def _fmtf(v, decimals=1) -> str:
        if v is None or str(v).strip() in ("", "nan", "None"): return "N/A"
        try: return f"{float(v):.{decimals}f}"
        except (TypeError, ValueError): return str(v).strip()

    odds       = stats.get("odds_american", "")
    world_rank = _fmtf(stats.get("world_rank"), 0)
    opponent   = stats.get("opponent", "")
    market_lbl = {
        "outright": "outright winner", "top5": "Top 5", "top10": "Top 10",
        "top20": "Top 20", "make_cut": "make the cut",
    }.get(market, market.replace("_", " "))

    # ── Season SG ─────────────────────────────────────────────────────────────
    sg_total = _fmtv(stats.get("sg_total"))
    sg_ott   = _fmtv(stats.get("sg_ott"))
    sg_app   = _fmtv(stats.get("sg_app"))
    sg_putt  = _fmtv(stats.get("sg_putt"))
    sg_line  = ""
    if sg_total:
        parts = [f"SG: {sg_total} total"]
        if sg_ott:  parts.append(f"driving {sg_ott}")
        if sg_app:  parts.append(f"approach {sg_app}")
        if sg_putt: parts.append(f"putting {sg_putt}")
        sg_line = ", ".join(parts) + " (vs field avg)"

    # ── Recent form ───────────────────────────────────────────────────────────
    scoring_avg  = _fmtf(stats.get("recent_scoring_avg"), 1)
    top10s       = _fmtf(stats.get("recent_top10s"),      0)
    birdie_avg   = _fmtf(stats.get("recent_birdie_avg"),  1)
    bogey_per100 = _fmtf(stats.get("recent_bogey_avg"),   1)
    cuts_made    = _fmtf(stats.get("recent_cuts_made"),   0)
    gir          = _fmtf(stats.get("recent_gir_pct"),     1)
    scrambling   = _fmtf(stats.get("recent_scrambling"),  1)
    last_pos     = stats.get("last_start_position", "")
    momentum     = str(stats.get("momentum_trend", "") or "").upper()
    missed_cut   = stats.get("missed_cut_last_start")

    form_parts = []
    if scoring_avg != "N/A":  form_parts.append(f"scoring avg {scoring_avg}")
    if top10s     != "N/A":   form_parts.append(f"{top10s} top-10s in recent starts")
    if birdie_avg != "N/A":   form_parts.append(f"{birdie_avg} birdies/round")
    if bogey_per100 != "N/A": form_parts.append(f"{bogey_per100} bogeys per 100 holes")
    if cuts_made  != "N/A":   form_parts.append(f"{cuts_made} of last 5 cuts made")
    form_line = "; ".join(form_parts) if form_parts else ""

    last_start_note = ""
    if last_pos and str(last_pos).strip() not in ("", "nan"):
        try:
            pos = int(float(last_pos))
            last_start_note = f"Last start: T{pos}"
        except (ValueError, TypeError):
            pass
    if missed_cut and str(missed_cut) == "1":
        last_start_note = "Last start: missed cut"
    if momentum in ("HOT", "COLD"):
        last_start_note += f" · momentum {momentum.lower()}" if last_start_note else f"Momentum: {momentum.lower()}"

    # ── Course history ────────────────────────────────────────────────────────
    c_starts   = _fmtf(stats.get("course_starts"),      0)
    c_best     = stats.get("course_best_finish")
    c_avg_par  = _fmtf(stats.get("course_avg_to_par"),  1)
    c_top10r   = _fmtf(stats.get("course_top10_rate"),  0)  # fraction → %
    c_sg       = _fmtv(stats.get("course_sg"))
    course_line = ""
    if c_starts and c_starts != "N/A" and float(c_starts) > 0:
        cp = [f"{c_starts} starts here"]
        if c_best and str(c_best).strip() not in ("", "nan"):
            try: cp.append(f"best finish T{int(float(c_best))}")
            except (ValueError, TypeError): pass
        if c_avg_par != "N/A":
            try:
                avg = float(stats.get("course_avg_to_par", 0))
                cp.append(f"avg {avg:+.1f} per tournament")
            except (TypeError, ValueError): pass
        if c_top10r != "N/A":
            try:
                pct = int(float(stats.get("course_top10_rate", 0)) * 100)
                if pct > 0: cp.append(f"{pct}% top-10 rate")
            except (TypeError, ValueError): pass
        if c_sg: cp.append(f"SG {c_sg} vs field at this track")
        course_line = "; ".join(cp)
    elif c_sg:
        course_line = f"Course SG estimate: {c_sg} vs field"

    # ── Live tournament ───────────────────────────────────────────────────────
    position = stats.get("position", "")
    total    = stats.get("total", "")
    thru     = stats.get("thru", "")
    r1, r2, r3 = stats.get("r1",""), stats.get("r2",""), stats.get("r3","")
    t_sg     = _fmtv(stats.get("tourn_sg_total"))
    t_sg_app = _fmtv(stats.get("tourn_sg_app"))

    live_parts = []
    if position:
        ln = f"{position} ({total})"
        if thru and str(thru).strip() not in ("", "nan"): ln += f" thru {thru}"
        live_parts.append(ln)
    rnd_scores = [f"R{i+1}={s}" for i,s in enumerate([r1,r2,r3]) if s and str(s).strip() not in ("","-","nan")]
    if rnd_scores: live_parts.append(", ".join(rnd_scores))
    if t_sg:       live_parts.append(f"tournament SG {t_sg}")
    if t_sg_app:   live_parts.append(f"approach SG {t_sg_app} this week")
    live_line = " · ".join(live_parts) if live_parts else ""

    # ── Price note ────────────────────────────────────────────────────────────
    edge       = _f(stats.get("edge_pts"))
    model_prob = round(_f(stats.get("model_prob")) * 100, 1)
    book_prob  = round(_f(stats.get("book_prob"))  * 100, 1)
    price_note = f"{odds}" + (f" (model {model_prob}% vs book {book_prob}%)" if model_prob else "")

    # ── Build prompt ──────────────────────────────────────────────────────────
    is_h2h = market.startswith("h2h")

    if is_h2h and opponent:
        # Opponent data
        opp_rank  = _fmtf(stats.get("opp_world_rank"), 0)
        opp_sg    = _fmtv(stats.get("opp_sg_total"))
        opp_app   = _fmtv(stats.get("opp_sg_app"))
        opp_score = _fmtf(stats.get("opp_recent_scoring_avg"), 1)
        opp_t10s  = _fmtf(stats.get("opp_recent_top10s"), 0)
        opp_pos   = stats.get("opp_position","")
        opp_total = stats.get("opp_total","")
        opp_r1    = stats.get("opp_r1","")
        opp_t_sg  = _fmtv(stats.get("opp_tourn_sg_total"))
        opp_mom   = str(stats.get("opp_momentum_trend","") or "").upper()
        opp_last  = _fmtf(stats.get("opp_last_start_position",""), 0)

        p_live, o_live = [], []
        if position: p_live.append(f"{position} ({total})" + (f" thru {thru}" if thru and str(thru).strip() not in ("","nan") else ""))
        if rnd_scores: p_live.append(", ".join(rnd_scores))
        if t_sg: p_live.append(f"SG {t_sg} this week")
        if opp_pos: o_live.append(f"{opp_pos} ({opp_total})")
        if opp_r1 and str(opp_r1).strip() not in ("","-","nan"): o_live.append(f"R1 {opp_r1}")
        if opp_t_sg: o_live.append(f"SG {opp_t_sg} this week")

        prompt = f"""You are a sharp golf analyst writing for fans who follow the tour. Write 2-3 natural sentences explaining why {player} beats {opponent} in this round matchup. Lead with their current game and form — don't open with the odds.

Matchup: {player} vs {opponent} | {market_lbl} | {price_note}

{player} (World #{world_rank}):
- Season: {sg_line or "N/A"}
- Recent: {form_line or "N/A"}{(chr(10) + "- " + last_start_note) if last_start_note else ""}
- This week: {" · ".join(p_live) if p_live else "not yet started"}

{opponent} (World #{opp_rank}):
- Season SG: {opp_sg or "N/A"} total, approach {opp_app or "N/A"}
- Recent: scoring avg {opp_score}, {opp_t10s} top-10s{(", " + opp_mom.lower() + " form") if opp_mom in ("HOT","COLD") else ""}{(", last start T" + opp_last) if opp_last != "N/A" else ""}
- This week: {" · ".join(o_live) if o_live else "not yet started"}

Explain why {player} has the edge. Cite specific stats. Sound like a knowledgeable fan, not a quant."""

    else:
        sections = []
        if sg_line:      sections.append(f"Season: {sg_line}")
        if form_line:    sections.append(f"Recent form: {form_line}")
        if last_start_note: sections.append(last_start_note)
        if course_line:  sections.append(f"Course history: {course_line}")
        if live_line:    sections.append(f"This week: {live_line}")

        context = "\n".join(f"- {s}" for s in sections) if sections else "No detailed stats available."

        market_focus = {
            "make_cut": "Focus on their consistency, cut-making record, and course history.",
            "outright": "Focus on their elite form and what makes them a genuine winner this week.",
            "top5":     "Focus on their ceiling — recent high finishes and course fit.",
            "top10":    "Focus on their consistency and ability to contend.",
            "top20":    "Focus on their baseline quality and recent form.",
        }.get(market, "")

        prompt = f"""You are a sharp golf analyst writing for fans who follow the tour. Write 2-3 natural sentences explaining why {player} is worth backing for {market_lbl} at {odds}. Lead with their game and form — don't open with the odds or model numbers.

{player} (World #{world_rank}):
{context}

Price: {price_note}

{market_focus} Sound like a knowledgeable fan, not a quant. Use specific numbers from the data above."""

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()





def _load_settings() -> dict:
    try:
        with open(_SETTINGS_PATH) as f:
            stored = json.load(f)
        return _deep_merge(_DEFAULT_SETTINGS, stored)
    except Exception:
        return dict(_DEFAULT_SETTINGS)


def _save_settings(s: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        json.dump(s, f, indent=2)


@app.get("/api/settings")
def get_settings() -> dict:
    return _load_settings()


@app.patch("/api/settings")
def patch_settings(body: dict) -> dict:
    """
    Deep-merge body into the current settings and save.
    Only send what changed — e.g. {"alerts": {"mac_notifications": false}}.
    """
    current = _load_settings()
    updated = _deep_merge(current, body)
    _save_settings(updated)
    return updated

def _parse_pos_int(s) -> int | None:
    """'T2' → 2, '1' → 1, 'CUT' → 999, None → None."""
    if s is None:
        return None
    raw = str(s).strip().upper().lstrip("T")
    if raw in ("CUT", "WD", "DQ", "MDF", ""):
        return 999
    try:
        return int(raw)
    except ValueError:
        return None


def _notify_mac(title: str, body: str, settings: dict | None = None) -> None:
    """Fire a macOS Notification Center banner — non-blocking, best-effort.
    Skipped if alerts.mac_notifications is False in settings."""
    cfg = (settings or _load_settings()).get("alerts", {})
    if not cfg.get("mac_notifications", True):
        return
    try:
        subprocess.Popen(
            ["osascript", "-e",
             f'display notification "{body}" with title "{title}" subtitle "Golf"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _load_alert_state() -> dict:
    try:
        with open(_ALERTS_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_alert_state(state: dict) -> None:
    _ALERTS_STATE_PATH.parent.mkdir(exist_ok=True)
    with open(_ALERTS_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _load_pending() -> list:
    try:
        with open(_ALERTS_PENDING_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _save_pending(alerts: list) -> None:
    _ALERTS_PENDING_PATH.parent.mkdir(exist_ok=True)
    with open(_ALERTS_PENDING_PATH, "w") as f:
        json.dump(alerts[-_ALERT_MAX_PENDING:], f, indent=2)


_SEV_ORDER = {"low": 0, "normal": 1, "high": 2}

def _push_alert(state: dict, pending: list,
                key: str, title: str, body: str,
                atype: str, severity: str = "normal",
                settings: dict | None = None) -> None:
    """
    Add an alert if its key hasn't been fired yet this tournament.

    Settings gates (all checked before firing):
      alerts.events.<atype>    — event type must be enabled
      alerts.min_severity      — severity must meet the minimum
      alerts.web_toasts        — controls whether the pending list is appended to
      alerts.mac_notifications — controls whether osascript fires (checked in _notify_mac)
    """
    cfg = (settings or _load_settings()).get("alerts", {})

    # Gate 1: event type enabled
    # atype may be "my_pick_T5", "my_pick_leads", "leader_change", etc.
    # Strip "my_pick_" prefix to get the base event key used in settings
    base_event = atype.replace("my_pick_", "") if atype.startswith("my_pick_") else atype
    events_cfg = cfg.get("events", {})
    event_key  = f"my_pick_{base_event}" if f"my_pick_{base_event}" in events_cfg else base_event
    if not events_cfg.get(event_key, True):
        return

    # Gate 2: severity threshold
    min_sev = cfg.get("min_severity", "low")
    if _SEV_ORDER.get(severity, 0) < _SEV_ORDER.get(min_sev, 0):
        return

    # Gate 3: deduplication
    fired: list = state.setdefault("fired_keys", [])
    if key in fired:
        return
    fired.append(key)

    # Gate 4: web toasts
    if cfg.get("web_toasts", True):
        pending.append({
            "id":       key,
            "type":     atype,
            "title":    title,
            "body":     body,
            "ts":       datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "severity": severity,
            "read":     False,
        })

    # macOS notification (gated inside _notify_mac)
    _notify_mac(title, body, settings)


def _my_lineup_full_names(rows: list[dict], tid: str) -> list[str]:
    """
    Return the full names (as they appear in the leaderboard) for this week's picks.
    Reads usage_tracker_2026.json, finds the right week, then fuzzy-matches
    short tracker names ('Scheffler') to full leaderboard names ('Scottie Scheffler').
    """
    tracker_path = _TRACKER_JSON
    sched_path   = _SCHED_CSV
    try:
        with open(tracker_path) as f:
            tracker = json.load(f)
        sched = pd.read_csv(sched_path, dtype=str)
        row = sched[sched["tournament_id"].str.upper() == tid.upper()]
        if row.empty:
            return []
        tourney_name = row.iloc[0]["tournament_name"]

        short_names: list[str] = []
        for wk, entry in tracker.get("weekly_lineups", {}).items():
            if entry.get("tournament", "") == tourney_name and entry.get("lineup"):
                short_names = entry["lineup"]
                break

        if not short_names:
            return []

        # Build last-name lookup from the live leaderboard rows
        # rows[i]["player_name"] is already "First Last"
        full_names = [r["player_name"] for r in rows]
        last_to_full: dict[str, list[str]] = {}
        for full in full_names:
            parts = full.lower().split()
            if parts:
                last_to_full.setdefault(parts[-1], []).append(full)

        results: list[str] = []
        for short in short_names:
            tokens = short.strip().lower().split()
            if not tokens:
                continue
            last = tokens[-1]
            has_initial = len(tokens) == 2 and len(tokens[0]) == 1
            candidates = last_to_full.get(last, [])
            if has_initial:
                candidates = [c for c in candidates if c.lower().split()[0][0] == tokens[0]]
            if len(candidates) == 1:
                results.append(candidates[0])
            elif len(candidates) > 1:
                results.append(candidates[0])   # best guess on tie
        return results
    except Exception:
        return []


def _detect_alerts(rows: list[dict], tid: str, current_round) -> None:
    """
    Compare current leaderboard to the last-seen state and push alerts for notable events.
    Called once per fresh DG fetch (≈every 60s during live play).
    Reads settings once per call so changes take effect on the next poll.
    """
    if not rows or not tid:
        return

    settings = _load_settings()
    state    = _load_alert_state()
    pending  = _load_pending()

    if state.get("tid") != tid:
        state = {"tid": tid, "last_positions": {}, "last_leader": None, "fired_keys": []}

    last_positions: dict = state.setdefault("last_positions", {})
    rnd            = str(current_round or "")
    is_first_run   = not last_positions
    bigmove_thresh = settings.get("alerts", {}).get("bigmove_threshold", 5)
    my_picks       = _my_lineup_full_names(rows, tid)

    new_positions: dict = {}
    for r in rows:
        name    = r.get("player_name", "")
        pos_int = _parse_pos_int(r.get("position"))
        total   = r.get("total") or "E"
        thru    = r.get("thru") or ""
        if pos_int is None:
            continue

        new_positions[name] = {"pos": pos_int, "total": total, "thru": thru}

        if is_first_run or name not in last_positions:
            continue

        prev_pos   = last_positions[name].get("pos", 999)
        is_my_pick = name in my_picks

        # ── Threshold crossings ───────────────────────────────────────────────
        for threshold, label, sev in [(1, "leads", "high"), (5, "T5", "high"), (10, "T10", "normal")]:
            if pos_int <= threshold < prev_pos:
                key   = f"{label}_{name}_{tid}_r{rnd}"
                title = f"{'Your pick: ' if is_my_pick else ''}{name} {label}"
                body  = f"{name} is {r.get('position')} at {total} (thru {thru})"
                _push_alert(state, pending, key, title, body,
                            atype=f"{'my_pick_' if is_my_pick else ''}{label}",
                            severity=sev if is_my_pick else "low",
                            settings=settings)

        # ── Big move (picks only) ─────────────────────────────────────────────
        if is_my_pick and pos_int < prev_pos and (prev_pos - pos_int) >= bigmove_thresh:
            key = f"bigmove_{name}_{tid}_r{rnd}_pos{pos_int}"
            _push_alert(state, pending, key,
                        title=f"{name} moving fast",
                        body=f"Gained {prev_pos - pos_int} spots → {r.get('position')} at {total}",
                        atype="my_pick_bigmove", severity="normal", settings=settings)

    # ── Leader change ─────────────────────────────────────────────────────────
    if rows and not is_first_run:
        new_leader = rows[0]["player_name"]
        old_leader = state.get("last_leader")
        if old_leader and new_leader != old_leader:
            key = f"leader_{new_leader}_{tid}_r{rnd}"
            _push_alert(state, pending, key,
                        title=f"New leader: {new_leader}",
                        body=f"{new_leader} takes the lead at {rows[0].get('total', 'E')}",
                        atype="leader_change", severity="normal", settings=settings)

    state["last_positions"] = {**last_positions, **new_positions}
    state["last_leader"]    = rows[0]["player_name"] if rows else state.get("last_leader")
    _save_alert_state(state)
    _save_pending(pending)



@app.get("/api/bets/reason")
def get_bet_reason(player: str, market: str, opponent: str = "") -> dict:
    tid = _get_tournament_id()
    key = f"{player}|{market}" + (f"|{opponent}" if opponent else "")
    cache = _load_reasons_cache()

    if cache.get(tid, {}).get(key):
        return {"reason": cache[tid][key], "cached": True}

    stats: dict = {}

    # ── DB queries ────────────────────────────────────────────────────────────
    try:
        with _get_db_conn() as con:
            # Bet stats: most recent entry for this player+market in this tournament
            bet_row = con.execute("""
                SELECT edge_pts, model_prob, book_prob, odds_american
                FROM recommended_bets_log
                WHERE tournament_id = ?
                  AND LOWER(player_name) = LOWER(?)
                  AND LOWER(market) = LOWER(?)
                ORDER BY recommended_at DESC
                LIMIT 1
            """, [tid, player, market]).fetchone()
            if bet_row:
                stats["edge_pts"]      = bet_row[0]
                stats["model_prob"]    = bet_row[1]
                stats["book_prob"]     = bet_row[2]
                stats["odds_american"] = bet_row[3]

            # World rank from the players table (more reliable than predictions CSV)
            rank_row = con.execute("""
                SELECT world_rank FROM players
                WHERE LOWER(player_name) = LOWER(?)
                ORDER BY updated_at DESC
                LIMIT 1
            """, [player]).fetchone()
            if rank_row:
                stats["world_rank"] = rank_row[0]

            # SG total from live_stats event-avg bucket (round_num = 0)
            sg_row = con.execute("""
                SELECT sg_total FROM live_stats
                WHERE tournament_id = ?
                  AND round_num = 0
                  AND LOWER(player_name) = LOWER(?)
                LIMIT 1
            """, [tid, player]).fetchone()
            if sg_row:
                stats["sg_total"] = sg_row[0]

    except Exception:
        pass  # DB failures are non-fatal; CSV fallbacks below

    # ── CSV fallbacks ─────────────────────────────────────────────────────────
    # Bet stats: current tournament may not be in the DB yet — read the CSV
    if "edge_pts" not in stats:
        bets_path = ODDS_DIR / "recommended_bets_latest.csv"
        if bets_path.exists():
            bets_df = pd.read_csv(bets_path, dtype=str)
            match = bets_df[
                (bets_df["player_name"].str.lower() == player.lower()) &
                (bets_df["market"].str.lower()       == market.lower())
            ]
            if not match.empty:
                r = match.iloc[0]
                stats["edge_pts"]      = _safe(r.get("edge_pts"))
                stats["model_prob"]    = _safe(r.get("model_prob"))
                stats["book_prob"]     = _safe(r.get("book_prob"))
                stats["odds_american"] = _safe(r.get("odds_american"))

    # Predictions CSV: rich form + course history pull
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if preds_path.exists():
        preds_df = pd.read_csv(preds_path, dtype=str)
        last = player.split()[-1].lower()
        prow = preds_df[preds_df["player_name"].str.lower().str.contains(last, na=False)]
        if not prow.empty:
            p = prow.iloc[0]
            # Fallbacks for DB-sourced fields
            if "sg_total"    not in stats: stats["sg_total"]    = _safe(p.get("season_sg_total"))
            if "world_rank"  not in stats: stats["world_rank"]  = _safe(p.get("world_rank"))
            # Season SG by category
            stats["sg_ott"]  = _safe(p.get("season_sg_ott"))
            stats["sg_app"]  = _safe(p.get("season_sg_app"))
            stats["sg_putt"] = _safe(p.get("season_sg_putt"))
            # Form / recent results
            stats["recent_scoring_avg"]   = _safe(p.get("recent_scoring_avg"))
            stats["recent_top10s"]        = _safe(p.get("recent_top10s"))
            stats["recent_birdie_avg"]    = _safe(p.get("recent_birdie_avg"))
            stats["recent_bogey_avg"]     = _safe(p.get("recent_bogey_avg"))
            stats["recent_cuts_made"]     = _safe(p.get("recent_cuts_made"))
            stats["recent_gir_pct"]       = _safe(p.get("recent_gir_pct"))
            stats["recent_scrambling"]    = _safe(p.get("recent_scrambling"))
            stats["last_start_position"]  = _safe(p.get("last_start_position"))
            stats["missed_cut_last_start"]= _safe(p.get("missed_cut_last_start"))
            stats["momentum_trend"]       = _safe(p.get("momentum_trend"))
            stats["form_trend"]           = _safe(p.get("recent_sg_trend"))
            # Course history
            stats["course_sg"]            = _safe(p.get("course_sg_total_avg"))
            stats["course_starts"]        = _safe(p.get("course_starts"))
            stats["course_best_finish"]   = _safe(p.get("course_best_finish"))
            stats["course_avg_to_par"]    = _safe(p.get("course_avg_to_par"))
            stats["course_top10_rate"]    = _safe(p.get("course_top_10_rate"))
            stats["course_made_cut_rate"] = _safe(p.get("course_made_cut_rate"))
            # Key traditional stats
            stats["driving_dist"]         = _safe(p.get("driving_dist_val"))
            stats["gir_pct"]              = _safe(p.get("gir_pct_val"))

    # ── Live tournament stats for this player ────────────────────────────────
    live = _get_live_player_stats(tid, player)
    stats.update(live)

    # ── Opponent stats for H2H markets ───────────────────────────────────────
    if opponent and market.startswith("h2h"):
        stats["opponent"] = opponent
        opp_last = opponent.split(",")[0].strip().lower()
        # Live tournament stats for opponent
        opp_live = _get_live_player_stats(tid, opponent)
        for k, v in opp_live.items():
            stats[f"opp_{k}"] = v
        # World rank + season SG from DB/CSV
        try:
            with _get_db_conn() as con:
                opp_rank_row = con.execute(
                    "SELECT world_rank FROM players WHERE LOWER(player_name) LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    [f"%{opp_last}%"]
                ).fetchone()
                if opp_rank_row:
                    stats["opp_world_rank"] = opp_rank_row[0]
                opp_sg_row = con.execute(
                    "SELECT sg_total FROM live_stats WHERE tournament_id = ? AND round_num = 0 AND LOWER(player_name) LIKE ? LIMIT 1",
                    [tid, f"%{opp_last}%"]
                ).fetchone()
                if opp_sg_row:
                    stats["opp_sg_total"] = opp_sg_row[0]
        except Exception:
            pass
        # Rich form pull for opponent from predictions CSV
        if preds_path.exists():
            try:
                preds_df = pd.read_csv(preds_path, dtype=str)
                orow = preds_df[preds_df["player_name"].str.lower().str.contains(opp_last, na=False)]
                if not orow.empty:
                    op = orow.iloc[0]
                    if "opp_sg_total"    not in stats: stats["opp_sg_total"]    = _safe(op.get("season_sg_total"))
                    if "opp_world_rank"  not in stats: stats["opp_world_rank"]  = _safe(op.get("world_rank"))
                    stats["opp_sg_app"]             = _safe(op.get("season_sg_app"))
                    stats["opp_sg_putt"]            = _safe(op.get("season_sg_putt"))
                    stats["opp_recent_scoring_avg"] = _safe(op.get("recent_scoring_avg"))
                    stats["opp_recent_top10s"]      = _safe(op.get("recent_top10s"))
                    stats["opp_last_start_position"]= _safe(op.get("last_start_position"))
                    stats["opp_momentum_trend"]     = _safe(op.get("momentum_trend"))
            except Exception:
                pass

    # ── Generate + cache ──────────────────────────────────────────────────────
    try:
        reason = _generate_bet_reason(player, market, stats)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude error: {e}")

    cache.setdefault(tid, {})[key] = reason
    _save_reasons_cache(cache)
    return {"reason": reason, "cached": False}





# ── /api/alerts endpoint ─────────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts(mark_read: bool = True) -> dict:
    """
    Return all pending alerts. If mark_read=true (default), marks them read so
    the next poll only returns new alerts.
    """
    alerts = _load_pending()
    unread = [a for a in alerts if not a.get("read")]
    if mark_read and unread:
        for a in alerts:
            a["read"] = True
        _save_pending(alerts)
    return {"alerts": unread, "total_unread": len(unread)}


def _safe(v, default=None):
    """Convert NaN / None / numpy scalars to a JSON-safe Python native value."""
    if v is None:
        return default
    # pandas NA / numpy nan/inf
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return default
    # numpy scalar → Python native
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of dicts, replacing NaN with None."""
    return [
        {k: _safe(v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _get_tournament_name(tid: str) -> str:
    """Look up the human-readable name for a tournament ID from the schedule CSV."""
    sched_path = _SCHED_CSV
    if not sched_path.exists() or not tid:
        return ""
    try:
        sched = pd.read_csv(sched_path)
        row = sched[sched["tournament_id"].astype(str).str.upper() == tid.upper()]
        return str(row.iloc[0].get("tournament_name", "")).strip() if not row.empty else ""
    except Exception:
        return ""


def _get_tournament_id() -> str:
    """Find the current tournament ID from the latest recommendations file."""
    # Try latest predictions file first
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        try:
            df = pd.read_csv(pred_path, nrows=1)
            if "tournament_id" in df.columns:
                return str(df.iloc[0]["tournament_id"]).strip().upper()
        except Exception:
            pass

    # Fall back to most recent recommended bets file
    files = sorted(ODDS_DIR.glob("recommended_bets_R*.csv"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        m = f.stem.replace("recommended_bets_", "")
        if m.startswith("R"):
            return m.upper()
    return ""


def _load_bets(tid: str) -> pd.DataFrame:
    """Load the most recently modified bets file for this tournament."""
    live_path = ODDS_DIR / f"recommended_bets_live_{tid}.csv"
    std_path  = ODDS_DIR / f"recommended_bets_{tid}.csv"
    candidates = sorted(
        [p for p in [live_path, std_path] if p.exists()],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not candidates:
        return pd.DataFrame()
    try:
        df = pd.read_csv(candidates[0])
        # Drop rows with no identifiable player (content cards score as NaN player)
        if "player_name" in df.columns:
            df = df[df["player_name"].notna() & (df["player_name"].astype(str).str.lower() != "nan")]
        # Drop content_card market — DK branded parlays, not individual player bets
        if "market" in df.columns:
            df = df[df["market"].astype(str) != "content_card"]
        return df
    except Exception:
        return pd.DataFrame()


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/api/tournament")
def get_tournament() -> dict:
    """Current tournament info: name, id, phase, week."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament found")

    result: dict[str, Any] = {"tournament_id": tid}

    # Pull name + week from Supabase → fallback to CSV
    _loaded_sched = False
    sb = _get_sb()
    if sb:
        try:
            rows = sb.table("tournaments").select("*").eq("tournament_id", tid).execute().data
            if rows:
                r = rows[0]
                result["name"]       = str(r.get("tournament_name", ""))
                result["start_date"] = str(r.get("start_date", ""))
                result["end_date"]   = str(r.get("end_date", ""))
                result["purse"]      = r.get("purse")
                _loaded_sched = True
        except Exception:
            pass
    if not _loaded_sched:
        sched_path = _SCHED_CSV
        if sched_path.exists():
            try:
                sched = pd.read_csv(sched_path)
                row = sched[sched["tournament_id"].astype(str).str.upper() == tid]
                if not row.empty:
                    result["name"]       = str(row.iloc[0].get("tournament_name", ""))
                    result["start_date"] = str(row.iloc[0].get("start_date", ""))
                    result["end_date"]   = str(row.iloc[0].get("end_date", ""))
                    result["purse"]      = _safe(row.iloc[0].get("purse"))
            except Exception:
                pass

    # Detect phase from live meta
    meta_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}_meta.json"
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            result["current_round"] = _safe(meta.get("current_round"))
            result["round_status"]  = str(meta.get("round_status", ""))
            result["leader_score"]  = _safe(meta.get("leader_score"))
            result["leader_name"]   = str(meta.get("leader_name", ""))
        except Exception:
            pass

    # Add smart phase (overrides meta current_round when R1 is done but meta hasn't flipped)
    try:
        from scripts.models.recommend_bets import get_tournament_phase as _gtp
        _phase = _gtp(tid)
        result["phase"] = _phase
        # Derive display round from phase so the UI shows "Round 2" even before
        # the PGA Tour API updates current_round in the meta file.
        _phase_round = {"pre": None, "r1": 1, "r2": 2, "r2_postcut": 2, "r3": 3, "r4": 4, "post": None}
        _pr = _phase_round.get(_phase)
        if _pr is not None:
            result["current_round"] = _pr
    except Exception:
        pass

    result["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return result


@app.get("/api/bets/lines")
def get_bet_lines(player: str, market: str) -> dict:
    """
    All book odds for a given player + market, sorted best→worst.
    Used for line shopping on the betting page.
    Only covers outright markets available in the DG JSON
    (win / top_5 / top_10 / top_20 / make_cut).
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    # Map frontend market names → DG JSON keys
    _mkt_map = {
        "outright": "outrights_win",
        "win":      "outrights_win",
        "top5":     "outrights_top_5",
        "top10":    "outrights_top_10",
        "top20":    "outrights_top_20",
        "make_cut": "outrights_make_cut",
    }
    dg_key = _mkt_map.get(market.lower())
    if not dg_key:
        raise HTTPException(status_code=400, detail=f"Line shopping not available for market: {market}")

    dg_path = DG_DIR / f"dg_odds_{tid}.json"
    if not dg_path.exists():
        raise HTTPException(status_code=404, detail="DG odds file not found")

    with open(dg_path) as f:
        dg_raw = json.load(f)

    market_data = dg_raw.get(dg_key, {})
    odds_list   = market_data.get("odds", [])
    if not isinstance(odds_list, list):
        raise HTTPException(status_code=404, detail="No odds available for this market")

    # Find the player (case-insensitive, last-name fallback)
    player_last = player.split()[-1].lower()
    player_row  = None
    for row in odds_list:
        name = row.get("player_name", "")
        # DG uses "Last, First" format
        if name.lower() == player.lower():
            player_row = row; break
        name_norm = name.replace(",", "").strip().lower()
        if player.replace(",", "").strip().lower() == name_norm:
            player_row = row; break
        # last-name fallback
        if name.split(",")[0].strip().lower() == player_last:
            player_row = row; break

    if player_row is None:
        raise HTTPException(status_code=404, detail=f"Player not found: {player}")

    # Get model prob from bets CSV for edge calculation
    model_prob: float | None = None
    bets_path = ODDS_DIR / "recommended_bets_latest.csv"
    if bets_path.exists():
        try:
            bdf = pd.read_csv(bets_path, dtype=str)
            match = bdf[
                (bdf["player_name"].str.lower() == player.lower()) &
                (bdf["market"].str.lower()       == market.lower())
            ]
            if not match.empty:
                model_prob = float(match.iloc[0]["model_prob"])
        except Exception:
            pass

    def _to_prob(odds_str) -> float | None:
        """American odds string → implied probability."""
        try:
            o = float(str(odds_str).replace("+", ""))
            return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
        except Exception:
            return None

    books_offering = market_data.get("books_offering", [])
    lines = []
    for book in books_offering:
        val = player_row.get(book)
        if not val or str(val).strip().lower() in ("null", ""):
            continue
        prob = _to_prob(val)
        if prob is None:
            continue
        # Remove vig: simple halving approximation (exact only works for 2-way;
        # good enough as a display metric for sorting purposes)
        edge_pp = round((model_prob - prob) * 100, 2) if model_prob is not None else None
        lines.append({
            "book":         book,
            "odds_american": str(val),
            "implied_prob": round(prob, 4),
            "edge_pp":      edge_pp,
        })

    # Also include DG model line for reference
    dg_obj = player_row.get("datagolf")
    if isinstance(dg_obj, dict):
        dg_odds = dg_obj.get("baseline_history_fit") or dg_obj.get("baseline")
        if dg_odds:
            prob = _to_prob(dg_odds)
            if prob:
                lines.append({
                    "book":         "datagolf (model)",
                    "odds_american": str(dg_odds),
                    "implied_prob": round(prob, 4),
                    "edge_pp":      None,
                })

    # Sort by best odds (highest positive number first, then lowest negative)
    def _sort_key(line):
        try:
            o = float(str(line["odds_american"]).replace("+", ""))
            return -o  # higher positive = better → more negative sort key
        except Exception:
            return 9999

    lines.sort(key=_sort_key)

    return {
        "player":      player,
        "market":      market,
        "model_prob":  model_prob,
        "best_odds":   lines[0]["odds_american"] if lines else None,
        "best_book":   lines[0]["book"]          if lines else None,
        "lines":       lines,
        "last_updated": market_data.get("last_updated"),
    }


def _build_leaderboard_lookup(tid: str) -> dict[str, dict]:
    """Build a last-name-keyed lookup of live position/score from the leaderboard CSV."""
    lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    if not lb_path.exists():
        return {}
    try:
        lb = pd.read_csv(lb_path, dtype=str)
        lookup: dict[str, dict] = {}
        for _, row in lb.iterrows():
            name = str(row.get("player_name", "")).strip()
            if not name:
                continue
            # Store under multiple keys: full name, last name, normalized
            entry = {
                "position": str(row.get("position", "")).strip(),
                "total":    str(row.get("total", "")).strip(),
                "thru":     str(row.get("thru", "")).strip(),
                "r1":       str(row.get("R1", "")).strip(),
                "r2":       str(row.get("R2", "")).strip(),
                "r3":       str(row.get("R3", "")).strip(),
                "r4":       str(row.get("R4", "")).strip(),
            }
            # Remove empty/dash values
            entry = {k: v for k, v in entry.items() if v and v not in ("-", "nan")}
            # Index by last name (first token of "First Last" leaderboard format)
            last = name.split()[-1].lower()
            lookup[last] = entry
            lookup[name.lower()] = entry
        return lookup
    except Exception:
        return {}


def _enrich_bet_with_live(bet: dict, lb: dict[str, dict]) -> dict:
    """Add position/score fields to a bet dict from the leaderboard lookup."""
    player = str(bet.get("player_name", ""))
    # Try last token of player name ("Last, First" → last="Last", "First Last" → last="Last")
    last = player.split(",")[0].strip().lower() if "," in player else player.split()[-1].lower()
    entry = lb.get(last) or lb.get(player.lower()) or {}
    if entry:
        bet["live_position"] = entry.get("position")
        bet["live_total"]    = entry.get("total")
        bet["live_thru"]     = entry.get("thru")
        bet["live_r1"]       = entry.get("r1")
        bet["live_r2"]       = entry.get("r2")
        bet["live_r3"]       = entry.get("r3")
    return bet


@app.get("/api/bets")
def get_bets(market: str = "all", min_edge: float = 0.0) -> dict:
    """
    Recommended bets for the current tournament.
    Optional filters: ?market=top10&min_edge=1.5
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    df = _load_bets(tid)
    if df.empty:
        return {"tournament_id": tid, "bets": [], "count": 0}

    # Coerce numeric columns
    for col in ["edge_pts", "model_prob", "book_prob", "odds_american",
                "confidence", "ev_per_1", "kelly_fraction"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Apply filters
    if market != "all":
        df = df[df["market"].astype(str).str.lower() == market.lower()]
    df = df[df["edge_pts"].fillna(0) >= min_edge]
    df = df.sort_values("edge_pts", ascending=False)

    # Enrich each bet with live position/score from the leaderboard
    lb_lookup = _build_leaderboard_lookup(tid)
    records = [_enrich_bet_with_live(r, lb_lookup) for r in _df_to_records(df)]

    return {
        "tournament_id": tid,
        "bets": records,
        "count": len(records),
    }


@app.get("/api/bets/best")
def get_best_bet() -> dict:
    """Best bet of the week — reads outputs/best_bet.json written by send_best_bet.py.
    Returns available=False if the saved bet is from a different tournament."""
    path = OUTPUTS_DIR / "best_bet.json"
    if not path.exists():
        return {"available": False}
    try:
        import json
        data = json.loads(path.read_text())
        player = str(data.get("player_name", "") or "")
        if not player or player.lower() in ("nan", "none", ""):
            return {"available": False}
        if data.get("market") == "content_card":
            return {"available": False}
        # Stale check: must match current tournament
        current_tid = _get_tournament_id()
        if current_tid and data.get("tournament_id") != current_tid:
            return {"available": False}
        return {"available": True, **data}
    except Exception:
        return {"available": False}


@app.get("/api/odds/comparison")
def get_odds_comparison(market: str = "top10") -> dict:
    """
    Multi-book odds comparison for all players in a given market.
    Returns one row per player with odds from each available book,
    plus the model probability and edge vs DraftKings (no-vig).

    market: top10 | top5 | top20 | outright
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    # Map frontend market name → DG file market name
    dg_mkt_map = {
        "outright": "win", "top5": "top_5",
        "top10": "top_10", "top20": "top_20",
    }
    dg_mkt = dg_mkt_map.get(market.lower())
    if not dg_mkt:
        raise HTTPException(status_code=400, detail=f"Unknown market: {market}")

    dg_path = DG_DIR / f"dg_outrights_{tid}.csv"
    if not dg_path.exists():
        raise HTTPException(status_code=404, detail="DG outrights file not found")

    dg = pd.read_csv(dg_path)
    dg_mkt_df = dg[
        (dg["market"].astype(str).str.lower() == dg_mkt) &
        (dg["is_dg_model"].astype(str).str.lower() != "true")
    ].copy()

    if dg_mkt_df.empty:
        return {"tournament_id": tid, "market": market, "players": [], "books": []}

    # Normalize "Last, First" → "First Last"
    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    dg_mkt_df["player_name_display"] = dg_mkt_df["player_name"].apply(_flip)
    dg_mkt_df["odds_american"]       = pd.to_numeric(dg_mkt_df["odds_american"], errors="coerce")
    dg_mkt_df["book_upper"]          = dg_mkt_df["book"].str.upper()

    # Pivot: player × book → odds
    BOOKS_ORDER = ["DRAFTKINGS", "FANDUEL", "BET365", "BETMGM", "CAESARS", "PINNACLE", "UNIBET", "BOVADA"]
    pivot = dg_mkt_df.pivot_table(
        index="player_name_display", columns="book_upper",
        values="odds_american", aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    books_present = [b for b in BOOKS_ORDER if b in pivot.columns]

    # Load model probabilities
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    model_prob_col = {"top10": "top10_prob", "top5": "top5_prob",
                      "top20": "top20_prob", "outright": "win_prob"}.get(market, "top10_prob")
    if pred_path.exists():
        try:
            preds = pd.read_csv(pred_path)
            if model_prob_col in preds.columns and "player_name" in preds.columns:
                preds["_display"] = preds["player_name"].apply(
                    lambda n: f"{n.split(',')[1].strip()} {n.split(',')[0].strip()}".strip()
                    if "," in str(n) else str(n).strip()
                )
                prob_map = dict(zip(preds["_display"].str.lower(), preds[model_prob_col]))
                pivot["model_prob"] = pivot["player_name_display"].str.lower().map(prob_map)
        except Exception:
            pivot["model_prob"] = None
    else:
        pivot["model_prob"] = None

    # Compute no-vig edge vs DK
    ref_book = next((b for b in ["DRAFTKINGS", "FANDUEL", "BET365"] if b in pivot.columns), None)
    if ref_book:
        spots = {"top10": 10, "top5": 5, "top20": 20, "outright": 1}.get(market, 10)

        def _to_prob(o):
            try:
                o = float(o)
                return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
            except Exception:
                return 0.0

        total = pivot[ref_book].apply(_to_prob).sum()
        nv_factor = total / spots if total > 0 else 1.0

        def _edge(row):
            mp = _safe(row.get("model_prob"))
            odds = _safe(row.get(ref_book))
            if mp is None or odds is None:
                return None
            return round((float(mp) - _to_prob(odds) / nv_factor) * 100, 2)

        pivot["edge_vs_dk"] = pivot.apply(_edge, axis=1)
        pivot = pivot.sort_values("edge_vs_dk", ascending=False, na_position="last")

    # Build response
    players = []
    for _, row in pivot.head(50).iterrows():
        book_odds = {b: _fmt_odds(row[b]) if b in row and pd.notna(row[b]) else None
                     for b in books_present}
        mp = _safe(row.get("model_prob"))
        players.append({
            "player":      str(row["player_name_display"]),
            "model_prob":  round(float(mp) * 100, 1) if mp is not None else None,
            "book_odds":   book_odds,
            "edge_vs_dk":  _safe(row.get("edge_vs_dk")),
            "ref_book":    ref_book,
        })

    return {
        "tournament_id": tid,
        "market":        market,
        "books":         books_present,
        "ref_book":      ref_book,
        "players":       players,
    }


@app.get("/api/predictions")
def get_predictions(limit: int = 50) -> dict:
    """Top N players — Supabase first, CSV fallback."""
    tid = _get_tournament_id()
    df  = None

    # Try Supabase first
    sb = _get_sb()
    if sb and tid:
        try:
            rows = sb.table("predictions").select("*").eq("tournament_id", tid).execute().data
            if rows:
                df = pd.DataFrame(rows)
        except Exception:
            pass

    # Fallback to CSV
    if df is None or df.empty:
        pred_path = OUTPUTS_DIR / "latest_predictions.csv"
        if not pred_path.exists():
            raise HTTPException(status_code=404, detail="No predictions file found")
        df = pd.read_csv(pred_path)

    keep_cols = [c for c in [
        "player_name", "world_rank", "win_prob", "top5_prob", "top10_prob",
        "top20_prob", "cut_prob", "season_sg_total", "model_vs_vegas_edge",
        "form_trend", "odds_to_win", "dk_odds_direction",
        "win_prob_sim", "top5_prob_sim", "top10_prob_sim",
        "top20_prob_sim", "make_cut_prob_sim",
    ] if c in df.columns]

    df = df[keep_cols].copy()
    for col in ["win_prob", "top5_prob", "top10_prob", "top20_prob",
                "cut_prob", "world_rank", "season_sg_total", "model_vs_vegas_edge", "form_trend",
                "win_prob_sim", "top5_prob_sim", "top10_prob_sim", "top20_prob_sim", "make_cut_prob_sim"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    sort_col = "win_prob_sim" if "win_prob_sim" in df.columns and df["win_prob_sim"].notna().any() else "win_prob"
    df = df.sort_values(sort_col, ascending=False).head(limit)

    # Normalize "Last, First" → "First Last"
    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    df["player_name"] = df["player_name"].apply(lambda n: _flip(str(n)))

    # Merge uses_remaining from usage tracker
    uses_map: dict[str, int] = {}
    tracker_path = _TRACKER_JSON
    if tracker_path.exists():
        try:
            with open(tracker_path) as f:
                tracker = json.load(f)
            picks = tracker.get("picks", {})
            for name, info in picks.items():
                uses_map[str(name).strip()] = int(info.get("remaining_uses", 3))
        except Exception:
            pass

    # Merge strategy recommendation, EV, and narrative from strategy_reasoning.json
    rec_map: dict[str, str] = {}
    ev_map:  dict[str, int] = {}
    weekly_narrative = ""
    analysis_generated_at = ""
    sr_path = OUTPUTS_DIR / "strategy_reasoning.json"
    if sr_path.exists():
        try:
            with open(sr_path) as f:
                sr = json.load(f)
            # Only use narrative if it was generated for the current tournament.
            # Old files lack tournament_id — treat those as stale too.
            sr_tid = sr.get("tournament_id", "")
            if not sr_tid or sr_tid != tid:
                sr = {}  # stale or unversioned — suppress narrative
            weekly_narrative       = sr.get("weekly_narrative", "")
            analysis_generated_at  = str(sr.get("generated_at", ""))[:16].replace("T", " ")
            for raw_name, info in sr.get("players", {}).items():
                display = _flip(str(raw_name).strip())
                rec_map[display] = info.get("recommendation", "")
                ev = info.get("this_week_ev")
                if ev is not None:
                    ev_map[display] = int(ev)
        except Exception:
            pass

    # Merge player explanations from player_explanations.csv
    explanation_map: dict[str, str] = {}
    exp_path = OUTPUTS_DIR / "player_explanations.csv"
    if exp_path.exists():
        try:
            exp_df = pd.read_csv(exp_path)
            for _, row in exp_df.iterrows():
                explanation_map[_flip(str(row["player_name"]).strip())] = str(row.get("explanation", ""))
        except Exception:
            pass

    records = []
    for _, row in df.iterrows():
        name = str(row["player_name"])
        uses = uses_map.get(name, 3)
        rec  = rec_map.get(name, "")
        badge = "MAXED" if uses == 0 else ("USE" if "USE" in rec.upper() else ("SAVE" if "SAVE" in rec.upper() else ""))
        entry = {k: _safe(row[k]) for k in keep_cols if k != "player_name"}
        entry["player_name"]    = name
        entry["uses_remaining"] = uses
        entry["recommendation"] = rec
        entry["badge"]          = badge
        entry["this_week_ev"]   = ev_map.get(name)
        entry["explanation"]    = explanation_map.get(name, "")
        records.append(entry)

    return {
        "tournament_id":    tid,
        "players":          records,
        "count":            len(records),
        "weekly_narrative": weekly_narrative,
        "analysis_generated_at": analysis_generated_at,
    }


@app.get("/api/leaderboard")
def get_leaderboard() -> dict:
    """Live leaderboard — Supabase first, CSV fallback."""
    tid      = _get_tournament_id()
    live_dir = DATA_DIR / "live"
    df       = None

    # Try Supabase first
    sb = _get_sb()
    if sb and tid:
        try:
            rows = sb.table("live_leaderboard").select("*").eq("tournament_id", tid.upper()).execute().data
            if rows:
                df = pd.DataFrame(rows)
                for col in ["r1", "r2", "r3", "r4"]:
                    if col in df.columns:
                        df = df.rename(columns={col: col.upper()})
        except Exception:
            pass

    # Fallback to CSV
    if df is None or df.empty:
        lb_files = sorted(live_dir.glob("leaderboard_r*.csv"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if not lb_files:
            raise HTTPException(status_code=404, detail="No leaderboard found")
        df = pd.read_csv(lb_files[0])

    # Numeric coercions
    for col in ["total_numeric", "R1", "R2", "R3", "R4", "position_change"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    keep = [c for c in ["position", "position_change", "player_name", "country",
                         "total", "total_numeric", "thru", "current_round",
                         "R1", "R2", "R3", "R4", "total_strokes",
                         "made_cut", "status", "movement"] if c in df.columns]
    records = _df_to_records(df[keep])

    # Meta
    meta: dict = {}
    meta_files = sorted(live_dir.glob("leaderboard_r*_meta.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if meta_files:
        try:
            with open(meta_files[0]) as f:
                raw_meta = json.load(f)
            meta = {
                "current_round":   raw_meta.get("current_round"),
                "round_status":    raw_meta.get("round_status"),
                "cut_projection":  raw_meta.get("cut_projection"),
                "fetched_at":      raw_meta.get("fetched_at", "")[:16],
            }
        except Exception:
            pass

    return {"tournament_id": tid, "players": records, "count": len(records), **meta}


@app.get("/api/live/vs-predictions")
def get_live_vs_predictions() -> dict:
    """Leaderboard merged with our model predictions — compare live position vs model rank."""
    tid = _get_tournament_id()
    live_dir = DATA_DIR / "live"

    lb_files = sorted(live_dir.glob("leaderboard_r*.csv"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not lb_files:
        raise HTTPException(status_code=404, detail="No leaderboard found")

    lb = pd.read_csv(lb_files[0])
    for col in ["total_numeric", "position_change"]:
        if col in lb.columns:
            lb[col] = pd.to_numeric(lb[col], errors="coerce")

    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    rank_map: dict[str, dict] = {}
    if pred_path.exists():
        preds = pd.read_csv(pred_path)
        preds["win_prob"]   = pd.to_numeric(preds.get("win_prob",   pd.Series()), errors="coerce")
        preds["top10_prob"] = pd.to_numeric(preds.get("top10_prob", pd.Series()), errors="coerce")
        preds = preds.sort_values("win_prob", ascending=False).reset_index(drop=True)
        preds["model_rank"] = preds.index + 1

        def _flip(n: str) -> str:
            s = str(n).strip()
            return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

        for _, row in preds.iterrows():
            display = _flip(str(row["player_name"]))
            entry = {
                "model_rank": int(row["model_rank"]),
                "win_prob":   round(float(row["win_prob"])   * 100, 1) if pd.notna(row.get("win_prob"))   else None,
                "top10_prob": round(float(row["top10_prob"]) * 100, 1) if pd.notna(row.get("top10_prob")) else None,
            }
            rank_map[display.lower()] = entry
            rank_map[str(row["player_name"]).strip().lower()] = entry

    players = []
    for _, row in lb.iterrows():
        name = str(row.get("player_name", "")).strip()
        pinfo = rank_map.get(name.lower(), {})
        pos_raw = row.get("position")
        try:
            live_pos = int(str(pos_raw).replace("T", "").replace("CUT", "999").replace("WD", "999").replace("-", "999"))
        except Exception:
            live_pos = None
        model_rank = pinfo.get("model_rank")
        rank_diff  = (live_pos - model_rank) if (live_pos and model_rank) else None
        players.append({
            "player":      name,
            "position":    _safe(pos_raw),
            "total":       _safe(row.get("total")),
            "total_numeric": _safe(row.get("total_numeric")),
            "thru":        _safe(row.get("thru")),
            "made_cut":    _safe(row.get("made_cut")),
            "status":      _safe(row.get("status")),
            "model_rank":  model_rank,
            "win_prob":    pinfo.get("win_prob"),
            "top10_prob":  pinfo.get("top10_prob"),
            "rank_diff":   rank_diff,   # positive = outperforming model, negative = underperforming
        })

    return {"tournament_id": tid, "players": players}


@app.get("/api/live/my-lineup")
def get_my_lineup_live() -> dict:
    """This week's 3 picks with live leaderboard status.
    Source priority: tracker weekly_lineups for current week → strategy_reasoning.json.
    """
    tid = _get_tournament_id()
    live_dir = DATA_DIR / "live"

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    picks: list[str] = []
    tournament_name = ""

    # 1. Try tracker weekly_lineups for current week (most reliable source of actual picks)
    try:
        sched = pd.read_csv(_SCHED_CSV)
        sched_row = sched[sched["tournament_id"].astype(str) == tid]
        if not sched_row.empty:
            current_week = int(sched_row["week"].iloc[0])
            tournament_name = str(sched_row["tournament_name"].iloc[0])
            tracker_path = _TRACKER_JSON
            if tracker_path.exists():
                tracker = json.loads(tracker_path.read_text())
                week_key = f"week_{current_week}"
                week_entry = tracker.get("weekly_lineups", {}).get(week_key, {})
                raw_lineup = week_entry.get("lineup", [])
                if raw_lineup:
                    picks = [_flip(str(n)) for n in raw_lineup]
    except Exception:
        pass

    # 2. Fall back to strategy_reasoning.json (model-recommended lineup)
    if not picks:
        sr_path = OUTPUTS_DIR / "strategy_reasoning.json"
        if sr_path.exists():
            with open(sr_path) as f:
                sr = json.load(f)
            tournament_name = sr.get("tournament", tournament_name)
            picks = [_flip(n) for n in sr.get("lineup", [])]

    if not picks:
        return {"tournament_id": tid, "picks": [], "tournament": tournament_name}

    def _score_str_local(n) -> str | None:
        if n is None: return None
        try:
            n = int(n)
            return "E" if n == 0 else (f"+{n}" if n > 0 else str(n))
        except (ValueError, TypeError):
            return str(n)

    # Build lb_map: DB (freshest) → in-play cache → CSV fallback
    lb_map: dict[str, dict] = {}

    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                df_lb = conn.execute(
                    "SELECT * FROM live_leaderboard WHERE tournament_id=?", [tid]
                ).fetchdf()
            for _, row in df_lb.iterrows():
                lb_map[str(row.get("player_name", "")).strip().lower()] = {
                    "position":      _safe(row.get("position")),
                    "total":         _score_str_local(row.get("total_numeric")),
                    "total_numeric": _safe(row.get("total_numeric")),
                    "thru":          _safe(row.get("thru")),
                    "R1": _safe(row.get("r1")), "R2": _safe(row.get("r2")),
                    "R3": _safe(row.get("r3")), "R4": _safe(row.get("r4")),
                    "made_cut":      _safe(row.get("made_cut")),
                    "win_prob":      _safe(row.get("win_prob")),
                    "top10_prob":    _safe(row.get("top10_prob")),
                }
        except Exception:
            pass

    # In-play cache fallback (populated on each /api/live/inplay hit)
    if not lb_map:
        for p in (_inplay_cache.get("data") or {}).get("players", []):
            name_key = str(p.get("player_name", "")).strip().lower()
            lb_map[name_key] = {
                "position": p.get("position"), "total": p.get("total"),
                "total_numeric": p.get("total_numeric"), "thru": p.get("thru"),
                "R1": p.get("R1"), "R2": p.get("R2"), "R3": p.get("R3"), "R4": p.get("R4"),
                "made_cut": p.get("made_cut"), "win_prob": p.get("win_prob"), "top10_prob": p.get("top10_prob"),
            }

    # CSV final fallback
    if not lb_map:
        lb_files = sorted(live_dir.glob("leaderboard_r*.csv"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if lb_files:
            lb = pd.read_csv(lb_files[0])
            for col in ["total_numeric", "R1", "R2", "R3", "R4"]:
                if col in lb.columns: lb[col] = pd.to_numeric(lb[col], errors="coerce")
            for _, row in lb.iterrows():
                lb_map[str(row.get("player_name", "")).strip().lower()] = {
                    "position": _safe(row.get("position")), "total": _safe(row.get("total")),
                    "total_numeric": _safe(row.get("total_numeric")), "thru": _safe(row.get("thru")),
                    "R1": _safe(row.get("R1")), "R2": _safe(row.get("R2")),
                    "R3": _safe(row.get("R3")), "R4": _safe(row.get("R4")),
                    "made_cut": _safe(row.get("made_cut")),
                }

    # Build a last-name → full-name lookup so short tracker names (e.g. "Scheffler") resolve
    lastname_map: dict[str, str] = {}
    for full_lower in lb_map:
        parts = full_lower.split()
        if parts:
            lastname_map[parts[-1]] = full_lower  # last token → full key

    result = []
    for name in picks:
        key = name.lower()
        lb_info = lb_map.get(key)
        if lb_info is None:
            # Try matching on last name token
            last = key.split()[-1]
            resolved = lastname_map.get(last)
            if resolved:
                lb_info = lb_map[resolved]
                name = " ".join(w.capitalize() for w in resolved.split())  # pretty-print full name
        result.append({"player": name, **(lb_info or {})})

    return {"tournament_id": tid, "tournament": tournament_name, "picks": result}


_SG_STATS_TTL_SECS = 300  # re-fetch from DG if DB row is older than 5 minutes
_ROUND_PARAM_TO_NUM = {"event_avg": 0, "1": 1, "2": 2, "3": 3, "4": 4}


def _refresh_sg_stats_from_dg(tid: str, round_param: str) -> bool:
    """Fetch live SG stats from DG API, write to DB + CSV. Returns True on success."""
    try:
        from scripts.scrapers.dg_client import dg_get
        SG_STATS = "sg_putt,sg_arg,sg_app,sg_ott,sg_t2g,sg_total,driving_dist,driving_acc"
        raw = dg_get("/preds/live-tournament-stats", {"stats": SG_STATS, "round": round_param, "tour": "pga"})
        fetched_at = datetime.utcnow().isoformat()
        event_name  = raw.get("event_name", "")
        last_updated = raw.get("last_updated", "")
        round_num = _ROUND_PARAM_TO_NUM.get(round_param, 0)
        rows = []
        for p in raw.get("live_stats", []):
            rows.append({
                "player_name": p.get("player_name", ""), "dg_id": str(p.get("dg_id", "")),
                "position": str(p.get("position", "")), "total": p.get("total"),
                "thru": p.get("thru"), "sg_ott": p.get("sg_ott"), "sg_app": p.get("sg_app"),
                "sg_arg": p.get("sg_arg"), "sg_putt": p.get("sg_putt"),
                "sg_t2g": p.get("sg_t2g"), "sg_total": p.get("sg_total"),
                "driving_dist": p.get("driving_dist"), "driving_acc": p.get("driving_acc"),
                "tournament_id": tid, "round_num": round_num,
                "event_name": event_name, "last_updated": last_updated, "fetched_at": fetched_at,
            })
        if not rows:
            return False
        df = pd.DataFrame(rows)
        df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0).astype(int)
        df["thru"]  = pd.to_numeric(df["thru"],  errors="coerce")
        for col in ["sg_ott","sg_app","sg_arg","sg_putt","sg_t2g","sg_total","driving_dist","driving_acc"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Write to DB
        if _DB_AVAILABLE:
            with _get_db_conn() as conn:
                conn.register("_sg_fresh", df)
                conn.execute(f"DELETE FROM live_stats WHERE tournament_id='{tid}' AND round_num={round_num}")
                conn.execute("""
                    INSERT OR REPLACE INTO live_stats
                        (tournament_id, player_name, dg_id, round_num, position, total, thru,
                         sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, sg_total,
                         driving_dist, driving_acc, event_name, last_updated, fetched_at)
                    SELECT tournament_id, player_name, dg_id, round_num, position, total, thru,
                           sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, sg_total,
                           driving_dist, driving_acc, event_name, last_updated, fetched_at
                    FROM _sg_fresh
                """)
        # Also keep CSV as backup
        df_csv = df.copy()
        df_csv["round_param"] = round_param
        df_csv = df_csv.sort_values("sg_total", ascending=False, na_position="last")
        out = DG_DIR / f"dg_live_stats_{tid}_{round_param}.csv"
        df_csv.to_csv(out, index=False)
        if round_param == "event_avg":
            (DG_DIR / f"dg_live_stats_{tid}_latest.csv").write_bytes(out.read_bytes())
        return True
    except Exception:
        return False


@app.get("/api/live/sg-stats")
def get_live_sg_stats(round_param: str = "event_avg") -> dict:
    """
    DG live SG stats — reads from DB, auto-refreshes from DG if data is >5 minutes old.
    round_param: event_avg | 1 | 2 | 3 | 4
    """
    tid = _get_tournament_id()
    round_num = _ROUND_PARAM_TO_NUM.get(round_param, 0)

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    # Check DB freshness
    stale = True
    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                row = conn.execute(
                    "SELECT MAX(fetched_at) FROM live_stats WHERE tournament_id=? AND round_num=?",
                    [tid, round_num]
                ).fetchone()
                if row and row[0]:
                    age = (datetime.utcnow() - datetime.fromisoformat(str(row[0])[:19])).total_seconds()
                    stale = age > _SG_STATS_TTL_SECS
        except Exception:
            pass

    if stale:
        _refresh_sg_stats_from_dg(tid, round_param)

    # Read from DB
    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                df = conn.execute(
                    "SELECT * FROM live_stats WHERE tournament_id=? AND round_num=? ORDER BY sg_total DESC NULLS LAST",
                    [tid, round_num]
                ).fetchdf()
            if not df.empty:
                players = []
                updated = None
                if "last_updated" in df.columns and not df["last_updated"].dropna().empty:
                    updated = str(df["last_updated"].dropna().iloc[0])[:16]
                for _, row in df.iterrows():
                    players.append({
                        "player":       _flip(str(row.get("player_name", ""))),
                        "position":     _safe(row.get("position")),
                        "total":        _safe(row.get("total")),
                        "thru":         _safe(row.get("thru")),
                        "sg_total":     _safe(row.get("sg_total")),
                        "sg_ott":       _safe(row.get("sg_ott")),
                        "sg_app":       _safe(row.get("sg_app")),
                        "sg_arg":       _safe(row.get("sg_arg")),
                        "sg_putt":      _safe(row.get("sg_putt")),
                        "sg_t2g":       _safe(row.get("sg_t2g")),
                        "driving_dist": _safe(row.get("driving_dist")),
                        "driving_acc":  _safe(row.get("driving_acc")),
                    })
                return {"tournament_id": tid, "players": players, "round_param": round_param, "updated": updated}
        except Exception:
            pass

    # CSV fallback
    sg_path = DG_DIR / f"dg_live_stats_{tid}_{round_param}.csv"
    if not sg_path.exists():
        sg_path = DG_DIR / f"dg_live_stats_{tid}_latest.csv"
    if not sg_path.exists():
        return {"tournament_id": tid, "players": [], "updated": None}
    df = pd.read_csv(sg_path)
    for col in ["sg_total","sg_ott","sg_app","sg_arg","sg_putt","sg_t2g","driving_dist","driving_acc","total"]:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("sg_total", ascending=False, na_position="last")
    players = [{"player": _flip(str(r.get("player_name",""))), "position": _safe(r.get("position")),
                "total": _safe(r.get("total")), "thru": _safe(r.get("thru")),
                "sg_total": _safe(r.get("sg_total")), "sg_ott": _safe(r.get("sg_ott")),
                "sg_app": _safe(r.get("sg_app")), "sg_arg": _safe(r.get("sg_arg")),
                "sg_putt": _safe(r.get("sg_putt")), "sg_t2g": _safe(r.get("sg_t2g")),
                "driving_dist": _safe(r.get("driving_dist")), "driving_acc": _safe(r.get("driving_acc"))}
               for _, r in df.iterrows()]
    updated = str(df["last_updated"].dropna().iloc[0])[:16] if "last_updated" in df.columns and not df["last_updated"].dropna().empty else None
    return {"tournament_id": tid, "players": players, "round_param": round_param, "updated": updated}


_HOLE_STATS_CACHE: dict = {}
_HOLE_STATS_TTL = 300  # 5-minute cache

@app.get("/api/live/hole-stats")
def get_live_hole_stats(round_param: str = "event_avg") -> dict:
    """
    Per-hole scoring stats from DG (avg score, vs par, birdie/bogey/double counts, morning/afternoon wave).
    round_param: event_avg | 1 | 2 | 3 | 4 (event_avg returns current round)
    """
    cache_key = round_param
    cached = _HOLE_STATS_CACHE.get(cache_key)
    if cached and time.time() - cached["_ts"] < _HOLE_STATS_TTL:
        return cached

    try:
        from scripts.scrapers.dg_client import dg_get
        params: dict = {"tour": "pga"}
        if round_param not in ("event_avg", ""):
            params["round"] = round_param
        raw = dg_get("/preds/live-hole-stats", params)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DG API error: {e}")

    courses = raw.get("courses", [])
    if not courses:
        return {"event_name": raw.get("event_name", ""), "round": raw.get("current_round"), "holes": [], "updated": raw.get("last_update", "")}

    # Flatten first course's first round (PGA events typically one course)
    course = courses[0]
    rounds_data = course.get("rounds", [])
    if not rounds_data:
        return {"event_name": raw.get("event_name", ""), "round": raw.get("current_round"), "holes": [], "updated": raw.get("last_update", "")}

    round_obj = rounds_data[0]
    holes_raw = round_obj.get("holes", [])

    holes = []
    for h in holes_raw:
        par = h.get("par")
        yardage = h.get("yardage")
        total = h.get("total", {})
        morning = h.get("morning_wave", {})
        afternoon = h.get("afternoon_wave", {})

        def _pct(count, thru):
            return round(count / thru * 100, 1) if thru and thru > 0 else None

        def _wave(w: dict) -> dict:
            thru = w.get("players_thru") or 0
            avg = w.get("avg_score")
            vs_par = round(avg - par, 3) if avg is not None and par else None
            return {
                "players_thru": thru,
                "avg_score":    round(avg, 3) if avg is not None else None,
                "vs_par":       vs_par,
                "birdies":      w.get("birdies", 0),
                "pars":         w.get("pars", 0),
                "bogeys":       w.get("bogeys", 0),
                "doubles":      w.get("doubles_or_worse", 0),
                "eagles":       w.get("eagles_or_better", 0),
                "birdie_pct":   _pct(w.get("birdies", 0), thru),
                "bogey_pct":    _pct(w.get("bogeys", 0), thru),
                "double_pct":   _pct(w.get("doubles_or_worse", 0), thru),
            }

        thru = total.get("players_thru") or 0
        avg = total.get("avg_score")
        vs_par = round(avg - par, 3) if avg is not None and par else None

        holes.append({
            "hole":       h.get("hole"),
            "par":        par,
            "yardage":    yardage,
            "players_thru": thru,
            "avg_score":  round(avg, 3) if avg is not None else None,
            "vs_par":     vs_par,
            "birdies":    total.get("birdies", 0),
            "pars":       total.get("pars", 0),
            "bogeys":     total.get("bogeys", 0),
            "doubles":    total.get("doubles_or_worse", 0),
            "eagles":     total.get("eagles_or_better", 0),
            "birdie_pct": _pct(total.get("birdies", 0), thru),
            "bogey_pct":  _pct(total.get("bogeys", 0), thru),
            "double_pct": _pct(total.get("doubles_or_worse", 0), thru),
            "morning":    _wave(morning),
            "afternoon":  _wave(afternoon),
        })

    result = {
        "event_name": raw.get("event_name", ""),
        "round":      raw.get("current_round"),
        "holes":      holes,
        "updated":    raw.get("last_update", ""),
        "_ts":        time.time(),
    }
    _HOLE_STATS_CACHE[cache_key] = result
    return result


@app.get("/api/live/hole-scores")
def get_hole_scores() -> dict:
    """Per-hole scores indexed by player name and round number."""
    tid = _get_tournament_id()
    path = DATA_DIR / "live" / f"hole_scores_{tid.lower()}.csv"
    if not path.exists():
        return {"tournament_id": tid, "by_player": {}}

    df = pd.read_csv(path)

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    by_player: dict = {}
    for _, row in df.iterrows():
        name = _flip(str(row.get("player_name", "")))
        rnd  = str(int(float(row["round"]))) if pd.notna(row.get("round")) else "1"
        holes = []
        for h in range(1, 19):
            st  = _safe(row.get(f"h{h}"))
            par = _safe(row.get(f"h{h}_par"))
            rel = _safe(row.get(f"h{h}_rel"))
            holes.append({
                "hole":    h,
                "strokes": int(st)  if st  is not None else None,
                "par":     int(par) if par is not None else None,
                "rel":     int(rel) if rel is not None else None,
            })
        if name not in by_player:
            by_player[name] = {}
        by_player[name][rnd] = holes

    return {"tournament_id": tid, "by_player": by_player}


# ── In-play cache (avoids hammering DG on every frontend poll) ────────────────
_inplay_cache: dict = {"ts": 0.0, "data": None}
_INPLAY_TTL = 60  # seconds

@app.get("/api/live/inplay")
def get_inplay() -> dict:
    """
    Live leaderboard + win probabilities direct from DataGolf /preds/in-play.
    Cached for 60 seconds so the frontend can poll freely without hitting DG rate limits.
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.scrapers.dg_client import dg_get

    # Return cached result if still fresh
    if time.time() - _inplay_cache["ts"] < _INPLAY_TTL and _inplay_cache["data"]:
        return _inplay_cache["data"]

    try:
        raw = dg_get("/preds/in-play", {})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DG API error: {e}")

    info    = raw.get("info", {})
    players = raw.get("data", [])

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    def _pos(p: dict) -> str | None:
        pos = p.get("current_pos")
        if pos in (None, "", "null"): return None
        return str(pos)

    def _score_str(n) -> str | None:
        if n is None: return None
        n = int(n)
        if n == 0:  return "E"
        return f"+{n}" if n > 0 else str(n)

    rows = []
    for p in players:
        name = _flip(str(p.get("player_name", "")))
        thru_raw = p.get("thru")
        thru = str(int(thru_raw)) if thru_raw not in (None, 0, "0") else None
        rows.append({
            "player_name":    name,
            "position":       _pos(p),
            "country":        p.get("country"),
            "total":          _score_str(p.get("current_score")),
            "total_numeric":  p.get("current_score"),
            "thru":           thru,
            "current_round":  p.get("round"),
            "R1":             p.get("R1"),
            "R2":             p.get("R2"),
            "R3":             p.get("R3"),
            "R4":             p.get("R4"),
            "today":          p.get("today"),
            "made_cut":       bool(p.get("make_cut", 1)),
            "win_prob":       round(float(p["win"]) * 100, 1)   if p.get("win")    is not None else None,
            "top5_prob":      round(float(p["top_5"]) * 100, 1) if p.get("top_5")  is not None else None,
            "top10_prob":     round(float(p["top_10"]) * 100, 1) if p.get("top_10") is not None else None,
            "top20_prob":     round(float(p["top_20"]) * 100, 1) if p.get("top_20") is not None else None,
        })

    def _sort_key(r: dict):
        score = r.get("total_numeric")
        score = score if score is not None else 999

        thru_raw = r.get("thru")
        if thru_raw in (None, ""):
            thru = 0          # not started — loosely tied at 0
        elif str(thru_raw).upper() in ("F", "18"):
            thru = -18        # finished round — sort before in-progress ties
        else:
            try:
                thru = -int(str(thru_raw).replace("*", ""))
            except ValueError:
                thru = 0

        cut = 0 if r.get("made_cut", True) else 1
        return (cut, score, thru)

    rows.sort(key=_sort_key)

    # Merge movement from leaderboard CSV (not available from DG live API)
    try:
        _tid = _get_tournament_id()
        _lb_csv = DATA_DIR / "live" / f"leaderboard_{_tid.lower()}.csv"
        if _lb_csv.exists():
            _lb_mv = pd.read_csv(_lb_csv, usecols=lambda c: c in ("player_name", "movement"))
            _mv_map = {str(r["player_name"]).strip(): str(r.get("movement", "") or "")
                       for _, r in _lb_mv.iterrows()}
            for row in rows:
                row["movement"] = _mv_map.get(row["player_name"], None)
    except Exception:
        pass

    result = {
        "tournament_id":  _get_tournament_id(),
        "event_name":     info.get("event_name", ""),
        "current_round":  info.get("current_round"),
        "last_update":    info.get("last_update", ""),
        "players":        rows,
        "count":          len(rows),
    }

    _inplay_cache["ts"]   = time.time()
    _inplay_cache["data"] = result

    # Write to live_leaderboard DB so my-lineup and other endpoints always have fresh data
    if _DB_AVAILABLE and rows:
        try:
            tid = result["tournament_id"]
            fetched_at = datetime.utcnow().isoformat()
            df_lb = pd.DataFrame([{
                "tournament_id": tid,
                "player_name":   r["player_name"],
                "position":      r.get("position"),
                "total_numeric": r.get("total_numeric") if r.get("total_numeric") is not None else 0,
                "thru":          str(r.get("thru") or ""),
                "current_round": r.get("current_round") or 1,
                "r1":            r.get("R1"), "r2": r.get("R2"),
                "r3":            r.get("R3"), "r4": r.get("R4"),
                "today":         r.get("today"),
                "made_cut":      bool(r.get("made_cut", True)),
                "win_prob":      r.get("win_prob"),
                "top10_prob":    r.get("top10_prob"),
                "fetched_at":    fetched_at,
            } for r in rows])
            with _get_db_conn() as conn:
                conn.register("_lb_fresh", df_lb)
                conn.execute(f"DELETE FROM live_leaderboard WHERE tournament_id='{tid}'")
                conn.execute("""
                    INSERT INTO live_leaderboard
                        (tournament_id, player_name, position, total_numeric, thru,
                         current_round, r1, r2, r3, r4, today, made_cut, win_prob, top10_prob, fetched_at)
                    SELECT tournament_id, player_name, position, total_numeric, thru,
                           current_round, r1, r2, r3, r4, today, made_cut, win_prob, top10_prob, fetched_at
                    FROM _lb_fresh
                """)
        except Exception:
            pass

    # Detect and push live alerts (only runs on fresh fetches, not cache hits)
    try:
        _detect_alerts(rows, result["tournament_id"], result["current_round"])
    except Exception:
        pass

    return result


@app.post("/api/live/refresh-hole-scores")
def refresh_hole_scores() -> dict:
    """
    Trigger fetch_hole_scores.py in the background so the frontend doesn't wait.
    Takes ~30-60s to run (one PGA Tour GraphQL call per player).
    The next auto-poll of /api/live/hole-scores will return fresh data.
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    cmd = [
        "python3",
        str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_hole_scores.py"),
        "--tournament-id", tid,
    ]
    # Popen (not run) so it's non-blocking — returns immediately
    subprocess.Popen(cmd, cwd=PROJECT_ROOT,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "message": "Hole scores refresh started in background"}


@app.get("/api/live/pulse")
def get_live_pulse(force: bool = False) -> dict:
    """
    LLM-generated live tournament narrative: leaders, players on fire,
    players to watch, your picks status, round story.
    Cached per round for 30 minutes. Pass force=true to regenerate.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set")

    tid = _get_tournament_id()
    cache_dir = DATA_DIR / "player_synopses"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"live_pulse_{tid}.json"

    if not force and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            age_min = (time.time() - cached.get("generated_ts", 0)) / 60
            sections = cached.get("sections", {})
            headline = sections.get("headline", "")
            # Detect corrupt cache: headline shouldn't start with { or ```
            valid = age_min < 30 and not str(headline).strip().startswith(("{", "```"))
            if valid:
                cached["cached"] = True
                return cached
        except Exception:
            pass

    # ── Load live data ────────────────────────────────────────────────────────
    # In-play leaderboard
    inplay_players: list[dict] = []
    current_round = 1
    try:
        lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
        if lb_path.exists():
            lb = pd.read_csv(lb_path)
            lb["total_numeric"] = pd.to_numeric(lb.get("total_numeric", 0), errors="coerce").fillna(0)
            lb = lb.sort_values("total_numeric").head(30)
            current_round = int(lb["current_round"].mode()[0]) if "current_round" in lb.columns else 1
            for _, r in lb.iterrows():
                inplay_players.append({
                    "name":     str(r.get("player_name", "")),
                    "pos":      str(r.get("position", "")),
                    "total":    int(r.get("total_numeric", 0)),
                    "thru":     str(r.get("thru", "")),
                    "today":    str(r.get("current_round", "")),
                    "made_cut": bool(r.get("made_cut", True)),
                    "movement": str(r.get("movement", "")) or "",
                    "R1": r.get("R1"), "R2": r.get("R2"), "R3": r.get("R3"), "R4": r.get("R4"),
                })
    except Exception:
        pass

    # DG live SG stats — top performers
    sg_leaders: list[dict] = []
    try:
        stats_path = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_latest.csv"
        if stats_path.exists():
            sg = pd.read_csv(stats_path)
            for col in ["sg_total", "sg_app", "sg_ott", "sg_putt", "sg_arg"]:
                if col in sg.columns:
                    sg[col] = pd.to_numeric(sg[col], errors="coerce")
            sg = sg.dropna(subset=["sg_total"]).sort_values("sg_total", ascending=False).head(15)
            for _, r in sg.iterrows():
                sg_leaders.append({
                    "name":     str(r.get("player_name", "")),
                    "pos":      str(r.get("position", "")),
                    "total":    int(r.get("total", 0)),
                    "thru":     str(r.get("thru", "")),
                    "sg_total": round(float(r["sg_total"]), 2),
                    "sg_app":   round(float(r["sg_app"]), 2) if pd.notna(r.get("sg_app")) else None,
                    "sg_ott":   round(float(r["sg_ott"]), 2) if pd.notna(r.get("sg_ott")) else None,
                    "sg_putt":  round(float(r["sg_putt"]), 2) if pd.notna(r.get("sg_putt")) else None,
                })
    except Exception:
        pass


    # Enrich players with season context from latest_predictions.csv
    pred_ctx: dict[str, dict] = {}
    try:
        preds_path = OUTPUTS_DIR / "latest_predictions.csv"
        if preds_path.exists():
            preds = pd.read_csv(preds_path)
            for col in ["season_sg_total","season_sg_app","season_sg_putt",
                          "recent_scoring_avg","recent_top10s","momentum_trend",
                          "course_starts","course_best_finish","course_avg_to_par",
                          "last_start_position","missed_cut_last_start","world_rank"]:
                if col in preds.columns:
                    preds[col] = pd.to_numeric(preds[col], errors="coerce") if col != "momentum_trend" else preds[col]
            def _ln(n): 
                return str(n).split(",")[0].strip().lower() if "," in str(n) else str(n).strip().split()[-1].lower()

            for _, row in preds.iterrows():
                key = _ln(str(row.get("player_name","")))
                pred_ctx[key] = {
                "season_sg": round(float(row["season_sg_total"]), 2) if pd.notna(row.get("season_sg_total")) else None,
                      "sg_app": round(float(row["season_sg_app"]), 2) if pd.notna(row.get("season_sg_app")) else None,
                      "sg_putt":     round(float(row["season_sg_putt"]), 2)  if pd.notna(row.get("season_sg_putt")) else None,
                      "scoring_avg": round(float(row["recent_scoring_avg"]),1) if pd.notna(row.get("recent_scoring_avg")) else None,
                      "top10s": int(row["recent_top10s"]) if pd.notna(row.get("recent_top10s")) else None,
                      "momentum":  str(row["momentum_trend"]).strip() if pd.notna(row.get("momentum_trend")) else None,
                      "c_starts": int(row["course_starts"]) if pd.notna(row.get("course_starts")) else None,
                      "c_best": int(row["course_best_finish"]) if pd.notna(row.get("course_best_finish")) else None, 
                      "c_avg":       round(float(row["course_avg_to_par"]),1) if pd.notna(row.get("course_avg_to_par")) else None, 
                    "last_pos":    int(row["last_start_position"]) if pd.notna(row.get("last_start_position")) else None,
                    "missed_cut":  int(row["missed_cut_last_start"]) if pd.notna(row.get("missed_cut_last_start")) else None, 
                    "world_rank":  int(row["world_rank"]) if pd.notna(row.get("world_rank")) else None,
                  }
    except Exception:
        pass


    try:
        pred_tid = str(preds["tournament_id"].iloc[0]) if "tournament_id" in preds.columns else ""
        if pred_tid and pred_tid != tid:
            for v in pred_ctx.values():
                v["c_starts"] = None 
                v["c_best"] = None
                v["c_avg"] = None
                # invalidate course starts context if preds are from a different tournament
    except Exception:
        pass




    # Fantasy picks
    fantasy_picks: list[dict] = []
    try:
        tracker_path = _TRACKER_JSON
        if tracker_path.exists():
            tracker = json.loads(tracker_path.read_text())
            def _ln(n): s = str(n).strip(); return s.split(",")[0].strip().lower() if "," in s else s.split()[-1].lower()
            pick_lnames = {_ln(k): k for k in tracker.get("picks", {})}
            for p in inplay_players:
                ln = _ln(p["name"])
                if ln in pick_lnames:
                    uses = tracker["picks"][pick_lnames[ln]].get("remaining_uses", 3)
                    fantasy_picks.append({**p, "uses_remaining": uses})
    except Exception:
        pass

    # Tournament name
    tournament_name = tid
    try:
        sched = pd.read_csv(_SCHED_CSV)
        row = sched[sched["tournament_id"].astype(str) == tid]
        if not row.empty:
            tournament_name = str(row["tournament_name"].iloc[0])
    except Exception:
        pass

    # ── Build prompt ──────────────────────────────────────────────────────────
    def _fmt_lb(players: list[dict]) -> str:
        lines = []
        for p in players[:20]:
            score = f"{p['total']:+d}" if p['total'] != 0 else "E"
            def _r_score(v):
                try: return int(float(v))
                except (TypeError, ValueError): return None
            r_scores = " | ".join(
                f"R{i+1}:{_r_score(p.get(f'R{i+1}'))}"
                for i in range(4)
                if _r_score(p.get(f'R{i+1}')) is not None
            )
            lines.append(f"  {p['pos']:<5} {p['name']:<25} {score:<5} thru {p['thru']}  {r_scores}")
        return "\n".join(lines)

    def _fmt_sg(players: list[dict]) -> str:
        lines = []
        for p in players[:12]:
            score = f"{p['total']:+d}" if p['total'] != 0 else "E"
            ctx = pred_ctx.get(p["name"].strip().split()[-1].lower(), {})
            ctx_parts = []
            if ctx.get("season_sg") is not None:
                ctx_parts.append(f"season SG {ctx['season_sg']:+.2f}")
            if ctx.get("momentum"):
                m = ctx["momentum"].upper()
                if m in ("HOT","COLD"): ctx_parts.append(m)
            if ctx.get("c_starts") and ctx["c_starts"] > 0:
                cp = f"course: {ctx['c_starts']} starts"
                if ctx.get("c_best"): cp += f" best T{ctx['c_best']}"
                ctx_parts.append(cp)
            ctx_str = "  [" + " | ".join(ctx_parts) + "]" if ctx_parts else ""
            lines.append(
                f"  {p['name']:<25} pos={p['pos']:<5} {score:<5} thru {p['thru']}"
                f"  SG: total={p['sg_total']:+.2f}  app={p.get('sg_app',0) or 0:+.2f}"
                f"  ott={p.get('sg_ott',0) or 0:+.2f}  putt={p.get('sg_putt',0) or 0:+.2f}"
                f"{ctx_str}"
            )
        return "\n".join(lines)

    def _fmt_picks(picks: list[dict]) -> str:
        if not picks:
            return "  (none of your fantasy picks are in the current field data)"
        lines = []
        for p in picks:
            score = f"{p['total']:+d}" if p['total'] != 0 else "E"
            ctx = pred_ctx.get(p["name"].strip().split()[-1].lower(), {})
            ctx_parts = []
            if ctx.get("season_sg") is not None:
                ctx_parts.append(f"season SG {ctx['season_sg']:+.2f}")
            if ctx.get("scoring_avg"):
                ctx_parts.append(f"recent scoring avg {ctx['scoring_avg']}")
            if ctx.get("top10s") is not None:
                ctx_parts.append(f"{ctx['top10s']} recent top-10s")
            if ctx.get("c_starts") and ctx["c_starts"] > 0:
                cp = f"course: {ctx['c_starts']} starts"
                if ctx.get("c_best"): cp += f" best T{ctx['c_best']}"
                ctx_parts.append(cp)
            ctx_str = "  [" + " | ".join(ctx_parts) + "]" if ctx_parts else ""
            cut_note = "  ⚠ MISSED CUT" if not p.get("made_cut", True) else ""
            lines.append(
                f"  {p['name']:<25} pos={p['pos']:<5} {score:<5} thru {p['thru']}"
                f"  uses_left={p['uses_remaining']}{ctx_str}{cut_note}"
            )
        return "\n".join(lines)

    # Static instructions go in the system prompt so they can be cached.
    # Dynamic live data goes in the user turn — it changes every refresh.
    _SYSTEM = """You are a live PGA Tour analyst. Generate sharp, real-time tournament commentary.

Rules:
- Use ONLY data provided in the user message. Do not invent stats, scores, or results.
- Every sentence must contain at least one number or player name.
- No filler phrases ("it's clear that", "notably", "it's worth mentioning").
- Keep it tight — this is a live feed, not an essay.

Output format: JSON only, no markdown fences. Exactly this structure:
{
  "headline": "One punchy sentence capturing the biggest story right now.",
  "leaders": "2-3 sentences about who's leading, how they're doing it (which SG categories), and what's driving them.",
  "on_fire": [
    {"name": "Player Name", "blurb": "1-2 sentences on why they're on fire — cite SG numbers and specific strokes gained."},
    {"name": "Player Name", "blurb": "..."}
  ],
  "to_watch": [
    {"name": "Player Name", "blurb": "1-2 sentences on why this player is dangerous — position, SG trend, trajectory."},
    {"name": "Player Name", "blurb": "..."}
  ],
  "your_picks": "1-2 sentences about the user's fantasy picks — position, scoring, and whether they look likely to pay off.",
  "round_story": "1-2 sentences on the broader narrative — scoring conditions, big moves, surprises."
}"""

    user_msg = f"""Round {current_round} — {tournament_name}

--- LEADERBOARD (top 20) ---
{_fmt_lb(inplay_players)}

--- LIVE SG LEADERS (top 15 by total SG this round/event) ---
{_fmt_sg(sg_leaders)}

--- USER'S FANTASY PICKS ---
{_fmt_picks(fantasy_picks)}"""

    # ── Call Claude Haiku ─────────────────────────────────────────────────────
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1400,
            # cache_control on system — static instructions cached across refreshes.
            # Haiku requires 2048+ tokens to trigger caching; the threshold is met
            # once the instruction block grows (or if switched to Sonnet at 1024).
            system=[{
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = message.content[0].text.strip()
        cache_read = getattr(message.usage, "cache_read_input_tokens", 0) or 0
        cache_created = getattr(message.usage, "cache_creation_input_tokens", 0) or 0
        if cache_read:
            print(f"[pulse] cache hit: {cache_read} tokens read from cache")
        elif cache_created:
            print(f"[pulse] cache created: {cache_created} tokens cached")
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw).rstrip("`").strip()
        sections = json.loads(raw)
    except json.JSONDecodeError as _jde:
        # Truncated JSON — try to salvage required fields via regex
        def _extract(key, default=""):
            m2 = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            return m2.group(1) if m2 else default
        sections = {
            "headline":    _extract("headline"),
            "leaders":     _extract("leaders"),
            "on_fire":     [],
            "to_watch":    [],
            "your_picks":  _extract("your_picks"),
            "round_story": _extract("round_story"),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    result = {
        "tournament_id":   tid,
        "tournament_name": tournament_name,
        "current_round":   current_round,
        "sections":        sections,
        "generated_ts":    time.time(),
        "cached":          False,
    }

    try:
        cache_file.write_text(json.dumps(result))
    except Exception:
        pass

    # ── Persist to DuckDB ─────────────────────────────────────────────────────
    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                on_fire_json  = json.dumps(sections.get("on_fire", []))
                to_watch_json = json.dumps(sections.get("to_watch", []))
                conn.execute("""
                    INSERT OR REPLACE INTO live_pulse
                        (tournament_id, round_num, generated_at, headline, leaders_text,
                         on_fire_json, to_watch_json, your_picks_text, round_story, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    tid, current_round,
                    datetime.utcnow().isoformat(),
                    sections.get("headline", ""),
                    sections.get("leaders", ""),
                    on_fire_json,
                    to_watch_json,
                    sections.get("your_picks", ""),
                    sections.get("round_story", ""),
                    json.dumps(sections),
                ])
        except Exception:
            pass

    return result


@app.post("/api/refresh-bets")
def refresh_bets() -> dict:
    """Trigger recommend_bets.py and return the updated bets."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    cmd = [
        "python3", str(PROJECT_ROOT / "scripts" / "models" / "recommend_bets.py"),
        "--tournament-id", tid,
        "--min-edge", "0.75", "--min-confidence", "0.45",
        "--max-per-market", "15", "--top-n", "40",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=120, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[:500])

    df = _load_bets(tid)
    return {
        "tournament_id": tid,
        "bets": _df_to_records(df),
        "count": len(df),
        "log": result.stdout[-800:],
    }


@app.post("/api/refresh-odds")
def refresh_odds() -> dict:
    """Trigger refresh_odds.py (updates latest_predictions.csv odds columns)."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    cmd = [
        "python3", str(PROJECT_ROOT / "scripts" / "predictions" / "refresh_odds.py"),
        "--tournament-id", tid,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=120, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[:500])

    return {"tournament_id": tid, "ok": True, "log": result.stdout[-800:]}


@app.post("/api/refresh-dg-odds")
def refresh_dg_odds() -> dict:
    """Fetch fresh DG outrights (all markets) — updates dg_outrights_{tid}.csv."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    cmd = [
        "python3",
        str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_dg_odds.py"),
        "--tournament-id", tid,
        "--market", "all",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            timeout=120, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr[:500])

    # Return the updated explorer data for the default market
    path = DG_DIR / f"dg_outrights_{tid}.csv"
    updated = None
    if path.exists():
        raw = pd.read_csv(path)
        if "last_updated" in raw.columns and not raw["last_updated"].dropna().empty:
            updated = str(raw["last_updated"].dropna().iloc[0])[:16]

    return {"tournament_id": tid, "ok": True, "updated": updated, "log": result.stdout[-400:]}


@app.get("/api/model-comparison")
def get_model_comparison() -> dict:
    """
    Compare our model predictions vs DataGolf's pre-tournament predictions.
    Returns Spearman ρ by market, top-10 picks side-by-side, and largest disagreements.
    """
    from scipy.stats import spearmanr

    tid = _get_tournament_id()

    # Load our predictions
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not pred_path.exists():
        raise HTTPException(status_code=404, detail="No predictions file found")

    preds = pd.read_csv(pred_path)
    for col in ["win_prob", "top10_prob"]:
        if col in preds.columns:
            preds[col] = pd.to_numeric(preds[col], errors="coerce")
    preds = preds.dropna(subset=["win_prob"])

    # Load DG pre-tournament probabilities
    dg_path = DG_DIR / f"dg_pre_tournament_{tid}.csv"
    if not dg_path.exists():
        dg_path = DG_DIR / "dg_pre_tournament_latest.csv"
    if not dg_path.exists():
        raise HTTPException(status_code=404, detail="No DG pre-tournament file found")

    dg = pd.read_csv(dg_path)
    if "model" in dg.columns:
        dg = dg[dg["model"] == "baseline"]
    dg = dg.dropna(subset=["win"])

    tournament_name = str(dg["event_name"].iloc[0]) if "event_name" in dg.columns and len(dg) > 0 else ""

    # Sort-key normalization: both files use "Last, First" — alphabetise tokens so format
    # differences (comma vs no comma, capitalisation) don't block the join
    def _name_key(n: str) -> str:
        return " ".join(sorted(str(n).replace(",", "").lower().split()))

    preds["_key"] = preds["player_name"].apply(_name_key)
    dg["_key"]    = dg["player_name"].apply(_name_key)

    merged = preds.merge(dg[["_key", "win", "top_10"]], on="_key", how="inner")

    if len(merged) < 5:
        raise HTTPException(status_code=404, detail="Not enough players matched between our model and DG")

    # Spearman ρ per market
    markets: list[dict] = []
    for our_col, dg_col, label in [
        ("win_prob",   "win",    "Win"),
        ("top10_prob", "top_10", "Top 10"),
    ]:
        if our_col in merged.columns:
            sub = merged[[our_col, dg_col]].dropna()
            if len(sub) >= 5:
                rho, _ = spearmanr(sub[our_col], sub[dg_col])
                markets.append({"market": label, "spearman_rho": round(float(rho), 3)})

    overall_rho = markets[0]["spearman_rho"] if markets else None

    # Our top 10 by win_prob
    our_top10 = [
        {"player": str(r["player_name"]).strip(), "prob": round(float(r["win_prob"]) * 100, 1)}
        for _, r in preds.sort_values("win_prob", ascending=False).head(10).iterrows()
    ]

    # DG top 10 by win
    dg_top10 = [
        {"player": str(r["player_name"]).strip(), "prob": round(float(r["win"]) * 100, 1)}
        for _, r in dg.sort_values("win", ascending=False).head(10).iterrows()
    ]

    # Disagreements — adaptive threshold: at least 2pp, or 75th-percentile of abs diffs
    merged["our_win_pct"] = merged["win_prob"] * 100
    merged["dg_win_pct"]  = merged["win"] * 100
    merged["diff_pp"]     = merged["our_win_pct"] - merged["dg_win_pct"]
    thresh = max(2.0, float(merged["diff_pp"].abs().quantile(0.75)))

    disagreements: list[dict] = []
    for _, r in (
        merged[merged["diff_pp"].abs() >= thresh]
        .sort_values("diff_pp", key=abs, ascending=False)
        .head(10)
        .iterrows()
    ):
        diff = float(r["diff_pp"])
        t10  = r.get("top10_prob")
        dt10 = r.get("top_10")
        disagreements.append({
            "player_name": str(r["player_name"]).strip(),
            "our_win_pct": round(float(r["our_win_pct"]), 1),
            "dg_win_pct":  round(float(r["dg_win_pct"]),  1),
            "diff_pp":     round(diff, 1),
            "our_top10":   round(float(t10)  * 100, 1) if pd.notna(t10)  else None,
            "dg_top10":    round(float(dt10) * 100, 1) if pd.notna(dt10) else None,
            "direction":   "higher" if diff > 0 else "lower",
        })

    # Full ranked player list for the side-by-side comparison table
    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    merged_sorted = merged.sort_values("win_prob", ascending=False).reset_index(drop=True)
    merged_sorted["our_rank"] = merged_sorted.index + 1
    dg_sorted = dg.sort_values("win", ascending=False).reset_index(drop=True)
    dg_sorted["dg_rank"] = dg_sorted.index + 1
    dg_rank_map = {_name_key(str(r["player_name"])): int(r["dg_rank"]) for _, r in dg_sorted.iterrows()}

    players_list: list[dict] = []
    for _, r in merged_sorted.iterrows():
        our_rank = int(r["our_rank"])
        dg_rank  = dg_rank_map.get(r["_key"])
        delta    = (dg_rank - our_rank) if dg_rank else None
        our_win  = _safe(r.get("win_prob"))
        our_t10  = _safe(r.get("top10_prob"))
        dg_win   = _safe(r.get("win"))
        dg_t10   = _safe(r.get("top_10"))
        players_list.append({
            "player":    _flip(str(r["player_name"])),
            "our_rank":  our_rank,
            "dg_rank":   dg_rank,
            "delta":     delta,
            "our_win":   round(float(our_win) * 100, 1) if our_win else None,
            "dg_win":    round(float(dg_win)  * 100, 1) if dg_win  else None,
            "our_top10": round(float(our_t10) * 100, 1) if our_t10 else None,
            "dg_top10":  round(float(dg_t10)  * 100, 1) if dg_t10  else None,
        })

    return {
        "tournament_id":        tid,
        "tournament_name":      tournament_name,
        "players_compared":     len(merged),
        "overall_spearman_rho": overall_rho,
        "markets":              markets,
        "our_top10":            our_top10,
        "dg_top10":             dg_top10,
        "disagreements":        disagreements,
        "players":              players_list,
    }


@app.get("/api/lineup")
def get_lineup() -> dict:
    """
    Weekly lineup recommendation from strategy_reasoning.json,
    merged with latest prediction probabilities.
    """
    tid = _get_tournament_id()
    sr_path = OUTPUTS_DIR / "strategy_reasoning.json"
    if not sr_path.exists():
        return {"tournament_id": tid, "picks": [], "weekly_narrative": ""}

    with open(sr_path) as f:
        sr = json.load(f)

    # Load predictions for prob columns
    prob_map: dict = {}
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        preds = pd.read_csv(pred_path)
        for col in ["win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob",
                    "world_rank", "odds_to_win", "form_trend", "season_sg_total",
                    "dk_odds_direction", "model_vs_vegas_edge"]:
            if col not in preds.columns:
                preds[col] = None
        for _, row in preds.iterrows():
            name = str(row["player_name"]).strip()
            prob_map[name] = {c: _safe(row[c]) for c in [
                "win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob",
                "world_rank", "odds_to_win", "form_trend", "season_sg_total",
                "dk_odds_direction", "model_vs_vegas_edge",
            ]}

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    lineup_names: list[str] = sr.get("lineup", [])
    players_data: dict = sr.get("players", {})

    picks = []
    for raw_name in lineup_names:
        sr_info = players_data.get(raw_name, {})
        preds_info = prob_map.get(raw_name, {})
        wp  = preds_info.get("win_prob")
        t10 = preds_info.get("top10_prob")
        picks.append({
            "player_name":   _flip(raw_name),
            "recommendation": sr_info.get("recommendation", ""),
            "tier":          sr_info.get("tier", ""),
            "uses_left":     sr_info.get("uses_left"),
            "in_field":      sr_info.get("in_field", True),
            "narrative":     sr_info.get("narrative", ""),
            "this_week_ev":  sr_info.get("this_week_ev"),
            "win_prob":      round(float(wp) * 100, 1) if wp is not None else None,
            "top10_prob":    round(float(t10) * 100, 1) if t10 is not None else None,
            "world_rank":    preds_info.get("world_rank"),
            "odds_to_win":   _fmt_odds(preds_info.get("odds_to_win")),
            "form_trend":    _safe(preds_info.get("form_trend")),
            "season_sg":     _safe(preds_info.get("season_sg_total")),
            "drift":         str(preds_info.get("dk_odds_direction") or ""),
        })

    return {
        "tournament_id":    tid,
        "tournament":       sr.get("tournament", ""),
        "generated_at":     sr.get("generated_at", ""),
        "weekly_narrative": sr.get("weekly_narrative", ""),
        "picks":            picks,
    }


_tee_times_cache: dict = {"ts": 0.0, "data": None}
_TEE_TIMES_TTL = 300  # 5 minutes — tee times don't change often

_course_cache: dict = {"ts": 0.0, "data": None}
_COURSE_TTL = 300

_PGAT_URL = "https://orchestrator.pgatour.com/graphql"
_PGAT_HEADERS = {
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "content-type": "application/json",
}
_PGAT_COURSE_STATS_Q = """
query CourseStats($tournamentId: ID!) {
  courseStats(tournamentId: $tournamentId) {
    courses {
      courseId courseName par yardage
      roundHoleStats {
        roundNum
        holeStats {
          ... on CourseHoleStats {
            courseHoleNum parValue yards scoringAverage
          }
        }
      }
    }
  }
}
"""
_PGAT_HOLE_STATS_Q = """
query CourseHolesStats($tournamentId: ID!, $courseId: ID!) {
  courseHolesStats(tournamentId: $tournamentId, courseId: $courseId) {
    holeNum scoringAverage birdiesPercent bogeysPercent
  }
}
"""

@app.get("/api/tee-times")
def get_tee_times() -> dict:
    """
    Tee times for the current round, pulled live from DG /field-updates.
    Cached 5 minutes to avoid hammering DG. Falls back to CSV if DG is unavailable.
    """
    import sys as _sys
    _sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.scrapers.dg_client import dg_get as _dg_get  # type: ignore

    tid = _get_tournament_id()

    # Return cached result if fresh
    if time.time() - _tee_times_cache["ts"] < _TEE_TIMES_TTL and _tee_times_cache["data"]:
        cached = _tee_times_cache["data"]
        if cached.get("tournament_id") == tid:
            return cached

    # Fetch from DG — try pga (current week) first
    raw = None
    for _tour in ("pga", "upcoming_pga"):
        try:
            _r = _dg_get("/field-updates", {"tour": _tour, "file_format": "json"})
            if _r.get("field"):
                raw = _r
                break
        except Exception:
            pass

    if not raw:
        return {"tournament_id": tid, "round": None, "groups": []}

    current_round = int(raw.get("current_round") or 1)
    field = raw.get("field", [])

    # Build rows: one per player, for current_round
    rows = []
    for p in field:
        for tt in p.get("teetimes", []):
            if int(tt.get("round_num", 0)) != current_round:
                continue
            raw_tt = str(tt.get("teetime", "")).strip()  # "2026-06-11 14:27" local
            try:
                from datetime import datetime as _dt
                local_dt = _dt.strptime(raw_tt, "%Y-%m-%d %H:%M")
                tee_time_str = local_dt.strftime("%-I:%M %p")
                tee_time_local = local_dt.isoformat()
            except Exception:
                tee_time_str = raw_tt
                tee_time_local = raw_tt
            rows.append({
                "player_name": p.get("player_name", ""),
                "player_num":  p.get("player_num"),
                "owgr_rank":   p.get("owgr_rank"),
                "tee_time_str": tee_time_str,
                "tee_time_local": tee_time_local,
                "start_tee": tt.get("start_hole", 1),
            })

    round_num = current_round

    # Load model ranks from predictions CSV
    rank_map: dict = {}
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        preds = pd.read_csv(pred_path)
        preds = preds.sort_values("win_prob", ascending=False).reset_index(drop=True)
        preds["model_rank"] = preds.index + 1
        for col in ["win_prob", "top10_prob", "world_rank", "form_trend",
                    "cut_prob", "model_vs_vegas_edge", "dk_odds_direction"]:
            if col not in preds.columns:
                preds[col] = None
        def _flip_name(n: str) -> str:
            s = str(n).strip()
            return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s
        for _, row in preds.iterrows():
            raw_name = str(row["player_name"]).strip()
            entry = {
                "model_rank":  int(row["model_rank"]),
                "win_prob":    _safe(row["win_prob"]),
                "top10_prob":  _safe(row["top10_prob"]),
                "world_rank":  _safe(row["world_rank"]),
                "form_trend":  _safe(row["form_trend"]),
                "cut_prob":    _safe(row["cut_prob"]),
                "edge":        _safe(row["model_vs_vegas_edge"]),
                "drift":       str(row.get("dk_odds_direction") or ""),
            }
            rank_map[raw_name] = entry
            rank_map[_flip_name(raw_name)] = entry

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    # Group by tee time
    groups: dict[str, list] = {}
    for row in rows:
        tt = str(row.get("tee_time_str") or row.get("tee_time_local") or "").strip()
        if not tt or tt == "nan":
            tt = "TBD"
        raw_name = str(row.get("player_name", "")).strip()
        display  = _flip(raw_name)
        pinfo    = rank_map.get(raw_name, {})
        wp  = pinfo.get("win_prob")
        t10 = pinfo.get("top10_prob")
        world_rank = pinfo.get("world_rank") or _safe(row.get("owgr_rank"))
        player = {
            "name":        display,
            "start_tee":   row.get("start_tee"),
            "model_rank":  pinfo.get("model_rank"),
            "world_rank":  world_rank,
            "win_prob":    round(float(wp) * 100, 1) if wp is not None else None,
            "top10_prob":  round(float(t10) * 100, 1) if t10 is not None else None,
            "form_trend":  pinfo.get("form_trend"),
            "edge":        pinfo.get("edge"),
            "drift":       pinfo.get("drift", ""),
        }
        groups.setdefault(tt, []).append(player)

    # Sort by tee time string, then sort players within each group by model rank
    def _tt_sort_key(tt: str) -> tuple:
        import re
        m = re.search(r"(\d+):(\d+)\s*(AM|PM)", tt, re.IGNORECASE)
        if not m:
            return (99, 0)
        h, mn, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if period == "PM" and h != 12:
            h += 12
        if period == "AM" and h == 12:
            h = 0
        return (h, mn)

    sorted_groups = [
        {
            "tee_time": tt,
            "players":  sorted(players, key=lambda p: p["model_rank"] or 999),
        }
        for tt, players in sorted(groups.items(), key=lambda x: _tt_sort_key(x[0]))
    ]

    result = {"tournament_id": tid, "round": round_num, "groups": sorted_groups}
    _tee_times_cache["ts"]   = time.time()
    _tee_times_cache["data"] = result
    return result


@app.get("/api/course")
def get_course() -> dict:
    """Hole-by-hole course layout for the current tournament."""
    tid = _get_tournament_id()

    # Try course_stats JSON first (live data)
    cs_path = DATA_DIR / "live" / f"course_stats_{tid}.json"
    if cs_path.exists():
        try:
            with open(cs_path) as f:
                cs = json.load(f)
            def _parse_diff(v) -> float | None:
                try:
                    return float(str(v).replace("+", ""))
                except Exception:
                    return None

            def _parse_pct(v) -> float | None:
                try:
                    return float(str(v).replace("%", ""))
                except Exception:
                    return None

            holes = []
            for i, h in enumerate(cs.get("holes", [])):
                sa = h.get("scoringAverage") or h.get("scoring_avg")
                holes.append({
                    "hole_num":        h.get("holeNum") or h.get("holeNumber") or h.get("hole_num") or (i + 1),
                    "hole_par":        h.get("par") or h.get("hole_par"),
                    "hole_yards":      h.get("yardage") or h.get("hole_yards"),
                    "scoring_avg":     _safe(_parse_diff(sa)),
                    "scoring_diff":    _safe(_parse_diff(sa)),
                    "difficulty_rank": _safe(h.get("difficulty_rank")),
                    "birdies":         _safe(_parse_pct(h.get("birdiesPercent") or h.get("birdies"))),
                    "bogeys":          _safe(_parse_pct(h.get("bogeysPercent") or h.get("bogeys"))),
                })
            # Supplement with CSV data (par/yards per hole) if available
            cc_path = DATA_DIR / "course_characteristics" / "all_courses_2026.csv"
            if cc_path.exists():
                try:
                    csv_df = pd.read_csv(cc_path)
                    csv_tid = csv_df[csv_df["tournament_id"].astype(str).str.upper() == tid.upper()]
                    if not csv_tid.empty:
                        csv_map = {int(r["hole_num"]): r for _, r in csv_tid.iterrows()}
                        for h in holes:
                            hn = h.get("hole_num")
                            if hn and int(hn) in csv_map:
                                r = csv_map[int(hn)]
                                h["hole_par"]   = h["hole_par"]   or _safe(r.get("hole_par"))
                                h["hole_yards"] = h["hole_yards"] or _safe(r.get("hole_yards"))
                                h["difficulty_rank"] = h["difficulty_rank"] or _safe(r.get("difficulty_rank"))
                except Exception:
                    pass

            return {
                "tournament_id": tid,
                "course_name":   cs.get("course_name", ""),
                "par":           cs.get("par"),
                "yardage":       cs.get("yardage"),
                "holes":         holes,
            }
        except Exception:
            pass

    # Fall back: call PGA Tour GraphQL directly (5-min cache)
    now = time.time()
    cached = _course_cache.get("data")
    if cached and now - _course_cache["ts"] < _COURSE_TTL and cached.get("tournament_id") == tid:
        return cached

    def _parse_diff(v) -> float | None:
        try:
            return float(str(v).replace("+", ""))
        except Exception:
            return None

    def _parse_pct(v) -> float | None:
        try:
            return float(str(v).replace("%", ""))
        except Exception:
            return None

    try:
        import requests as _req
        r1 = _req.post(_PGAT_URL, headers=_PGAT_HEADERS, json={
            "operationName": "CourseStats",
            "query": _PGAT_COURSE_STATS_Q,
            "variables": {"tournamentId": tid},
        }, timeout=10)
        r1.raise_for_status()
        courses = r1.json().get("data", {}).get("courseStats", {}).get("courses", [])
        if not courses:
            raise ValueError("no courses")
        course = courses[0]
        course_id   = course["courseId"]
        course_name = course.get("courseName", "")
        par         = _safe(course.get("par"))
        _yrd = str(course.get("yardage") or "").replace(",", "")
        yardage     = int(_yrd) if _yrd.isdigit() else None

        # Build par/yards lookup from roundHoleStats (historical hole data)
        hole_info: dict[int, dict] = {}
        for rnd in course.get("roundHoleStats", []):
            for h in rnd.get("holeStats", []):
                hn = h.get("courseHoleNum")
                if hn is None:
                    continue  # skip SummaryRow entries
                hole_info[int(hn)] = {
                    "hole_par":   _safe(h.get("parValue")),
                    "hole_yards": _safe(h.get("yards")),
                }
            break  # only need one round for structural data

        r2 = _req.post(_PGAT_URL, headers=_PGAT_HEADERS, json={
            "operationName": "CourseHolesStats",
            "query": _PGAT_HOLE_STATS_Q,
            "variables": {"tournamentId": tid, "courseId": course_id},
        }, timeout=10)
        r2.raise_for_status()
        raw_holes = r2.json().get("data", {}).get("courseHolesStats", [])

        holes = []
        for i, h in enumerate(raw_holes):
            hn = h.get("holeNum") or (i + 1)
            info = hole_info.get(int(hn), {})
            sa = h.get("scoringAverage")
            holes.append({
                "hole_num":        hn,
                "hole_par":        info.get("hole_par"),
                "hole_yards":      info.get("hole_yards"),
                "scoring_avg":     _safe(_parse_diff(sa)),
                "scoring_diff":    _safe(_parse_diff(sa)),
                "difficulty_rank": None,
                "birdies":         _safe(_parse_pct(h.get("birdiesPercent"))),
                "bogeys":          _safe(_parse_pct(h.get("bogeysPercent"))),
            })

        result = {
            "tournament_id": tid,
            "course_name":   course_name,
            "par":           par,
            "yardage":       yardage,
            "holes":         holes,
        }
        _course_cache["ts"]   = now
        _course_cache["data"] = result
        return result
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"No course data for {tid}")


@app.get("/api/matchups")
def get_matchups(
    market: str = "tournament",  # "tournament" | "round"
    search: str = "",
    pos_ev_only: bool = False,
) -> dict:
    """
    H2H matchup betting lines from DataGolf.
    market=tournament → dg_tourn_matchups_{tid}.csv
    market=round      → dg_matchups_{tid}.csv
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    if market == "tournament":
        path = DG_DIR / f"dg_tourn_matchups_{tid}.csv"
    else:
        path = DG_DIR / f"dg_matchups_{tid}.csv"
        if not path.exists():
            path = DG_DIR / "dg_matchups_latest.csv"

    if not path.exists():
        return {"tournament_id": tid, "market": market, "matchups": [], "books": [], "updated": None}

    raw = pd.read_csv(path)
    raw["book"] = raw["book"].astype(str).str.title()

    dg_rows    = raw[raw["is_dg_model"].astype(str).str.lower() == "true"].copy()
    book_rows  = raw[raw["is_dg_model"].astype(str).str.lower() == "false"].copy()

    # DG model probs keyed by (p1, p2)
    dg_probs: dict[tuple, dict] = {}
    for _, r in dg_rows.iterrows():
        key = (str(r["p1_name"]), str(r["p2_name"]))
        dg_probs[key] = {
            "dg_p1": _safe(r.get("p1_novig")),
            "dg_p2": _safe(r.get("p2_novig")),
        }

    # Preferred book order
    BOOK_PREF = ["Draftkings", "Fanduel", "Bet365", "Pinnacle", "Betmgm", "Caesars", "Bovada", "Betonline", "Unibet"]
    avail_books = [b for b in BOOK_PREF if b in book_rows["book"].unique()]
    avail_books += [b for b in book_rows["book"].unique() if b not in BOOK_PREF]

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    def _to_dec(o) -> float | None:
        try:
            v = float(str(o).replace("+", ""))
            return (1 + v / 100) if v > 0 else (1 + 100 / abs(v))
        except Exception:
            return None

    # Build one entry per unique (p1, p2) pair
    pairs = dg_rows[["p1_name", "p2_name"]].drop_duplicates()
    if search.strip():
        q = search.strip().lower()
        pairs = pairs[
            pairs["p1_name"].str.lower().str.contains(q, na=False) |
            pairs["p2_name"].str.lower().str.contains(q, na=False)
        ]

    matchups = []
    for _, pr in pairs.iterrows():
        p1, p2 = str(pr["p1_name"]), str(pr["p2_name"])
        probs  = dg_probs.get((p1, p2), {"dg_p1": None, "dg_p2": None})
        dg_p1  = probs["dg_p1"] or 0.5
        dg_p2  = probs["dg_p2"] or 0.5

        pair_books = book_rows[(book_rows["p1_name"] == p1) & (book_rows["p2_name"] == p2)]
        books_data: dict[str, dict] = {}
        has_pos_ev = False
        for _, br in pair_books.iterrows():
            bk = str(br["book"])
            d1 = _to_dec(br.get("p1_odds"))
            d2 = _to_dec(br.get("p2_odds"))
            ev1 = round((dg_p1 * d1 - 1) * 100, 1) if d1 else None
            ev2 = round((dg_p2 * d2 - 1) * 100, 1) if d2 else None
            if (ev1 and ev1 > 0) or (ev2 and ev2 > 0):
                has_pos_ev = True
            books_data[bk] = {
                "p1_odds": _fmt_odds(br.get("p1_odds")),
                "p2_odds": _fmt_odds(br.get("p2_odds")),
                "p1_ev":   ev1,
                "p2_ev":   ev2,
            }

        if pos_ev_only and not has_pos_ev:
            continue

        ties_val = raw[(raw["p1_name"] == p1) & (raw["p2_name"] == p2)]["ties"].iloc[0] \
            if "ties" in raw.columns and not raw[(raw["p1_name"] == p1) & (raw["p2_name"] == p2)].empty else ""

        matchups.append({
            "p1":    _flip(p1),
            "p2":    _flip(p2),
            "dg_p1": round(dg_p1 * 100, 1),
            "dg_p2": round(dg_p2 * 100, 1),
            "ties":  str(ties_val),
            "books": books_data,
        })

    updated = None
    if "last_updated" in raw.columns and not raw["last_updated"].dropna().empty:
        updated = str(raw["last_updated"].dropna().iloc[0])[:16]

    return {
        "tournament_id": tid,
        "market":        market,
        "books":         avail_books,
        "matchups":      matchups,
        "updated":       updated,
    }


@app.get("/api/3ball")
def get_3ball() -> dict:
    """3-ball pairings with tee times from DuckDB dg_matchups table."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    try:
        import duckdb
        db_path = DATA_DIR / "golf_data.db"
        with duckdb.connect(str(db_path), read_only=True) as conn:
            df = conn.execute(
                "SELECT event_name, round, group_num, teetime, start_hole, "
                "p1_name, p1_odds, p2_name, p2_odds, p3_name, p3_odds, last_update "
                "FROM dg_matchups ORDER BY teetime, group_num"
            ).df()
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return {"tournament_id": tid, "pairings": [], "updated": None}

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    pairings = []
    for _, r in df.iterrows():
        teetime_raw = str(r.get("teetime", ""))
        teetime = teetime_raw.split("T")[-1][:5] if "T" in teetime_raw else teetime_raw[:5]
        p3_name = str(r.get("p3_name", "")).strip()
        p3_odds = r.get("p3_odds")
        is_tie  = p3_name in ("-1", "Tie", "", "nan", "None")
        pairings.append({
            "round":    _safe(r.get("round")),
            "group":    _safe(r.get("group_num")),
            "teetime":  teetime,
            "p1":       _flip(str(r.get("p1_name", ""))),
            "p1_odds":  _fmt_odds(r.get("p1_odds")),
            "p2":       _flip(str(r.get("p2_name", ""))),
            "p2_odds":  _fmt_odds(r.get("p2_odds")),
            "p3":       None if is_tie else _flip(p3_name),
            "p3_odds":  None if is_tie else _fmt_odds(p3_odds),
        })

    updated = None
    if "last_update" in df.columns and not df["last_update"].dropna().empty:
        updated = str(df["last_update"].dropna().iloc[0])[:16]

    return {"tournament_id": tid, "pairings": pairings, "updated": updated}


@app.get("/api/odds/explorer")
def get_odds_explorer(market: str = "top_10") -> dict:
    """
    Full odds explorer: per-player per-book odds + EV (DG model prob × decimal − 1).
    market: top_10 | top_20 | top_5 | win | make_cut
    """
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    path = DG_DIR / f"dg_outrights_{tid}.csv"
    if not path.exists():
        return {"tournament_id": tid, "market": market, "players": [], "books": []}

    raw = pd.read_csv(path)
    raw["book"] = raw["book"].astype(str).str.title()

    model_rows = raw[
        (raw["market"].astype(str).str.lower() == market.lower()) &
        (raw["is_dg_model"].astype(str).str.lower() == "true")
    ].copy()
    book_rows = raw[
        (raw["market"].astype(str).str.lower() == market.lower()) &
        (raw["is_dg_model"].astype(str).str.lower() == "false")
    ].copy()

    BOOK_PREF = ["Draftkings", "Fanduel", "Pointsbet", "Bet365", "Betonline",
                 "Caesars", "Unibet", "Bovada", "Betmgm", "Pinnacle", "Betcris"]
    avail = sorted(book_rows["book"].unique().tolist())
    books = [b for b in BOOK_PREF if b in avail] + [b for b in avail if b not in BOOK_PREF]

    dg_prob_map = dict(zip(model_rows["player_name"], model_rows["implied_prob"].astype(float)))

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    def _to_dec(o) -> float | None:
        try:
            v = float(str(o).replace("+", ""))
            return (1 + v / 100) if v > 0 else (1 + 100 / abs(v))
        except Exception:
            return None

    # Sort players by DG model prob descending
    player_order = (
        model_rows.sort_values("implied_prob", ascending=False)["player_name"].tolist()
    )
    for p in book_rows["player_name"].unique():
        if p not in player_order:
            player_order.append(p)

    players = []
    for pn in player_order:
        dg_p = dg_prob_map.get(pn)
        odds_per_book: dict[str, dict] = {}
        any_pos = False
        for bk in books:
            bk_row = book_rows[(book_rows["player_name"] == pn) & (book_rows["book"] == bk)]
            if bk_row.empty:
                odds_per_book[bk] = {"odds": None, "ev": None}
                continue
            o_raw = bk_row.iloc[0]["odds_american"]
            dec   = _to_dec(o_raw)
            ev    = round((float(dg_p) * dec - 1) * 100, 1) if (dg_p is not None and dec) else None
            if ev and ev > 0:
                any_pos = True
            odds_per_book[bk] = {
                "odds": _fmt_odds(o_raw),
                "ev":   ev,
            }
        players.append({
            "player":   _flip(pn),
            "dg_prob":  round(float(dg_p) * 100, 1) if dg_p is not None else None,
            "books":    odds_per_book,
            "has_pos_ev": any_pos,
        })

    updated = None
    if "last_updated" in raw.columns and not raw["last_updated"].dropna().empty:
        updated = str(raw["last_updated"].dropna().iloc[0])[:16]

    return {
        "tournament_id": tid,
        "market":        market,
        "books":         books,
        "players":       players,
        "updated":       updated,
    }


@app.get("/api/players/list")
def get_player_list() -> dict:
    """All players in the current field, sorted alphabetically as 'First Last'."""
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not pred_path.exists():
        raise HTTPException(status_code=404, detail="No predictions file found")

    try:
        df = pd.read_csv(pred_path, usecols=["player_name"])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read predictions")

    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    names = sorted(set(df["player_name"].dropna().apply(lambda n: _flip(str(n)))))
    return {"players": names}


@app.get("/api/players/profile")
def get_player_profile(player: str) -> dict:
    """
    Full player profile merged from all data sources.
    `player` param is 'First Last' format; internally flipped to 'Last, First' for CSV lookups.
    """
    tid = _get_tournament_id()

    def _find_row(df: pd.DataFrame, col: str = "player_name") -> pd.Series | None:
        lf = _flip_to_last_first(player)
        fl = _flip_to_first_last(lf)
        target_keys = {_name_key(lf), _name_key(fl)}
        for _, row in df.iterrows():
            if _name_key(str(row[col])) in target_keys:
                return row
        return None

    # ── Our model (latest_predictions.csv) ───────────────────────────────────
    our_model: dict[str, Any] = {}
    win_rank: int | None = None
    top10_rank: int | None = None

    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        try:
            preds = pd.read_csv(pred_path)
            for col in ["win_prob", "top10_prob", "cut_prob", "world_rank",
                        "season_sg_total", "form_trend", "model_vs_vegas_edge", "odds_to_win"]:
                if col in preds.columns:
                    preds[col] = pd.to_numeric(preds[col], errors="coerce")

            # Compute field ranks (plain float — Int64 is not JSON-serializable)
            if "win_prob" in preds.columns:
                preds["_win_rank"] = preds["win_prob"].rank(ascending=False, method="min")
            if "top10_prob" in preds.columns:
                preds["_top10_rank"] = preds["top10_prob"].rank(ascending=False, method="min")

            row = _find_row(preds)
            if row is not None:
                for col in ["win_prob", "top10_prob", "cut_prob", "world_rank",
                            "season_sg_total", "form_trend", "model_vs_vegas_edge",
                            "odds_to_win", "dk_odds_direction"]:
                    our_model[col] = _safe(row.get(col)) if col in preds.columns else None
                win_rank  = int(row["_win_rank"])  if "_win_rank"  in preds.columns and pd.notna(row.get("_win_rank"))  else None
                top10_rank = int(row["_top10_rank"]) if "_top10_rank" in preds.columns and pd.notna(row.get("_top10_rank")) else None
        except Exception:
            pass

    our_model["win_rank"]   = win_rank
    our_model["top10_rank"] = top10_rank

    # ── Strategy reasoning (uses_left, badge, recommendation, EV) ────────────
    our_model["uses_remaining"] = 3
    our_model["badge"]          = ""
    our_model["recommendation"] = ""
    our_model["this_week_ev"]   = None

    def _flip_to_first_last_safe(n: str) -> str:
        return _flip_to_first_last(str(n).strip())

    sr_path = OUTPUTS_DIR / "strategy_reasoning.json"
    if sr_path.exists():
        try:
            with open(sr_path) as f:
                sr = json.load(f)
            fl_player = _flip_to_first_last(_flip_to_last_first(player))
            for raw_name, info in sr.get("players", {}).items():
                display = _flip_to_first_last(str(raw_name).strip())
                if _name_key(display) == _name_key(fl_player):
                    rec = info.get("recommendation", "")
                    uses = info.get("uses_left", 3)
                    our_model["recommendation"] = rec
                    our_model["uses_remaining"] = uses if uses is not None else 3
                    badge = "MAXED" if uses == 0 else ("USE" if "USE" in str(rec).upper() else ("SAVE" if "SAVE" in str(rec).upper() else ""))
                    our_model["badge"] = badge
                    ev = info.get("this_week_ev")
                    our_model["this_week_ev"] = int(ev) if ev is not None else None
                    break
        except Exception:
            pass

    # ── Explanation ───────────────────────────────────────────────────────────
    our_model["explanation"] = ""
    exp_path = OUTPUTS_DIR / "player_explanations.csv"
    if exp_path.exists():
        try:
            exp_df = pd.read_csv(exp_path)
            row = _find_row(exp_df)
            if row is not None:
                our_model["explanation"] = str(row.get("explanation", ""))
        except Exception:
            pass

    # ── DG pre-tournament prediction ──────────────────────────────────────────
    dg_prediction: dict | None = None
    dg_path = DG_DIR / f"dg_pre_tournament_{tid}.csv"
    if not dg_path.exists():
        dg_path = DG_DIR / "dg_pre_tournament_latest.csv"
    if dg_path.exists():
        try:
            dg_df = pd.read_csv(dg_path)
            dg_row = _find_row(dg_df)
            if dg_row is not None:
                dg_prediction = {
                    col: _safe(pd.to_numeric(dg_row.get(col), errors="coerce"))
                    for col in ["win", "top_5", "top_10", "top_20", "make_cut"]
                    if col in dg_df.columns
                }
                # Merge in course-fit adjusted predictions
                cf_path = DG_DIR / "dg_course_fit_latest.csv"
                if cf_path.exists():
                    try:
                        cf_df = pd.read_csv(cf_path)
                        cf_row = _find_row(cf_df)
                        if cf_row is not None:
                            for col in ["bhf_win", "baseline_win", "course_fit_delta", "course_fit_delta_pct"]:
                                if col in cf_df.columns:
                                    dg_prediction[col] = _safe(pd.to_numeric(cf_row.get(col), errors="coerce"))
                    except Exception:
                        pass
        except Exception:
            pass

    # ── DG decompositions ─────────────────────────────────────────────────────
    decompositions: dict | None = None
    dec_path = DG_DIR / f"dg_decompositions_{tid}.csv"
    if not dec_path.exists():
        dec_path = DG_DIR / "dg_decompositions_latest.csv"
    if dec_path.exists():
        try:
            dec_df = pd.read_csv(dec_path)
            dec_row = _find_row(dec_df)
            if dec_row is not None:
                dec_cols = [
                    "course_history_adjustment", "total_course_history_adjustment",
                    "driving_accuracy_adjustment", "driving_distance_adjustment",
                    "timing_adjustment", "age_adjustment",
                    "strokes_gained_category_adjustment", "total_fit_adjustment",
                    "true_sg_adjustments", "course_fit_delta",
                ]
                decompositions = {
                    col: _safe(pd.to_numeric(dec_row.get(col), errors="coerce"))
                    for col in dec_cols
                    if col in dec_df.columns
                }
        except Exception:
            pass

    # ── DG skill ratings ──────────────────────────────────────────────────────
    skill_ratings: dict | None = None
    sk_path = DG_DIR / "dg_skill_ratings_latest.csv"
    if sk_path.exists():
        try:
            sk_df = pd.read_csv(sk_path)
            sk_row = _find_row(sk_df)
            if sk_row is not None:
                skill_ratings = {
                    "total": _safe(pd.to_numeric(sk_row.get("dg_skill_total"), errors="coerce")),
                    "ott":   _safe(pd.to_numeric(sk_row.get("dg_skill_ott"),   errors="coerce")),
                    "app":   _safe(pd.to_numeric(sk_row.get("dg_skill_app"),   errors="coerce")),
                    "arg":   _safe(pd.to_numeric(sk_row.get("dg_skill_arg"),   errors="coerce")),
                    "putt":  _safe(pd.to_numeric(sk_row.get("dg_skill_putt"),  errors="coerce")),
                    "dist":  _safe(pd.to_numeric(sk_row.get("dg_skill_dist"),  errors="coerce")),
                    "acc":   _safe(pd.to_numeric(sk_row.get("dg_skill_acc"),   errors="coerce")),
                }
        except Exception:
            pass

    # ── DG approach skill ─────────────────────────────────────────────────────
    approach_skill: dict | None = None
    ap_path = DG_DIR / "dg_approach_skill_latest.csv"
    if ap_path.exists():
        try:
            ap_df = pd.read_csv(ap_path)
            ap_row = _find_row(ap_df)
            if ap_row is not None:
                def _band(sg_col: str, prox_col: str) -> dict:
                    return {
                        "sg":   _safe(pd.to_numeric(ap_row.get(sg_col),   errors="coerce")),
                        "prox": _safe(pd.to_numeric(ap_row.get(prox_col), errors="coerce")),
                    }
                approach_skill = {
                    "50_100":       _band("50_100_fw_sg_per_shot",      "50_100_fw_proximity_per_shot"),
                    "100_150":      _band("100_150_fw_sg_per_shot",     "100_150_fw_proximity_per_shot"),
                    "150_200":      _band("150_200_fw_sg_per_shot",     "150_200_fw_proximity_per_shot"),
                    "over_200":     _band("over_200_fw_sg_per_shot",    "over_200_fw_proximity_per_shot"),
                    "rgh_under_150": _band("under_150_rgh_sg_per_shot", "under_150_rgh_proximity_per_shot"),
                    "rgh_over_150":  _band("over_150_rgh_sg_per_shot",  "over_150_rgh_proximity_per_shot"),
                    "overall_prox":  _safe(pd.to_numeric(ap_row.get("approach_skill_proximity"), errors="coerce")),
                }
        except Exception:
            pass

    # ── Betting profile ───────────────────────────────────────────────────────
    betting_profile: dict | None = None
    bp_path = DATA_DIR / "betting_profiles" / f"betting_profiles_{tid}.csv"
    if not bp_path.exists():
        candidates = sorted(
            (DATA_DIR / "betting_profiles").glob("betting_profiles_R*.csv"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        bp_path = candidates[0] if candidates else None  # type: ignore[assignment]

    if bp_path and Path(bp_path).exists():
        try:
            bp_df = pd.read_csv(bp_path)
            bp_row = _find_row(bp_df)
            if bp_row is not None:
                betting_profile = {}
                # Numeric stats
                for col in ["sg_total", "sg_total_rank", "sg_ott", "sg_ott_rank",
                            "sg_app", "sg_app_rank", "sg_arg", "sg_arg_rank",
                            "sg_putt", "sg_putt_rank", "driving_distance", "driving_accuracy",
                            "fedex_rank", "fedex_points", "events_played",
                            "wins", "top_10s", "top_25s", "cuts_made"]:
                    betting_profile[col] = _safe(pd.to_numeric(bp_row.get(col), errors="coerce")) if col in bp_df.columns else None
                # String stats
                for col in ["gir_pct", "scrambling_pct"]:
                    betting_profile[col] = str(bp_row[col]) if col in bp_df.columns and str(bp_row.get(col, "")) not in ("nan", "None", "") else None
                # Rich text
                betting_profile["summary"] = str(bp_row["summary"]) if "summary" in bp_df.columns and str(bp_row.get("summary", "")) not in ("nan", "None", "") else None
                # Bullets: pipe-separated string → list
                raw_bullets = str(bp_row.get("bullets", "")) if "bullets" in bp_df.columns else ""
                betting_profile["bullets"] = [b.strip() for b in raw_bullets.split("|") if b.strip()] if raw_bullets not in ("nan", "None", "") else []
                # JSON arrays
                betting_profile["course_history_raw"] = str(bp_row["course_history"]) if "course_history" in bp_df.columns else None
                betting_profile["recent_results_raw"] = str(bp_row["recent_results"]) if "recent_results" in bp_df.columns else None
        except Exception:
            pass

    return {
        "player_name":   _flip_to_first_last(_flip_to_last_first(player)),
        "tournament_id": tid,
        "our_model":     our_model,
        "dg_prediction": dg_prediction,
        "decompositions": decompositions,
        "skill_ratings":  skill_ratings,
        "approach_skill": approach_skill,
        "betting_profile": betting_profile,
    }


@app.get("/api/players/synopsis")
def get_player_synopsis(player: str, force: bool = False) -> dict:
    """
    Generate an LLM-powered player analysis synopsis using all available stats.
    Cached per player per tournament for 6 hours. Pass force=true to regenerate.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set")

    tid = _get_tournament_id()
    slug = re.sub(r"[^a-z0-9]+", "_", player.lower()).strip("_")
    cache_dir = DATA_DIR / "player_synopses" / tid
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{slug}.json"

    # Return cached if fresh and not forced
    if not force and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
            age_h = (time.time() - cached.get("generated_ts", 0)) / 3600
            if age_h < 6:
                cached["cached"] = True
                return cached
        except Exception:
            pass

    # ── Gather stats ─────────────────────────────────────────────────────────
    def _find(df: pd.DataFrame, col: str = "player_name") -> pd.Series | None:
        lf = _flip_to_last_first(player)
        fl = _flip_to_first_last(lf)
        keys = {_name_key(lf), _name_key(fl)}
        for _, row in df.iterrows():
            if _name_key(str(row[col])) in keys:
                return row
        return None

    def _n(val) -> float | None:
        try:
            f = float(val)
            return None if pd.isna(f) else round(f, 4)
        except Exception:
            return None

    def _fmt(val, decimals=2, pct=False) -> str:
        v = _n(val)
        if v is None: return "N/A"
        if pct: return f"{v*100:.{decimals}f}%"
        return f"{v:+.{decimals}f}" if v >= 0 else f"{v:.{decimals}f}"

    stats: dict = {}

    # Model predictions
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if pred_path.exists():
        try:
            preds = pd.read_csv(pred_path)
            row = _find(preds)
            if row is not None:
                for col in ["win_prob", "top10_prob", "cut_prob", "world_rank",
                            "season_sg_total", "season_sg_ott", "season_sg_app",
                            "season_sg_arg", "season_sg_putt", "form_trend",
                            "model_vs_vegas_edge", "odds_to_win", "dg_win", "dg_top10",
                            "dg_make_cut"]:
                    stats[col] = _n(row.get(col)) if col in preds.columns else None
        except Exception:
            pass

    # DG pre-tournament
    dg_path = DG_DIR / f"dg_pre_tournament_{tid}.csv"
    if not dg_path.exists():
        dg_path = DG_DIR / "dg_pre_tournament_latest.csv"
    if dg_path.exists():
        try:
            dg_df = pd.read_csv(dg_path)
            row = _find(dg_df)
            if row is not None:
                for col in ["win", "top_5", "top_10", "top_20", "make_cut"]:
                    if col in dg_df.columns:
                        stats[f"dg_{col}"] = _n(row.get(col))
        except Exception:
            pass

    # DG decompositions
    dec_path = DG_DIR / f"dg_decompositions_{tid}.csv"
    if not dec_path.exists():
        dec_path = DG_DIR / "dg_decompositions_latest.csv"
    if dec_path.exists():
        try:
            dec_df = pd.read_csv(dec_path)
            row = _find(dec_df)
            if row is not None:
                for col in ["timing_adjustment", "total_fit_adjustment",
                            "total_course_history_adjustment", "driving_distance_adjustment",
                            "driving_accuracy_adjustment", "baseline_pred", "final_pred"]:
                    if col in dec_df.columns:
                        stats[col] = _n(row.get(col))
        except Exception:
            pass

    # DG skill ratings
    sk_path = DG_DIR / "dg_skill_ratings_latest.csv"
    if sk_path.exists():
        try:
            sk_df = pd.read_csv(sk_path)
            row = _find(sk_df)
            if row is not None:
                for col in ["dg_skill_total", "dg_skill_ott", "dg_skill_app",
                            "dg_skill_arg", "dg_skill_putt", "dg_skill_dist"]:
                    if col in sk_df.columns:
                        stats[col] = _n(row.get(col))
        except Exception:
            pass

    # Course history (PGA Championship from DB)
    pga_starts = pga_top10s = pga_wins = 0
    avg_to_par = cut_rate = None
    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                lb = conn.execute(
                    "SELECT player_name, position FROM leaderboards WHERE tournament_id LIKE '%033'"
                ).df()
            def _ln(n):
                s = str(n).strip()
                return s.split(",")[0].strip().lower() if "," in s else s.strip().split()[-1].lower()
            target_ln = _ln(player)
            pga_rows = lb[lb["player_name"].apply(_ln) == target_ln]
            pga_starts = len(pga_rows)
            if pga_starts:
                def _parse_pos_num(p):
                    s = str(p).strip().upper().lstrip("T")
                    if s in {"CUT","MC","WD","DQ","MDF","RTD",""}: return None
                    try: return int(float(s))
                    except: return None
                positions = pga_rows["position"].apply(_parse_pos_num).dropna()
                pga_top10s = int((positions <= 10).sum())
                pga_wins   = int((positions == 1).sum())
        except Exception:
            pass

    # Fantasy uses remaining
    uses_remaining = 3
    try:
        tracker_path = _TRACKER_JSON
        if tracker_path.exists():
            tracker = json.loads(tracker_path.read_text())
            def _lname(n):
                s = str(n).strip()
                return s.split(",")[0].strip().lower() if "," in s else s.strip().split()[-1].lower()
            target_ln = _lname(player)
            for short_name, pdata in tracker.get("picks", {}).items():
                if _lname(short_name) == target_ln:
                    uses_remaining = int(pdata.get("remaining_uses", 0))
                    break
    except Exception:
        pass

    # Tournament & course info
    tournament_name = "this week's tournament"
    course_name = "the course"
    try:
        sched = pd.read_csv(_SCHED_CSV)
        row = sched[sched["tournament_id"].astype(str) == tid]
        if not row.empty:
            tournament_name = str(row["tournament_name"].iloc[0])
            course_name = {
                "R2026033": "Aronimink Golf Club",
                "R2026014": "Augusta National Golf Club",
            }.get(tid, str(row["location"].iloc[0]))
    except Exception:
        pass

    # ── Build prompt ──────────────────────────────────────────────────────────
    def _pct(v) -> str:
        n = _n(v)
        return f"{n*100:.1f}%" if n is not None else "N/A"

    def _sg(v) -> str:
        n = _n(v)
        if n is None: return "N/A"
        return f"{n:+.2f}"

    def _adj(v) -> str:
        n = _n(v)
        if n is None: return "N/A"
        return f"{n:+.3f} SG"

    world_rank = stats.get("world_rank")
    rank_str = f"#{int(world_rank)}" if world_rank else "unranked"

    prompt = f"""You are a sharp PGA Tour analyst. Write a concise player analysis for {player} ahead of the {tournament_name} at {course_name}.

Use ONLY the data below. Do not invent stats or results not provided.

--- PLAYER DATA ---
World Rank: {rank_str}

Model predictions:
  Win%: {_pct(stats.get('win_prob'))} | Top 10%: {_pct(stats.get('top10_prob'))} | Cut%: {_pct(stats.get('cut_prob'))}
  DK Odds: {stats.get('odds_to_win', 'N/A')} | Model edge vs Vegas: {_sg(stats.get('model_vs_vegas_edge'))}pp

DataGolf predictions:
  DG Win%: {_pct(stats.get('dg_win'))} | DG Top10%: {_pct(stats.get('dg_top10'))} | DG Make Cut%: {_pct(stats.get('dg_make_cut'))}

Season SG (vs field avg):
  Total: {_sg(stats.get('season_sg_total'))} | OTT: {_sg(stats.get('season_sg_ott'))} | APP: {_sg(stats.get('season_sg_app'))} | ARG: {_sg(stats.get('season_sg_arg'))} | Putt: {_sg(stats.get('season_sg_putt'))}
  Form trend: {_sg(stats.get('form_trend'))} (recent direction vs season average)

DG Skill Ratings (career/long-term):
  Total: {_sg(stats.get('dg_skill_total'))} | OTT: {_sg(stats.get('dg_skill_ott'))} | APP: {_sg(stats.get('dg_skill_app'))} | ARG: {_sg(stats.get('dg_skill_arg'))} | Putt: {_sg(stats.get('dg_skill_putt'))} | Drive dist: {_sg(stats.get('dg_skill_dist'))} yds vs avg

DG Adjustments for {tournament_name}:
  Timing/Form: {_adj(stats.get('timing_adjustment'))} (positive = currently above expected form)
  Course Fit: {_adj(stats.get('total_fit_adjustment'))} (positive = course suits their game)
  Course History: {_adj(stats.get('total_course_history_adjustment'))} (past results adjustment)
  Driving Distance fit: {_adj(stats.get('driving_distance_adjustment'))}
  Driving Accuracy fit: {_adj(stats.get('driving_accuracy_adjustment'))}
  DG Baseline SG: {_sg(stats.get('baseline_pred'))} | DG Final SG: {_sg(stats.get('final_pred'))}

PGA Championship history:
  Starts: {pga_starts} | Top 10s: {pga_top10s} | Wins: {pga_wins}

Fantasy uses: {uses_remaining}/3 remaining this season

--- OUTPUT FORMAT ---
Respond with JSON only, no markdown. Exactly this structure:
{{
  "form": "2-3 sentences about current form, timing adjustment, and trend direction.",
  "course_fit": "2-3 sentences about how the course suits or doesn't suit their game, citing specific SG categories.",
  "betting_angle": "1-2 sentences on where the value is or isn't. Reference model vs DG gap if significant.",
  "fantasy": "1 sentence on whether to use a pick on them this week given their uses remaining, EV, and form."
}}"""

    # ── Call Claude Haiku ─────────────────────────────────────────────────────
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw).rstrip("`").strip()
        sections = json.loads(raw)
    except json.JSONDecodeError:
        # If LLM didn't return valid JSON, wrap in a single block
        sections = {"form": raw, "course_fit": "", "betting_angle": "", "fantasy": ""}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    result = {
        "player_name":     player,
        "tournament_id":   tid,
        "tournament_name": tournament_name,
        "course_name":     course_name,
        "sections":        sections,
        "generated_ts":    time.time(),
        "cached":          False,
    }

    try:
        cache_file.write_text(json.dumps(result))
    except Exception:
        pass

    # ── Persist to DuckDB ─────────────────────────────────────────────────────
    if _DB_AVAILABLE:
        try:
            with _get_db_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO player_synopses
                        (tournament_id, player_name, generated_at,
                         form_text, course_fit_text, betting_angle, fantasy_text, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    tid, player,
                    datetime.utcnow().isoformat(),
                    sections.get("form", ""),
                    sections.get("course_fit", ""),
                    sections.get("betting_angle", ""),
                    sections.get("fantasy", ""),
                    json.dumps(sections),
                ])
        except Exception:
            pass

    return result


@app.get("/api/players/stats")
def get_field_stats() -> dict:
    """Field-wide stats table for the Stats Deep Dive tab."""
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not pred_path.exists():
        return {"players": []}

    df = pd.read_csv(pred_path)

    WANT = [
        "player_name", "world_rank",
        # SG breakdown
        "season_sg_total", "season_sg_ott", "season_sg_app", "season_sg_arg", "season_sg_putt",
        "season_sg_ott_field_rank", "season_sg_app_field_rank",
        "season_sg_arg_field_rank", "season_sg_putt_field_rank",
        # Course fit (historical)
        "course_sg_total_avg", "course_sg_ott_avg", "course_sg_app_avg",
        "course_sg_putt_avg", "course_sg_starts", "course_made_cut_rate", "course_win_rate",
        # DG course fit
        "dg_course_fit_delta", "dg_course_fit_delta_pct",
        # Form
        "form_trend", "consecutive_cuts", "consecutive_top10s",
        "recent_top10s", "recent_wins", "missed_cut_last_start",
        # DG model
        "dg_win", "dg_top10",
        # Our model (used for DG comparison view)
        "win_prob", "top10_prob",
    ]

    cols = [c for c in WANT if c in df.columns]
    for col in cols:
        if col != "player_name":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["player_name"] = df["player_name"].apply(
        lambda n: _flip_to_first_last(str(n).strip())
    )

    records = [{k: _safe(row[k]) for k in cols} for _, row in df[cols].iterrows()]
    return {"players": records}


@app.get("/api/mypicks")
def get_my_picks() -> dict:
    """Season usage tracker — weekly lineups + player roster."""
    path = _TRACKER_JSON
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"usage_tracker_{SEASON}.json not found")

    with open(path) as f:
        raw = json.load(f)

    # ── Weekly log (most recent first) ───────────────────────────────────────
    weekly_lineups = raw.get("weekly_lineups", {})
    weeks = []
    for key, wl in weekly_lineups.items():
        earnings = wl.get("earnings_earned") or wl.get("points_earned") or 0
        weeks.append({
            "week":          wl.get("week"),
            "tournament":    wl.get("tournament", ""),
            "date":          wl.get("date", ""),
            "lineup":        wl.get("lineup", []),
            "finish":        wl.get("wrp"),
            "earnings":      int(earnings) if earnings else 0,
        })
    weeks.sort(key=lambda w: w["week"] or 0, reverse=True)

    # ── Player roster ─────────────────────────────────────────────────────────
    picks = raw.get("picks", {})
    roster = []
    for name, p in picks.items():
        roster.append({
            "player_name":    name,
            "times_used":     p.get("times_used", 0),
            "remaining_uses": p.get("remaining_uses", 3),
            "total_earnings": int(p.get("total_earnings", 0)),
            "tournaments":    p.get("tournaments_used", []),
        })
    roster.sort(key=lambda r: r["total_earnings"], reverse=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = raw.get("summary", {})
    total_earnings = summary.get("total_earnings", 0) or sum(w["earnings"] for w in weeks)
    best_week = max(weeks, key=lambda w: w["earnings"]) if weeks else None

    return {
        "season":          raw.get("season", 2026),
        "last_updated":    raw.get("last_updated", ""),
        "max_uses":        raw.get("max_uses_per_player", 3),
        "weeks":           weeks,
        "roster":          roster,
        "summary": {
            "total_earnings":  int(total_earnings),
            "total_weeks":     len([w for w in weeks if w["earnings"] > 0]),
            "total_players":   len(roster),
            "best_week":       best_week,
            "avg_earnings":    int(total_earnings / len(weeks)) if weeks else 0,
        },
    }


@app.get("/api/expert-picks")
def get_expert_picks() -> dict:
    """Expert consensus picks from expert_picks_latest.csv (or tournament-specific file)."""
    tid = _get_tournament_id()
    ep_dir = DATA_DIR / "expert_picks"

    # Prefer tournament-specific file, fall back to latest
    candidates = [
        ep_dir / f"expert_picks_{tid}.csv",
        ep_dir / "expert_picks_latest.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise HTTPException(status_code=404, detail="No expert picks file found")

    import csv, ast

    def _parse_names(raw) -> list[str]:
        if not raw or str(raw).strip() in ("", "nan", "None", "[]"):
            return []
        try:
            parsed = ast.literal_eval(str(raw))
            return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            return []

    experts = []
    lineup_counts: dict[str, int] = {}
    winner_counts: dict[str, int] = {}

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lineup  = _parse_names(row.get("lineup_player_names", ""))
            bench   = _parse_names(row.get("bench_player_names", ""))
            winner  = str(row.get("winner_name", "") or "").strip()
            expert  = str(row.get("expert_name",  "") or "").strip()
            if not expert:
                continue
            experts.append({
                "expert_name":  expert,
                "expert_title": str(row.get("expert_title", "") or "").strip(),
                "winner_pick":  winner or None,
                "lineup":       lineup,
                "bench":        bench,
                "comment":      str(row.get("comment", "") or "").strip() or None,
            })
            for name in lineup:
                lineup_counts[name] = lineup_counts.get(name, 0) + 1
            if winner:
                winner_counts[winner] = winner_counts.get(winner, 0) + 1

    # Build consensus list
    all_players = set(lineup_counts) | set(winner_counts)
    n_experts = max(len(experts), 1)
    consensus = sorted(
        [
            {
                "player_name":      p,
                "lineup_mentions":  lineup_counts.get(p, 0),
                "winner_picks":     winner_counts.get(p, 0),
                "total_mentions":   lineup_counts.get(p, 0) + winner_counts.get(p, 0),
                "lineup_pct":       round(lineup_counts.get(p, 0) / n_experts * 100, 1),
                "winner_pct":       round(winner_counts.get(p, 0) / n_experts * 100, 1),
            }
            for p in all_players
        ],
        key=lambda x: (-x["winner_picks"], -x["lineup_mentions"]),
    )

    tournament_name = ""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tournament_name = str(row.get("tournament_name", "") or "").strip()
            break

    return {
        "tournament": tournament_name,
        "expert_count": len(experts),
        "experts": experts,
        "consensus": consensus,
    }


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    query: str
    messages: list[ChatMessage] = []
    last_players: list[str] = []


# Minutes before the local leaderboard CSV is considered stale.
# Above this threshold, Scenario B fires: warn the model + inject web search results.
_STALE_THRESHOLD_MIN = 60

# Queries where the user wants precise numbers cited verbatim.
# Lower temperature (0.3) reduces hallucinated stats; conversational queries stay at 0.6.
_FACTUAL_QUERY_SIGNALS = {
    "who is leading", "who's leading", "who won", "what's the score",
    "current score", "leaderboard", "what are the odds", "what's the line",
    "best bets", "value bets", "top bets", "what edge", "make cut odds",
    "outright odds", "who made the cut", "final score", "round score",
}

# Keywords that signal the user needs deeper analytical reasoning.
# These queries benefit from Sonnet's stronger reasoning vs. Haiku's speed/cost.
# Cost on a ~16K-token context: Haiku ~$0.01/turn, Sonnet ~$0.05/turn.
_COMPLEX_QUERY_SIGNALS = {
    "season strategy", "when to use", "when should i use", "save for",
    "best event for", "best tournament for", "uses left", "usage strategy",
    "model performance", "how has the model", "season performance", "how accurate",
    "calibration", "historical", "compare all", "rank these", "rank all",
    "which of my players", "among all", "start or sit", "full breakdown",
    "walk me through", "explain the model", "how does the model work",
}

def _select_model(query: str) -> str:
    """Route to Sonnet for complex analytical queries, Haiku for everything else."""
    q = query.lower()
    if any(sig in q for sig in _COMPLEX_QUERY_SIGNALS):
        return "claude-sonnet-4-6"
    return "claude-haiku-4-5-20251001"


# ── Response cache ────────────────────────────────────────────────────────────
# Caches full LLM responses in-memory. Keyed by normalized query + tournament +
# data freshness so it auto-invalidates when the pipeline updates predictions.
# Resets on server restart (intentional — stale responses from prior pipeline
# runs should never be served after a restart).

import hashlib as _hashlib

_RESPONSE_CACHE: dict[str, dict] = {}

# Queries about real-time state — never cache these
_LIVE_CACHE_SKIP = {
    "leaderboard", "right now", "currently", "score", "thru", "who's winning",
    "who is winning", "live", "in progress", "hole", "round score",
}

def _response_cache_key(query: str, tid: str | None) -> str:
    """Stable key: normalized query + tournament + predictions file bucket (10-min windows)."""
    q = re.sub(r"[^\w\s]", "", query.lower().strip())
    q = re.sub(r"\s+", " ", q)
    preds = OUTPUTS_DIR / "latest_predictions.csv"
    mtime_bucket = int(preds.stat().st_mtime // 600) if preds.exists() else 0
    raw = f"{tid}:{mtime_bucket}:{q}"
    return _hashlib.md5(raw.encode()).hexdigest()[:20]


def _cache_ttl(intent: dict, query: str) -> int:
    """Return TTL in seconds. 0 = do not cache."""
    q = query.lower()
    if any(s in q for s in _LIVE_CACHE_SKIP):
        return 0
    if intent.get("is_leaderboard") or intent.get("is_live"):
        return 0
    if intent.get("is_bet") or intent.get("is_value") or intent.get("is_daily_bet"):
        return 20 * 60   # 20 min — odds refresh every 30 min
    if intent.get("is_field_overview") or intent.get("is_course"):
        return 45 * 60   # 45 min — stable pre-tournament
    if intent.get("is_player") or intent.get("is_h2h"):
        return 30 * 60   # 30 min — player form is relatively stable
    return 15 * 60       # 15 min default


def _cache_get(key: str) -> str | None:
    entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > entry["ttl"]:
        del _RESPONSE_CACHE[key]
        return None
    return entry["text"]


def _cache_set(key: str, text: str, ttl: int) -> None:
    if ttl > 0 and text:
        _RESPONSE_CACHE[key] = {"text": text, "ts": time.time(), "ttl": ttl}


def _stream_from_cache(text: str):
    """Replay a cached response as a fake SSE stream (chunked so it feels live)."""
    chunk = 30
    for i in range(0, len(text), chunk):
        yield f"data: {json.dumps({'text': text[i:i+chunk], 'cached': True})}\n\n"
    yield "data: [DONE]\n\n"


def _select_temperature(query: str) -> float:
    """Lower temperature for factual queries (precise stat citation); higher for conversation."""
    q = query.lower()
    if any(sig in q for sig in _FACTUAL_QUERY_SIGNALS):
        return 0.3
    return 0.6


@app.post("/api/chat")
def chat_endpoint(body: ChatRequest, request: Request):
    """Stream an assistant response via SSE. Routes to Haiku (simple) or Sonnet (complex)."""
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limit_ok(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit: 20 chat requests per 24 hours")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not set in server environment")

    # Import chatbot (PROJECT_ROOT already on path from other endpoints)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from scripts.chat.golf_chatbot import (  # type: ignore
        build_context, _build_cached_system, _live_leaderboard_block,
        _leaderboard_age_minutes, _web_live_scores_block,
    )

    model = _select_model(body.query)

    context = build_context(
        query=body.query,
        last_players=body.last_players or [],
        lean=True,  # web API: keep context under ~45K chars
    )

    # ── Live data handling ────────────────────────────────────────────────────
    # Three scenarios:
    #   A) Fresh local CSV (≤60 min old)  → prepend authoritatively, model trusts it
    #   B) Stale local CSV (>60 min old)  → warn model, also inject real-time web search
    #   C) No local CSV (pre-tournament)  → skip live block entirely
    # Exception: when the query is about a past/historical tournament, skip the
    # authoritative live override so the model can answer from recap context.
    try:
        from scripts.chat.golf_chatbot import _classify_query as _cq  # type: ignore
        _q_intent = _cq(body.query)
        _query_is_historical = bool(
            _q_intent.get("is_historical") or
            _q_intent.get("is_round_recap") or
            _q_intent.get("is_season_performance")
        )
    except Exception:
        _query_is_historical = False

    tid = _get_tournament_id()
    if tid:
        age = _leaderboard_age_minutes(tid)
        lb  = _live_leaderboard_block(tid)

        if lb and age is not None and age <= _STALE_THRESHOLD_MIN and not _query_is_historical:
            # Scenario A: fresh data — authoritative (skip for historical queries)
            context = (
                "LIVE TOURNAMENT IN PROGRESS — the standings below are the ONLY authoritative "
                "source for current scores and positions. Do NOT use pre-tournament model "
                "rankings to describe who is leading or what position any player is in.\n\n"
                + lb
                + "\n\n<!-- SPLIT -->\n\n"
                + context
            )

        elif lb and age is not None and age > _STALE_THRESHOLD_MIN and not _query_is_historical:
            # Scenario B: stale data — warn the model, supplement with web search
            _t_name = _get_tournament_name(tid)
            web_scores = _web_live_scores_block(_t_name) if _t_name else ""
            context = (
                f"⚠️ LOCAL LEADERBOARD DATA IS {age} MINUTES OLD — it may not reflect "
                "current standings. Do NOT state specific positions or scores from it as facts. "
                "Instead, cite the web search results below for current standings, or tell the "
                "user you don't have real-time data and they should check the live leaderboard.\n\n"
                + (web_scores + "\n\n" if web_scores else "")
                + lb
                + "\n\n<!-- SPLIT -->\n\n"
                + context
            )

    # Conversation history for the API (last 20 turns, excluding current user msg)
    conv = [{"role": m.role, "content": m.content} for m in body.messages[-20:]]

    # Sonnet handles complex multi-part responses; give it more room than Haiku.
    max_tokens = 3000 if model == "claude-sonnet-4-6" else 1500
    temperature = _select_temperature(body.query)

    # ── Response cache check ──────────────────────────────────────────────────
    # Only cache single-turn questions (no conversation history) — follow-ups
    # are contextual and can't be replayed safely.
    _can_cache  = len(body.messages) == 0
    _cache_key  = _response_cache_key(body.query, tid) if _can_cache else ""
    _ttl        = _cache_ttl(_q_intent, body.query)    if _can_cache else 0

    if _can_cache and _ttl > 0:
        cached_text = _cache_get(_cache_key)
        if cached_text:
            return StreamingResponse(
                _stream_from_cache(cached_text),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    groq_key = os.environ.get("GROQ_API_KEY", "")

    def _stream_groq_fallback(buf: list[str]):
        """Groq/Llama fallback — used when Anthropic credits are exhausted."""
        from groq import Groq, RateLimitError  # type: ignore
        _GROQ_PRIMARY  = "llama-3.3-70b-versatile"
        _GROQ_FALLBACK = "llama-3.1-8b-instant"
        # Flatten system blocks back to a single string for Groq
        system_text = context if isinstance(context, str) else "\n\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in context
        )
        groq_messages = [{"role": "system", "content": system_text}, *conv]
        client = Groq(api_key=groq_key)

        def _call(model_name: str):
            return client.chat.completions.create(
                model=model_name, messages=groq_messages,
                stream=True, temperature=0.6, max_tokens=max_tokens,
            )

        try:
            for chunk in _call(_GROQ_PRIMARY):
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    buf.append(delta)
                    yield f"data: {json.dumps({'text': delta})}\n\n"
        except RateLimitError:
            notice = "\n\n*(Switching to backup model)*\n\n"
            buf.append(notice)
            yield f"data: {json.dumps({'text': notice})}\n\n"
            for chunk in _call(_GROQ_FALLBACK):
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    buf.append(delta)
                    yield f"data: {json.dumps({'text': delta})}\n\n"

    def _stream():
        buf: list[str] = []
        try:
            import httpx as _httpx
            from anthropic import Anthropic  # type: ignore
            client = Anthropic(
                api_key=api_key,
                timeout=_httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
            )
            system_blocks = _build_cached_system(context)
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_blocks,
                messages=conv,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            ) as stream:
                for text in stream.text_stream:
                    buf.append(text)
                    yield f"data: {json.dumps({'text': text})}\n\n"
        except Exception as e:
            err_str = str(e).lower()
            # Fall back to Groq on: credit exhaustion, overload, or stream timeout
            if groq_key and any(x in err_str for x in [
                "credit", "billing", "quota", "balance", "429", "overloaded",
                "timeout", "idle", "stream",
            ]):
                yield from _stream_groq_fallback(buf)
            else:
                yield f"data: {json.dumps({'text': f'\\n\\n*(Error: {e})*'})}\n\n"

        # Store full response after stream completes
        if _can_cache and _ttl > 0 and buf:
            _cache_set(_cache_key, "".join(buf), _ttl)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RateRequest(BaseModel):
    query: str
    response: str
    rating: str   # "up" or "down"
    tid: str = ""


@app.post("/api/chat/rate")
def rate_chat(body: RateRequest):
    """Log a thumbs-up or thumbs-down rating for a chat response."""
    import json as _json
    from datetime import datetime, timezone
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    feedback_dir = DATA_DIR / "feedback"
    feedback_dir.mkdir(exist_ok=True)
    entry = {
        "ts":       datetime.now(timezone.utc).isoformat(),
        "tid":      body.tid,
        "rating":   body.rating,
        "query":    body.query,
        "response": body.response,
    }
    with open(feedback_dir / "chat_ratings.jsonl", "a") as fh:
        fh.write(_json.dumps(entry) + "\n")
    return {"ok": True}


@app.get("/api/model-comparison")
def get_model_comparison() -> dict:
    """
    Compare our model's pre-tournament probabilities vs DataGolf's published predictions.

    Returns:
      - rank_correlation: Spearman ρ between our win_prob ranks and DG's win ranks
      - disagreements: players where our prob differs from DG by >5pp (potential edges)
      - our_top10 / dg_top10: each model's top-10 predicted finishers
      - markets: per-market correlation (win, top5, top10, top20, make_cut)
    """
    from scipy.stats import spearmanr  # type: ignore

    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    dg_path    = DG_DIR / "dg_pre_tournament_latest.csv"

    if not preds_path.exists():
        raise HTTPException(status_code=404, detail="No predictions found")
    if not dg_path.exists():
        raise HTTPException(status_code=404, detail="No DataGolf pre-tournament data found")

    our  = pd.read_csv(preds_path, low_memory=False)
    dg   = pd.read_csv(dg_path,    low_memory=False)

    # ── Name normalization ────────────────────────────────────────────────────
    def _sort_key(name: str) -> str:
        return " ".join(sorted(str(name).replace(",", "").lower().split()))

    our["_key"] = our["player_name"].fillna("").apply(_sort_key)
    # DG has two model variants — use baseline only
    if "model" in dg.columns:
        dg = dg[dg["model"] == "baseline"]
    dg["_key"] = dg["player_name"].fillna("").apply(_sort_key)

    # Use calibrated probabilities if available, fall back to raw
    our_win   = "win_prob_calibrated"   if "win_prob_calibrated"   in our.columns else "win_prob"
    our_top5  = "top5_prob_calibrated"  if "top5_prob_calibrated"  in our.columns else "top5_prob"
    our_top10 = "top10_prob_calibrated" if "top10_prob_calibrated" in our.columns else "top10_prob"
    our_top20 = "top20_prob_calibrated" if "top20_prob_calibrated" in our.columns else "top20_prob"

    # ── Merge on sort key ─────────────────────────────────────────────────────
    merged = our.merge(
        dg[["_key", "win", "top_5", "top_10", "top_20", "make_cut"]],
        on="_key", how="inner"
    )
    if merged.empty:
        raise HTTPException(status_code=404, detail="No player overlap between our predictions and DataGolf")

    # ── Per-market Spearman rank correlations ─────────────────────────────────
    markets: list[dict] = []
    market_map = [
        ("win",      our_win,   "win"),
        ("top5",     our_top5,  "top_5"),
        ("top10",    our_top10, "top_10"),
        ("top20",    our_top20, "top_20"),
        ("make_cut", "make_cut_prob" if "make_cut_prob" in our.columns else our_win, "make_cut"),
    ]
    for label, our_col, dg_col in market_map:
        if our_col not in merged.columns or dg_col not in merged.columns:
            continue
        rho, _ = spearmanr(merged[our_col].fillna(0), merged[dg_col].fillna(0))
        markets.append({"market": label, "spearman_rho": round(float(rho), 3)})

    # Overall win-prob correlation
    overall_rho = next((m["spearman_rho"] for m in markets if m["market"] == "win"), None)

    # ── Disagreements: players where win prob differs by >4pp ─────────────────
    merged["diff_pp"] = (merged[our_win].fillna(0) - merged["win"].fillna(0)) * 100
    disagreements: list[dict] = []
    for _, row in merged[merged["diff_pp"].abs() > 4].sort_values("diff_pp", key=abs, ascending=False).head(15).iterrows():
        disagreements.append({
            "player_name":  row["player_name"],
            "our_win_pct":  round(float(row[our_win]) * 100, 1),
            "dg_win_pct":   round(float(row["win"]) * 100, 1),
            "diff_pp":      round(float(row["diff_pp"]), 1),
            "our_top10":    round(float(row[our_top10]) * 100, 1) if our_top10 in row else None,
            "dg_top10":     round(float(row["top_10"]) * 100, 1),
            "direction":    "higher" if row["diff_pp"] > 0 else "lower",
        })

    # ── Top-10 predicted finishers for each model ─────────────────────────────
    def _top10_list(df: pd.DataFrame, prob_col: str, name_col: str) -> list[dict]:
        return [
            {"player": r[name_col], "prob": round(float(r[prob_col]) * 100, 1)}
            for _, r in df.nlargest(10, prob_col).iterrows()
            if pd.notna(r.get(prob_col))
        ]

    our_top10_list = _top10_list(merged, our_win, "player_name")
    dg_top10_list  = _top10_list(merged, "win",   "player_name")

    # Tournament context
    tid  = _get_tournament_id() or ""
    name = _get_tournament_name(tid) or "Current Tournament"

    return {
        "tournament_id":   tid,
        "tournament_name": name,
        "players_compared": len(merged),
        "overall_spearman_rho": overall_rho,
        "markets":         markets,
        "our_top10":       our_top10_list,
        "dg_top10":        dg_top10_list,
        "disagreements":   disagreements,
    }


@app.get("/api/weather")
def get_weather() -> dict:
    """Thu–Sun forecast from data/weather/{tid}.json (written by scheduler)."""
    tid = _get_tournament_id()
    path = DATA_DIR / "weather" / f"{tid}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No weather data for this tournament")

    with open(path) as f:
        raw = json.load(f)

    ROUND_DAYS = {"Thu", "Fri", "Sat", "Sun"}

    def _parse_day(d: dict) -> dict:
        temp = d.get("temperature", {})
        return {
            "day":         d.get("title", ""),
            "condition":   d.get("condition", ""),
            "wind_mph":    d.get("windSpeedMPH", ""),
            "wind_dir":    d.get("windDirection", "").replace("_", " ").title(),
            "precip_pct":  d.get("precipitation", ""),
            "humidity":    d.get("humidity", ""),
            "high_f":      temp.get("maxTempF", ""),
            "low_f":       temp.get("minTempF", ""),
        }

    days = [_parse_day(d) for d in raw.get("daily", []) if d.get("title") in ROUND_DAYS]
    return {
        "tournament_id": tid,
        "saved_at":      raw.get("saved_at", ""),
        "days":          days,
    }


@app.get("/api/withdrawals")
def get_withdrawals() -> dict:
    """Confirmed withdrawals from data/news/withdrawals_{tid}.json."""
    tid = _get_tournament_id()
    wd_dir = DATA_DIR / "news"
    path = wd_dir / f"withdrawals_{tid}.json"

    if not path.exists():
        files = sorted(wd_dir.glob("withdrawals_R*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return {"tournament_id": tid, "withdrawals": [], "count": 0, "confirmed_count": 0}
        path = files[0]

    with open(path) as f:
        raw = json.load(f)

    def _fmt_name(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    entries = [
        {
            "player_name": _fmt_name(w.get("player_name", "")),
            "status":      w.get("status", ""),
            "source":      w.get("source", ""),
            "detected_at": w.get("detected_at", ""),
        }
        for w in raw
        if w.get("status") == "WITHDRAWN"
    ]

    return {
        "tournament_id":   tid,
        "withdrawals":     entries,
        "count":           len(entries),
        "confirmed_count": len(entries),
    }


@app.post("/api/generate-analysis")
def generate_analysis() -> dict:
    """Trigger generate_strategy_reasoning.py in the background. Returns immediately."""
    import threading
    def _run():
        subprocess.run(
            ["python3", "scripts/predictions/generate_strategy_reasoning.py"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=300,
        )
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Analysis generation started — refresh in ~60 seconds."}


@app.get("/api/history/tournaments")
def history_tournaments() -> dict:
    """Past tournament results — winners, top 10, field size, earnings, recap."""
    hist_path = _LB_CSV
    if not hist_path.exists():
        return {"tournaments": []}

    df = pd.read_csv(hist_path)
    df["position_num"] = pd.to_numeric(df["position"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")

    schedule = pd.read_csv(_SCHED_CSV)
    sched_map = dict(zip(schedule["tournament_id"].astype(str), schedule["start_date"]))
    purse_map  = dict(zip(schedule["tournament_id"].astype(str), schedule["purse"]))
    name_map   = dict(zip(schedule["tournament_id"].astype(str), schedule["tournament_name"]))

    # Load recaps — Supabase first, JSON files fallback
    recap_map: dict[str, str] = {}
    sb = _get_sb()
    if sb:
        try:
            rows = sb.table("recaps").select("tournament_id,narrative").execute().data
            for r in rows:
                recap_map[str(r["tournament_id"]).upper()] = r.get("narrative", "")
        except Exception:
            pass
    if not recap_map:
        for recap_file in (PROJECT_ROOT / "outputs").glob("tournament_recap_*.json"):
            try:
                with open(recap_file) as f:
                    r = json.load(f)
                recap_map[r["tournament_id"].upper()] = r.get("narrative", "")
            except Exception:
                pass

    tournaments = []
    for tid, grp in df.groupby("tournament_id"):
        grp = grp.sort_values("position_num", na_position="last")
        winner_row = grp[grp["position_num"] == 1]
        top10 = grp[grp["position_num"] <= 10][["player_name", "position", "to_par"]].head(10)

        # Prefer schedule name; fall back to leaderboard column; last resort = ID
        raw_name = grp["tournament_name"].iloc[0] if "tournament_name" in grp.columns else None
        display_name = name_map.get(str(tid)) or (raw_name if pd.notna(raw_name) else str(tid))

        tournaments.append({
            "tournament_id":   str(tid),
            "name":            display_name,
            "start_date":      sched_map.get(str(tid), ""),
            "purse":           purse_map.get(str(tid), ""),
            "winner":          winner_row["player_name"].iloc[0] if not winner_row.empty else "",
            "winner_score":    winner_row["to_par"].iloc[0] if not winner_row.empty else "",
            "winner_earnings": winner_row["earnings"].iloc[0] if not winner_row.empty else "",
            "field_size":      len(grp),
            "recap":           recap_map.get(str(tid).upper(), None),
            "top10": [
                {"player": r["player_name"], "position": r["position"], "to_par": r["to_par"]}
                for _, r in top10.iterrows()
            ],
        })

    tournaments.sort(key=lambda t: t["start_date"], reverse=True)
    return {"tournaments": tournaments}


@app.get("/api/history/model")
def history_model() -> dict:
    """Model prediction accuracy by tournament — reads from DuckDB."""
    import math
    from scipy.stats import spearmanr

    if not _DB_AVAILABLE:
        return {"tournaments": []}

    try:
        with _get_db_conn() as conn:
            df = conn.execute("""
                SELECT tournament_id, tournament_name, tournament_date,
                       predicted_win_prob, predicted_top5_prob, predicted_top10_prob,
                       actual_position, actual_won, actual_top5, actual_top10, actual_top20
                FROM prediction_history
                WHERE result_recorded = TRUE
            """).df()
    except Exception:
        return {"tournaments": []}

    df["actual_position"] = pd.to_numeric(df["actual_position"], errors="coerce")
    for _col in ["actual_won", "actual_top5", "actual_top10", "actual_top20"]:
        df[_col] = df[_col].fillna(False).astype(bool).astype(int)

    rows = []
    for tid, grp in df.groupby("tournament_id"):
        n = len(grp)
        if n == 0:
            continue

        win_pred     = grp["predicted_win_prob"].mean()
        win_actual   = grp["actual_won"].sum() / n
        top5_pred    = grp["predicted_top5_prob"].mean()
        top5_actual  = grp["actual_top5"].sum() / n
        top10_pred   = grp["predicted_top10_prob"].mean()
        top10_actual = grp["actual_top10"].sum() / n

        grp2 = grp.dropna(subset=["actual_position", "predicted_win_prob"])
        grp2 = grp2[grp2["actual_position"] < 900]
        corr = None
        if len(grp2) >= 10:
            r_val, _ = spearmanr(-grp2["predicted_win_prob"], grp2["actual_position"])
            if not math.isnan(float(r_val)):
                corr = round(float(r_val), 3)

        rows.append({
            "tournament_id":   str(tid),
            "name":            grp["tournament_name"].iloc[0] or str(tid),
            "date":            grp["tournament_date"].iloc[0] or "",
            "field_size":      n,
            "win_pred_avg":    round(float(win_pred) * 100, 2),
            "win_actual_pct":  round(float(win_actual) * 100, 2),
            "top5_pred_avg":   round(float(top5_pred) * 100, 2),
            "top5_actual_pct": round(float(top5_actual) * 100, 2),
            "top10_pred_avg":  round(float(top10_pred) * 100, 2),
            "top10_actual_pct":round(float(top10_actual) * 100, 2),
            "rank_corr":       corr,
        })

    rows.sort(key=lambda r: r["date"], reverse=True)
    return {"tournaments": rows}


@app.get("/api/history/bets")
def history_bets() -> dict:
    """Bet P&L summary by tournament — reads from DuckDB."""
    if not _DB_AVAILABLE:
        return {"tournaments": [], "overall": {}}

    try:
        with _get_db_conn() as conn:
            df = conn.execute("""
                SELECT tournament_id, market, outcome_status, outcome_win, pnl_per_1
                FROM recommended_bets_log
                WHERE outcome_status IS NOT NULL AND outcome_status != 'pending'
            """).df()
    except Exception:
        return {"tournaments": [], "overall": {}}

    if df.empty:
        return {"tournaments": [], "overall": {"bets": 0, "wins": 0, "pnl": 0.0, "roi": 0.0}}

    df["outcome_win"] = df["outcome_win"].fillna(False).astype(bool).astype(int)
    df["pnl_per_1"]   = pd.to_numeric(df["pnl_per_1"], errors="coerce").fillna(0.0)

    overall_bets = len(df)
    overall_wins = int(df["outcome_win"].sum())
    overall_pnl  = round(float(df["pnl_per_1"].sum()), 3)
    overall_roi  = round(overall_pnl / overall_bets * 100, 1) if overall_bets else 0

    # Schedule name map
    name_map: dict = {}
    try:
        sched = pd.read_csv(_SCHED_CSV)
        name_map = dict(zip(sched["tournament_id"].astype(str), sched["tournament_name"]))
    except Exception:
        pass

    rows = []
    for tid, grp in df.groupby("tournament_id"):
        n    = len(grp)
        wins = int(grp["outcome_win"].sum())
        pnl  = round(float(grp["pnl_per_1"].sum()), 3)
        roi  = round(pnl / n * 100, 1) if n else 0

        market_breakdown = []
        for mkt, mg in grp.groupby("market"):
            market_breakdown.append({
                "market": mkt,
                "bets":   len(mg),
                "wins":   int(mg["outcome_win"].sum()),
                "pnl":    round(float(mg["pnl_per_1"].sum()), 3),
            })

        rows.append({
            "tournament_id": str(tid),
            "name":          name_map.get(str(tid), str(tid)),
            "bets":          n,
            "wins":          wins,
            "pnl":           pnl,
            "roi":           roi,
            "markets":       sorted(market_breakdown, key=lambda x: x["pnl"], reverse=True),
        })

    rows.sort(key=lambda r: r["tournament_id"], reverse=True)
    return {
        "tournaments": rows,
        "overall": {"bets": overall_bets, "wins": overall_wins, "pnl": overall_pnl, "roi": overall_roi},
    }


@app.get("/api/course-fit")
def course_fit() -> dict:
    """
    Course fit data for the current tournament.

    Returns:
    - course_profile: relative importance of each SG category at this course
        (computed from the spread of dg_fit_* adjustments across the field —
        higher spread = that skill is more differentiating here vs. an average course)
    - players: full field sorted by win probability, enriched with course history,
        SG-at-course vs average, and how much the course adjustment moved each player
    """
    
    pred_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not pred_path.exists():
        return {"course_profile": {}, "players": []}
    
    df = pd.read_csv(pred_path)
    
    # --- Course profile ---------------------------------- 
    # std dev of dg_fit_* across the field = how much each component 
    # varies in its course-fit contribution = how "important" that skills is here. 
    # Normalize so they sum to 1 for easier comparison.
    
    fit_stds = { 
        
        "ott": float(df['dg_fit_ott'].std()), 
        "app": float(df['dg_fit_app'].std()), 
        "arg": float(df['dg_fit_arg'].std()), 
        "putt": float(df['dg_fit_putt'].std()),                
                }
    
    total = sum(fit_stds.values()) or 1 
    course_profile = {k: round(v / total, 3) for k, v in fit_stds.items()}
    
    # -- Tournament metadata -------------------------------------------
    tid = str(df['tournament_id'].iloc[0]) if "tournament_id" in df.columns else "" 
    try:
        sched = pd.read_csv(_SCHED_CSV)
        sched_row = sched[sched["tournament_id"].astype(str) == tid]
        _VENUE_MAP = {
            "R2026033": "Aronimink Golf Club",
            "R2026014": "Augusta National Golf Club",
            "R2026026": "Oakmont Country Club",
            "R2026100": "Shinnecock Hills Golf Club",
        }
        if not sched_row.empty:
            course_name = _VENUE_MAP.get(tid) or str(sched_row["location"].iloc[0])
        else:
            course_name = ""

    except Exception:
        course_name = ""
    
    # -- Rank Each Player by overall win prob, then by course-adjusted win-prob - 
    
    df = df.sort_values("win_prob", ascending=False).reset_index(drop=True)
    df['overall_rank'] = df.index + 1 
    
    # Rank by course_fit_delta to show who the course moves most 
    df['win_prob_shift'] = df['win_prob'] - df['win_prob_pre_course_adj']
    
    def _safe(val, decimals=3):
        try:
            f = float(val)
            return None if pd.isna(f) else round(f, decimals)
        except Exception:
            return None

    def _last_name(name: str) -> str:
        """Normalize to lowercase last name for cross-format matching."""
        n = str(name).strip()
        if "," in n:
            return n.split(",")[0].strip().lower()
        return n.strip().split()[-1].lower()

    def _parse_pos(pos) -> int | None:
        s = str(pos).strip().upper().lstrip("T")
        if s in {"CUT", "MC", "WD", "DQ", "MDF", "RTD", ""}:
            return None
        try:
            return int(float(s))
        except ValueError:
            return None

    # ── DG Decompositions — timing, course fit, history adjustments ──────────
    dec_map: dict[str, dict] = {}
    try:
        dec_path = DATA_DIR / "datagolf" / f"dg_decompositions_{tid}.csv"
        if dec_path.exists():
            dec_df = pd.read_csv(dec_path)
            for _, r in dec_df.iterrows():
                key = _last_name(r["player_name"])
                dec_map[key] = {
                    "dg_timing_adj":    float(r["timing_adjustment"])              if pd.notna(r.get("timing_adjustment"))                     else None,
                    "dg_fit_adj":       float(r["total_fit_adjustment"])            if pd.notna(r.get("total_fit_adjustment"))                   else None,
                    "dg_hist_adj":      float(r["total_course_history_adjustment"]) if pd.notna(r.get("total_course_history_adjustment"))        else None,
                    "dg_final_pred":    float(r["final_pred"])                      if pd.notna(r.get("final_pred"))                            else None,
                    "dg_baseline_pred": float(r["baseline_pred"])                   if pd.notna(r.get("baseline_pred"))                         else None,
                }
    except Exception:
        pass

    # ── Venue history from leaderboards DB — dynamic per current tournament ──────
    event_code = tid[-3:] if len(tid) >= 3 else ""  # e.g. "R2026032" → "032"
    venue_label = ""
    try:
        sched = pd.read_csv(_SCHED_CSV)
        sched_row = sched[sched["tournament_id"].astype(str) == tid]
        if not sched_row.empty:
            venue_label = str(sched_row.iloc[0].get("tournament_name", "")).strip()
    except Exception:
        pass

    venue_history: dict[str, dict] = {}
    if _DB_AVAILABLE and event_code:
        try:
            with _get_db_conn() as conn:
                lb = conn.execute(
                    "SELECT player_name, position FROM leaderboards WHERE tournament_id LIKE ?",
                    [f"%{event_code}"],
                ).df()
            for _, r in lb.iterrows():
                key = _last_name(r["player_name"])
                pos = _parse_pos(r["position"])
                entry = venue_history.setdefault(key, {"starts": 0, "top10s": 0, "top5s": 0, "wins": 0, "cuts": 0})
                entry["starts"] += 1
                if pos is not None:
                    entry["top10s"] += 1 if pos <= 10 else 0
                    entry["top5s"]  += 1 if pos <= 5  else 0
                    entry["wins"]   += 1 if pos == 1  else 0
                else:
                    entry["cuts"] += 1
        except Exception:
            pass

    # ── Usage tracker — remaining uses per player ─────────────────────────────
    usage_map: dict[str, int] = {}
    try:
        tracker_path = _TRACKER_JSON
        if tracker_path.exists():
            import json as _json
            tracker = _json.loads(tracker_path.read_text())
            for short_name, pdata in tracker.get("picks", {}).items():
                key = _last_name(short_name)
                usage_map[key] = int(pdata.get("remaining_uses", 0))
    except Exception:
        pass

    # ── Build player rows ─────────────────────────────────────────────────────
    players = []
    for _, row in df.iterrows():
        lname = _last_name(row["player_name"])
        venue = venue_history.get(lname, {})
        dec   = dec_map.get(lname, {})
        players.append({
            "player_name":          row["player_name"],
            "overall_rank":         int(row["overall_rank"]),
            "win_prob":             _safe(row["win_prob"], 4),
            "top10_prob":           _safe(row["top10_prob"], 4),
            "win_prob_pre_adj":     _safe(row["win_prob_pre_course_adj"], 4),
            "win_prob_shift":       _safe(row["win_prob_shift"], 4),
            "course_fit_delta":     _safe(row.get("course_fit_delta"), 3),
            "dg_course_fit_delta":  _safe(row.get("dg_course_fit_delta"), 4),
            # Course / tournament history
            "has_history":          bool(row.get("has_course_history", 0)),
            "course_starts":        _safe(row.get("course_starts"), 0),
            "cut_rate":             _safe(row.get("course_made_cut_rate"), 2),
            "top10_rate":           _safe(row.get("course_top_10_rate"), 2),
            "avg_to_par":           _safe(row.get("course_avg_to_par"), 1),
            "experience_tier":      str(row.get("course_experience_tier", "")),
            # SG at this course vs player's season average
            "sg_ott_vs_avg":        _safe(row.get("course_sg_ott_vs_avg"), 2),
            "sg_app_vs_avg":        _safe(row.get("course_sg_app_vs_avg"), 2),
            "sg_putt_vs_avg":       _safe(row.get("course_sg_putt_vs_avg"), 2),
            "sg_t2g_vs_avg":        _safe(row.get("course_sg_t2g_vs_avg"), 2),
            # DG model numbers
            "dg_win":               _safe(row.get("dg_win"), 4),
            "dg_top10":             _safe(row.get("dg_top10"), 4),
            "world_rank":           _safe(row.get("world_rank"), 0),
            # Venue history — dynamically queried for current tournament event code
            "venue_starts":         venue.get("starts", 0),
            "venue_top10s":         venue.get("top10s", 0),
            "venue_wins":           venue.get("wins", 0),
            # Fantasy uses remaining (None = not in your tracker)
            "uses_remaining":       usage_map.get(lname, None),
            # DG decomposition adjustments
            "dg_timing_adj":        dec.get("dg_timing_adj"),
            "dg_fit_adj":           dec.get("dg_fit_adj"),
            "dg_hist_adj":          dec.get("dg_hist_adj"),
            "dg_final_pred":        dec.get("dg_final_pred"),
            "dg_baseline_pred":     dec.get("dg_baseline_pred"),
        })
    # Detect if history is venue-specific or just tournament-recurring.
    # If the course has no entries in the leaderboards DB, the history 
    # comes from the same named tournament at different venues
    
    # If the course has no entries in the leaderboards DB, the "history"
    # is actually recurring tournament data at different venues — flag it.
    course_history_type = "venue"
    try:
        if _DB_AVAILABLE:
            with _get_db_conn() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM leaderboards WHERE LOWER(tournament_name) LIKE ?",
                    [f"%{course_name.split(',')[0].lower().strip()}%"]
                ).fetchone()[0]
            if n == 0:
                course_history_type = "tournament"
    except Exception:
        pass

    return {
        "tournament_id":       tid,
        "course_name":         course_name,
        "venue_label":         venue_label,
        "course_history_type": course_history_type,
        "course_profile":      course_profile,
        "players":             players,
    }



@app.get("/api/intel")
def get_intel() -> dict:
    """Pre-tournament player intel + course conditions from fetch_tournament_intel.py."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")
    path = DATA_DIR / "intel" / f"tournament_intel_{tid}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No intel for {tid}. Run fetch_tournament_intel.py.")
    data = json.loads(path.read_text())

    # Normalize player names to "First Last" to match predictions endpoint
    def _flip(n: str) -> str:
        s = str(n).strip()
        return f"{s.split(',')[1].strip()} {s.split(',')[0].strip()}" if "," in s else s

    for p in data.get("players", []):
        p["player_name"] = _flip(p.get("player_name", ""))

    # Attach staleness
    try:
        gen = datetime.fromisoformat(data.get("generated_at", "").replace("Z", ""))
        data["age_hours"] = round((datetime.utcnow() - gen).total_seconds() / 3600, 1)
    except Exception:
        data["age_hours"] = None

    return data


@app.post("/api/refresh-intel")
def refresh_intel(top_n: int = 20) -> dict:
    """Trigger fetch_tournament_intel.py for the current tournament."""
    tid = _get_tournament_id()
    if not tid:
        raise HTTPException(status_code=404, detail="No active tournament")

    # Resolve tournament name + course name from schedule + characteristics
    tournament_name = tid
    course_name = ""
    try:
        sched = pd.read_csv(_SCHED_CSV)
        row = sched[sched["tournament_id"].astype(str) == str(tid)]
        if not row.empty:
            tournament_name = str(row.iloc[0].get("tournament_name", tid))
    except Exception:
        pass
    try:
        chars = pd.read_csv(DATA_DIR / "course_characteristics" / "all_courses_2026.csv",
                            usecols=["tournament_id", "course_name", "is_host_course"])
        host = chars[(chars["tournament_id"].astype(str) == str(tid)) &
                     (chars["is_host_course"] == True)]
        if host.empty:
            host = chars[chars["tournament_id"].astype(str) == str(tid)]
        if not host.empty:
            course_name = str(host.iloc[0]["course_name"])
    except Exception:
        pass

    cmd = [
        "python3", str(PROJECT_ROOT / "scripts" / "intel" / "fetch_tournament_intel.py"),
        "--tid", tid,
        "--tournament", tournament_name,
        "--top-n", str(top_n),
    ]
    if course_name:
        cmd += ["--course", course_name]

    subprocess.Popen(cmd, cwd=PROJECT_ROOT,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "message": f"Intel fetch started for {tournament_name} ({top_n} players)"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


 # ── Bet Slip ──────────────────────────────────────────────────────────────────

SLIP_PATH = DATA_DIR / "bets" / "slip.json"


class BetSlipEntry(BaseModel):
    recommendation_id: str | None = None
    tournament_id: str
    player_name: str
    market: str
    selection_label: str
    odds_american: float
    stake_units: float = 1.0


def _load_slip() -> list[dict]:
    if not SLIP_PATH.exists():
        return []
    try:
        return json.loads(SLIP_PATH.read_text()).get("bets", [])
    except Exception:
        return []


def _name_sort_key(name: str) -> str:
    """Normalize 'First Last' or 'Last, First' to a sorted-token key for matching."""
    return " ".join(sorted(name.replace(",", "").lower().split()))


_ON_TRACK_THRESHOLDS: dict[str, tuple[int, int]] = {
    "outright": (5, 12),
    "top5":     (5, 8),
    "top10":    (10, 14),
    "top20":    (20, 25),
    "top30":    (30, 37),
}


def _attach_live_context(bets: list[dict]) -> list[dict]:
    """For each pending bet, attach live leaderboard position/score data."""
    pending_tids = {b["tournament_id"] for b in bets
                    if b.get("outcome_status") == "pending" and b.get("tournament_id")}
    if not pending_tids:
        return bets

    lb_cache: dict[str, pd.DataFrame] = {}
    cut_cache: dict[str, float | None] = {}

    for tid in pending_tids:
        lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
        if not lb_path.exists():
            continue
        try:
            df = pd.read_csv(lb_path, low_memory=False)
            df["_name_key"] = df["player_name"].fillna("").apply(_name_sort_key)
            lb_cache[tid] = df
        except Exception:
            pass

        meta_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}_meta.json"
        projected_cut = None
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                projected_cut = meta.get("cut_projection", {}).get("projected_cut_score")
            except Exception:
                pass
        cut_cache[tid] = projected_cut

    enriched = []
    for bet in bets:
        b = dict(bet)
        tid = b.get("tournament_id", "")

        if b.get("outcome_status") != "pending" or tid not in lb_cache:
            enriched.append(b)
            continue

        df = lb_cache[tid]
        player_key = _name_sort_key(b.get("player_name", ""))
        rows = df[df["_name_key"] == player_key]

        if rows.empty:
            enriched.append(b)
            continue

        row = rows.iloc[0]

        def _str(col: str) -> str | None:
            v = row.get(col)
            s = str(v).strip() if pd.notna(v) else None
            return None if not s or s in ("nan", "") else s

        b["live_position"] = _str("position")
        b["live_total"]    = _str("total")
        b["live_thru"]     = _str("thru")
        b["live_r1"]       = _str("R1")
        b["live_r2"]       = _str("R2")
        b["live_r3"]       = _str("R3")
        b["live_r4"]       = _str("R4")

        pos_str = b["live_position"] or ""
        thru    = b["live_thru"] or ""
        market  = b.get("market", "")

        pos_num: int | None = None
        try:
            pos_num = int(pos_str.lstrip("Tt"))
        except (ValueError, AttributeError):
            pass

        live_status: str | None = None

        if thru == "F" and str(row.get("status", "")).lower() in ("complete", "wd", "cut"):
            live_status = "finished"
        elif market in _ON_TRACK_THRESHOLDS and pos_num is not None:
            on_t, margin_t = _ON_TRACK_THRESHOLDS[market]
            live_status = "on_track" if pos_num <= on_t else "marginal" if pos_num <= margin_t else "off_track"
        elif market == "make_cut":
            total_numeric = row.get("total_numeric")
            projected_cut = cut_cache.get(tid)
            if pd.notna(total_numeric) and projected_cut is not None:
                diff = float(total_numeric) - float(projected_cut)
                live_status = "on_track" if diff <= 0 else "marginal" if diff <= 2 else "off_track"
        elif market.startswith("h2h") or market in ("matchup", "group_winner"):
            live_status = "tracking"

        b["live_status"] = live_status
        enriched.append(b)

    return enriched


def _save_slip(bets: list[dict]) -> None:
    SLIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SLIP_PATH.write_text(json.dumps({"bets": bets}, indent=2))


def _merge_outcomes(bets: list[dict]) -> list[dict]:
    """Cross-reference slip entries against graded results to fill outcomes."""
    results_path = DATA_DIR / "odds" / "recommended_bets_results.csv"
    if not results_path.exists():
        return bets
    try:
        results = pd.read_csv(results_path, low_memory=False)
        by_rec_id: dict[str, Any] = {}
        if "recommendation_id" in results.columns:
            for _, r in results.iterrows():
                by_rec_id[str(r["recommendation_id"])] = r
        by_key: dict[tuple, Any] = {}
        for _, r in results.iterrows():
            if str(r.get("outcome_status", "")) in ("won", "lost"):
                key = (str(r.get("tournament_id", "")),
                        str(r.get("player_name", "")).lower().strip(),
                        str(r.get("market", "")))
                by_key[key] = r
    except Exception:
        return bets

    merged = []
    for bet in bets:
        b = dict(bet)
        result = None
        if b.get("recommendation_id") and b["recommendation_id"] in by_rec_id:
            result = by_rec_id[b["recommendation_id"]]
        else:
            key = (str(b.get("tournament_id", "")),
                    str(b.get("player_name", "")).lower().strip(),
                    str(b.get("market", "")))
            result = by_key.get(key)

        if result is not None and str(result.get("outcome_status", "")) in ("won", "lost"):
            b["outcome_status"] = str(result["outcome_status"])
            b["outcome_win"] = bool(result.get("outcome_win", False))
            pnl = result.get("pnl_per_1")
            b["pnl_per_unit"] = float(pnl) if pd.notna(pnl) else None
            b["pnl_usd"] = round(float(b["stake_units"]) * float(pnl), 2) if pd.notna(pnl) else None
        else:
            b.setdefault("outcome_status", "pending")
            b["outcome_win"] = None
            b["pnl_per_unit"] = None
            b["pnl_usd"] = None
        merged.append(b)
    return merged


BANKROLL_PATH = DATA_DIR / "bets" / "bankroll.json"


def _load_bankroll() -> dict:
    try:
        return json.loads(BANKROLL_PATH.read_text()) if BANKROLL_PATH.exists() else {}
    except Exception:
        return {}


def _slip_stats(bets: list[dict]) -> dict:
    graded = [b for b in bets if b.get("outcome_status") in ("won", "lost")]
    won    = [b for b in graded if b.get("outcome_status") == "won"]
    total_staked = sum(b.get("stake_units", 1.0) for b in graded)
    # pnl_usd in slip is already stake_units * pnl_per_unit (unit-based P&L)
    total_pnl_units = sum(b.get("pnl_usd") or 0 for b in graded)

    bankroll = _load_bankroll()
    starting  = float(bankroll.get("starting_bankroll", 0))
    unit_size = float(bankroll.get("unit_size", 1))

    # Convert unit P&L to real dollars
    total_pnl_dollars = round(total_pnl_units * unit_size, 2)
    current_bankroll  = round(starting + total_pnl_dollars, 2) if starting else None

    # P&L grouped by tournament (for the mini breakdown table)
    by_tid: dict[str, dict] = {}
    for b in graded:
        tid = b.get("tournament_id", "unknown")
        if tid not in by_tid:
            by_tid[tid] = {"won": 0, "total": 0, "pnl_units": 0.0}
        by_tid[tid]["total"] += 1
        if b.get("outcome_status") == "won":
            by_tid[tid]["won"] += 1
        by_tid[tid]["pnl_units"] += b.get("pnl_usd") or 0

    return {
        "total_bets":   len(bets),
        "graded":       len(graded),
        "pending":      len(bets) - len(graded),
        "won":          len(won),
        "lost":         len(graded) - len(won),
        "total_staked": round(total_staked, 2),
        "total_pnl":    round(total_pnl_units, 2),       # in units
        "total_pnl_dollars": total_pnl_dollars,          # in real $
        "roi_pct":  round(total_pnl_units / total_staked * 100, 1) if total_staked > 0 else None,
        "hit_rate": round(len(won) / len(graded) * 100, 1) if graded else None,
        # Bankroll
        "starting_bankroll": starting or None,
        "unit_size":         unit_size,
        "current_bankroll":  current_bankroll,
        # Per-tournament breakdown
        "by_tournament": [
            {"tid": tid, **vals, "pnl_dollars": round(vals["pnl_units"] * unit_size, 2)}
            for tid, vals in by_tid.items()
        ],
    }


@app.get("/api/bet-slip")
def get_bet_slip() -> dict:
    bets = _merge_outcomes(_load_slip())
    bets = _attach_live_context(bets)
    return {"bets": bets, "stats": _slip_stats(bets)}


@app.post("/api/bet-slip")
def add_to_bet_slip(entry: BetSlipEntry) -> dict:
    import uuid
    bets = _load_slip()
    for b in bets:
        if entry.recommendation_id and b.get("recommendation_id") == entry.recommendation_id:
            return {"ok": False, "message": "Already tracking this bet"}
        if (b.get("tournament_id") == entry.tournament_id
                and b.get("player_name") == entry.player_name
                and b.get("market") == entry.market):
            return {"ok": False, "message": "Already tracking this bet"}
    bet = {
        "id": uuid.uuid4().hex[:12],
        "recommendation_id": entry.recommendation_id,
        "tournament_id": entry.tournament_id,
        "player_name": entry.player_name,
        "market": entry.market,
        "selection_label": entry.selection_label,
        "odds_american": entry.odds_american,
        "stake_units": entry.stake_units,
        "placed_at": datetime.utcnow().isoformat() + "Z",
    }
    bets.append(bet)
    _save_slip(bets)
    return {"ok": True, "id": bet["id"]}


@app.delete("/api/bet-slip/{bet_id}")
def remove_from_bet_slip(bet_id: str) -> dict:
    bets = _load_slip()
    filtered = [b for b in bets if b.get("id") != bet_id]
    if len(filtered) == len(bets):
        raise HTTPException(status_code=404, detail="Bet not found")
    _save_slip(filtered)
    return {"ok": True}