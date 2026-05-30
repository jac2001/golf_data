"""
supabase_sync.py
================
Lightweight helpers to push current data into Supabase after each
pipeline step. Called by scheduled_refresh.py and run_pipeline.py.

Each function is silent on failure — Supabase being unavailable
should never crash the local pipeline.
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

DATA_DIR    = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        pass
    return _client


_DASH_VALUES = {"-", "--", "N/A", "n/a", "nan", ""}

def _clean(val):
    if val is None:
        return None
    if isinstance(val, str) and val.strip() in _DASH_VALUES:
        return None
    try:
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
    except Exception:
        pass
    # Convert numpy types to native Python
    try:
        import numpy as np
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        if isinstance(val, (np.bool_,)):
            return bool(val)
    except ImportError:
        pass
    return val


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for _, row in df.iterrows()]


_CONFLICT_COLS = {
    "predictions":      "tournament_id,player_name",
    "live_leaderboard": "tournament_id,player_name",
    "bets":             "recommendation_id",
    "recaps":           "tournament_id",
    "tournaments":      "tournament_id",
}

def _upsert(table: str, records: list[dict], batch_size: int = 500) -> int:
    if not records:
        return 0
    sb = _get_client()
    if sb is None:
        return 0
    conflict = _CONFLICT_COLS.get(table)
    try:
        total = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            q = sb.table(table).upsert(batch)
            if conflict:
                q = sb.table(table).upsert(batch, on_conflict=conflict)
            q.execute()
            total += len(batch)
        return total
    except Exception as e:
        print(f"  [supabase_sync] {table} upsert failed: {e}")
        return 0


# ── Public sync functions ─────────────────────────────────────────────────────

def sync_predictions(tid: str | None = None) -> int:
    """Push latest_predictions.csv → predictions table."""
    path = OUTPUTS_DIR / "latest_predictions.csv"
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
        if tid:
            df["tournament_id"] = tid
        keep = ["tournament_id", "player_id", "player_name", "world_rank",
                "win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob",
                "season_sg_total", "model_vs_vegas_edge", "form_trend",
                "odds_to_win", "dk_odds_direction"]
        df = df[[c for c in keep if c in df.columns]]

        # Merge uses_remaining
        uses_map: dict[str, int] = {}
        tracker_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
        if tracker_path.exists():
            try:
                tracker = json.loads(tracker_path.read_text())
                for name, info in tracker.get("picks", {}).items():
                    uses_map[str(name).strip().lower()] = int(info.get("remaining_uses", 3))
            except Exception:
                pass

        def _key(name: str) -> str:
            s = str(name).strip()
            if "," in s:
                parts = s.split(",", 1)
                return f"{parts[1].strip()} {parts[0].strip()}".lower()
            return s.lower()

        df["uses_remaining"] = df["player_name"].apply(
            lambda n: uses_map.get(_key(n).split()[-1], 3)
        )

        n = _upsert("predictions", _df_to_records(df))
        print(f"  [supabase] predictions: {n} rows")
        return n
    except Exception as e:
        print(f"  [supabase_sync] predictions failed: {e}")
        return 0


def sync_leaderboard(tid: str) -> int:
    """Push live leaderboard CSV → live_leaderboard table."""
    path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
        df["tournament_id"] = tid.upper()
        for col in ["R1", "R2", "R3", "R4"]:
            if col in df.columns:
                df = df.rename(columns={col: col.lower()})
        keep = ["tournament_id", "position", "position_change", "player_id",
                "player_name", "country", "total", "total_numeric", "thru",
                "current_round", "r1", "r2", "r3", "r4", "total_strokes",
                "made_cut", "status", "movement", "odds_to_win", "tee_time"]
        df = df[[c for c in keep if c in df.columns]]
        n = _upsert("live_leaderboard", _df_to_records(df))
        print(f"  [supabase] live_leaderboard: {n} rows")
        return n
    except Exception as e:
        print(f"  [supabase_sync] leaderboard failed: {e}")
        return 0


def sync_bets(tid: str) -> int:
    """Push recommended bets CSV → bets table."""
    candidates = sorted(
        glob.glob(str(DATA_DIR / "odds" / f"recommended_bets*{tid}*.csv")),
        key=os.path.getmtime, reverse=True,
    )
    if not candidates:
        return 0
    try:
        df = pd.read_csv(candidates[0])
        keep = ["recommendation_id", "tournament_id", "recommended_at", "bet_type",
                "market", "book", "player_name", "selection_label", "odds_american",
                "book_prob", "model_prob", "edge_pts", "ev_per_1", "confidence",
                "outcome_status", "outcome_win", "pnl_per_1", "roi_pct",
                "reasoning", "graded_at"]
        df = df[[c for c in keep if c in df.columns]]
        if "recommendation_id" in df.columns:
            df = df.dropna(subset=["recommendation_id"])
        n = _upsert("bets", _df_to_records(df))
        print(f"  [supabase] bets: {n} rows")
        return n
    except Exception as e:
        print(f"  [supabase_sync] bets failed: {e}")
        return 0


def sync_recap(tid: str) -> int:
    """Push a single tournament recap JSON → recaps table."""
    path = OUTPUTS_DIR / f"tournament_recap_{tid.upper()}.json"
    if not path.exists():
        return 0
    try:
        d = json.loads(path.read_text())
        record = {
            "tournament_id":   d.get("tournament_id", ""),
            "tournament_name": d.get("tournament_name", ""),
            "narrative":       d.get("narrative", ""),
            "generated_at":    d.get("generated_at"),
        }
        n = _upsert("recaps", [record])
        print(f"  [supabase] recaps: {n} rows")
        return n
    except Exception as e:
        print(f"  [supabase_sync] recap failed: {e}")
        return 0


def sync_tournaments() -> int:
    """Push schedule CSV → tournaments table."""
    path = DATA_DIR / "raw" / "schedule_2026.csv"
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path)
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce").dt.strftime("%Y-%m-%d")
        keep = ["tournament_id", "week", "start_date", "end_date", "tournament_name",
                "tournament_type", "location", "purse", "winner_share", "power_slug"]
        df = df[[c for c in keep if c in df.columns]]
        n = _upsert("tournaments", _df_to_records(df))
        print(f"  [supabase] tournaments: {n} rows")
        return n
    except Exception as e:
        print(f"  [supabase_sync] tournaments failed: {e}")
        return 0