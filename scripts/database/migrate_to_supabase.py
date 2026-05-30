"""
migrate_to_supabase.py
======================
One-time migration: populate Supabase tables from local CSV/JSON files.
Run after creating tables via supabase_schema.sql.

Usage:
    python3 scripts/database/migrate_to_supabase.py
    python3 scripts/database/migrate_to_supabase.py --dry-run
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

sys.path.insert(0, str(PROJECT_ROOT))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

DATA_DIR    = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def get_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert(client, table: str, records: list[dict], dry_run: bool) -> int:
    if not records:
        print(f"  {table}: no records to upsert")
        return 0
    if dry_run:
        print(f"  {table}: would upsert {len(records)} records (dry run)")
        return len(records)
    # Supabase upsert in batches of 500
    batch_size = 500
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        client.table(table).upsert(batch).execute()
        total += len(batch)
    print(f"  {table}: upserted {total} records")
    return total


def _clean(val):
    """Convert NaN/inf to None for JSON serialisation."""
    if val is None:
        return None
    try:
        import math
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
    except Exception:
        pass
    return val


def df_to_records(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, row in df.iterrows():
        rows.append({k: _clean(v) for k, v in row.items()})
    return rows


# ── tournaments ───────────────────────────────────────────────────────────────

def migrate_tournaments(client, dry_run: bool):
    print("\n[tournaments]")
    path = DATA_DIR / "raw" / "schedule_2026.csv"
    if not path.exists():
        print(f"  not found: {path}")
        return
    df = pd.read_csv(path)
    df = df.rename(columns={"tournament_name": "tournament_name"})
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["end_date"]   = pd.to_datetime(df["end_date"],   errors="coerce").dt.strftime("%Y-%m-%d")
    keep = ["tournament_id", "week", "start_date", "end_date", "tournament_name",
            "tournament_type", "location", "purse", "winner_share", "power_slug"]
    df = df[[c for c in keep if c in df.columns]]
    upsert(client, "tournaments", df_to_records(df), dry_run)


# ── predictions ───────────────────────────────────────────────────────────────

def migrate_predictions(client, dry_run: bool):
    print("\n[predictions]")
    path = OUTPUTS_DIR / "latest_predictions.csv"
    if not path.exists():
        print(f"  not found: {path}")
        return
    df = pd.read_csv(path)

    keep = ["tournament_id", "player_id", "player_name", "world_rank",
            "win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob",
            "season_sg_total", "model_vs_vegas_edge", "form_trend",
            "odds_to_win", "dk_odds_direction"]
    df = df[[c for c in keep if c in df.columns]]

    # Load uses_remaining from fantasy tracker
    uses_map: dict[str, int] = {}
    tracker_path = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
    if tracker_path.exists():
        try:
            tracker = json.loads(tracker_path.read_text())
            for name, info in tracker.get("picks", {}).items():
                uses_map[str(name).strip().lower()] = int(info.get("remaining_uses", 3))
        except Exception:
            pass

    # Load recommendation + EV from strategy_reasoning.json
    rec_map: dict[str, str] = {}
    ev_map:  dict[str, int] = {}
    sr_path = OUTPUTS_DIR / "strategy_reasoning.json"
    if sr_path.exists():
        try:
            sr = json.loads(sr_path.read_text())
            for raw_name, info in sr.get("players", {}).items():
                key = str(raw_name).strip().lower()
                rec_map[key] = info.get("recommendation", "")
                ev = info.get("this_week_ev")
                if ev is not None:
                    ev_map[key] = int(ev)
        except Exception:
            pass

    # Load explanations
    exp_map: dict[str, str] = {}
    exp_path = OUTPUTS_DIR / "player_explanations.csv"
    if exp_path.exists():
        try:
            exp_df = pd.read_csv(exp_path)
            for _, row in exp_df.iterrows():
                exp_map[str(row["player_name"]).strip().lower()] = str(row.get("explanation", ""))
        except Exception:
            pass

    def _key(name: str) -> str:
        s = str(name).strip()
        if "," in s:
            parts = s.split(",", 1)
            return f"{parts[1].strip()} {parts[0].strip()}".lower()
        return s.lower()

    df["recommendation"] = df["player_name"].apply(lambda n: rec_map.get(_key(n), ""))
    df["this_week_ev"]   = df["player_name"].apply(lambda n: ev_map.get(_key(n)))
    df["explanation"]    = df["player_name"].apply(lambda n: exp_map.get(_key(n), ""))
    df["uses_remaining"] = df["player_name"].apply(lambda n: uses_map.get(_key(n).split()[-1], 3))

    upsert(client, "predictions", df_to_records(df), dry_run)


# ── live_leaderboard ──────────────────────────────────────────────────────────

def migrate_leaderboard(client, dry_run: bool):
    print("\n[live_leaderboard]")
    files = sorted(glob.glob(str(DATA_DIR / "live" / "leaderboard_r*.csv")))
    # Exclude meta files
    files = [f for f in files if "_meta" not in f]
    if not files:
        print("  no leaderboard files found")
        return
    # Only migrate the most recent (current tournament)
    path = Path(files[-1])
    tid  = path.stem.replace("leaderboard_", "").upper()
    df   = pd.read_csv(path)
    df["tournament_id"] = tid
    # Rename round score columns to lowercase
    for col in ["R1", "R2", "R3", "R4"]:
        if col in df.columns:
            df = df.rename(columns={col: col.lower()})
    keep = ["tournament_id", "position", "position_change", "player_id",
            "player_name", "country", "total", "total_numeric", "thru",
            "current_round", "r1", "r2", "r3", "r4", "total_strokes",
            "made_cut", "status", "movement", "odds_to_win", "tee_time"]
    df = df[[c for c in keep if c in df.columns]]
    upsert(client, "live_leaderboard", df_to_records(df), dry_run)


# ── bets ──────────────────────────────────────────────────────────────────────

def migrate_bets(client, dry_run: bool):
    print("\n[bets]")
    log_path = DATA_DIR / "odds" / "recommended_bets_log.csv"
    if not log_path.exists():
        # Try individual files
        files = sorted(glob.glob(str(DATA_DIR / "odds" / "recommended_bets_R*.csv")))
        if not files:
            print("  no bet files found")
            return
        dfs = [pd.read_csv(f) for f in files]
        df  = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_csv(log_path)

    keep = ["recommendation_id", "tournament_id", "recommended_at", "bet_type",
            "market", "book", "player_name", "selection_label", "odds_american",
            "book_prob", "model_prob", "edge_pts", "ev_per_1", "confidence",
            "outcome_status", "outcome_win", "pnl_per_1", "roi_pct",
            "reasoning", "graded_at"]
    df = df[[c for c in keep if c in df.columns]]

    # recommendation_id is the primary key — drop rows without it
    if "recommendation_id" in df.columns:
        df = df.dropna(subset=["recommendation_id"])

    upsert(client, "bets", df_to_records(df), dry_run)


# ── recaps ────────────────────────────────────────────────────────────────────

def migrate_recaps(client, dry_run: bool):
    print("\n[recaps]")
    files = glob.glob(str(OUTPUTS_DIR / "tournament_recap_R*.json"))
    records = []
    for f in sorted(files):
        try:
            d = json.loads(Path(f).read_text())
            records.append({
                "tournament_id":   d.get("tournament_id", ""),
                "tournament_name": d.get("tournament_name", ""),
                "narrative":       d.get("narrative", ""),
                "generated_at":    d.get("generated_at"),
            })
        except Exception as e:
            print(f"  skipping {f}: {e}")
    upsert(client, "recaps", records, dry_run)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without writing")
    parser.add_argument("--table", help="Only migrate a specific table")
    args = parser.parse_args()

    client = None if args.dry_run else get_client()

    tables = {
        "tournaments":    migrate_tournaments,
        "predictions":    migrate_predictions,
        "live_leaderboard": migrate_leaderboard,
        "bets":           migrate_bets,
        "recaps":         migrate_recaps,
    }

    if args.table:
        if args.table not in tables:
            print(f"Unknown table: {args.table}. Options: {', '.join(tables)}")
            sys.exit(1)
        tables[args.table](client, args.dry_run)
    else:
        for fn in tables.values():
            fn(client, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
