#!/usr/bin/env python3
"""
DataGolf Field Fetcher
======================

Fetches the PGA Tour field from DataGolf.

Tour options:
  pga           — current week's in-tournament field
  upcoming_pga  — next week's field (available earlier than PGA Tour publishes)
  auto          — tries upcoming_pga first; falls back to pga (default)

Saves to:
  data/datagolf/dg_field_{tid}.csv   — full DG data (one row per player)
  data/datagolf/dg_field_latest.csv  — canonical latest copy
  data/fields/field_{tid}.csv        — pipeline-compatible (player_id, player_name)

Usage:
    python scripts/scrapers/fetch_dg_field.py --tournament-id R2026012
    python scripts/scrapers/fetch_dg_field.py --tournament-id R2026013 --tour upcoming_pga
    python scripts/scrapers/fetch_dg_field.py --tournament-id R2026012 --merge-predictions
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUTS_DIR  = PROJECT_ROOT / "outputs"
DG_DIR       = DATA_DIR / "datagolf"
FIELDS_DIR   = DATA_DIR / "fields"
DG_DIR.mkdir(parents=True, exist_ok=True)
FIELDS_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get


# ── Name normalisation ────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """Lowercase, strip suffixes, alphanum only — for fuzzy matching."""
    s = str(name).strip().lower()
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    for sfx in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(sfx, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def dg_to_first_last(name: str) -> str:
    """'Scheffler, Scottie' → 'Scottie Scheffler'"""
    if "," in str(name):
        parts = str(name).split(",", 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return str(name).strip()


# ── API fetch ─────────────────────────────────────────────────────────────────

def fetch_field(tour: str) -> dict:
    return dg_get("/field-updates", {"tour": tour, "file_format": "json"})


def fetch_field_auto() -> tuple[dict, str]:
    """Try pga (current week) first; fall back to upcoming_pga. Returns (raw, tour_used).

    pga is preferred because upcoming_pga returns the NEXT event during tournament week,
    which would give us the wrong field and no tee times.
    """
    for tour in ("pga", "upcoming_pga"):
        try:
            raw = fetch_field(tour)
            if raw.get("field"):
                return raw, tour
        except Exception as e:
            print(f"[WARN] {tour} failed: {e}")
    raise RuntimeError("Both pga and upcoming_pga fetch attempts failed")


# ── Flatten ───────────────────────────────────────────────────────────────────

def flatten_field(raw: dict) -> pd.DataFrame:
    """One row per player with tee times pivoted to columns."""
    event_name    = raw.get("event_name", "")
    event_id      = raw.get("event_id", "")
    course_name   = raw.get("course_name", "")
    current_round = raw.get("current_round")
    last_updated  = raw.get("last_updated", "")
    fetched_at    = datetime.now(timezone.utc).isoformat()

    rows = []
    for p in raw.get("field", []):
        row: dict = {
            "player_name_dg":   p.get("player_name", ""),
            "player_name":      dg_to_first_last(p.get("player_name", "")),
            "dg_id":            p.get("dg_id"),
            "player_num":       p.get("player_num"),
            "dg_rank":          p.get("dg_rank"),
            "owgr_rank":        p.get("owgr_rank"),
            "tour_rank":        p.get("tour_rank"),
            "country":          p.get("country", ""),
            "am":               p.get("am", 0),
            "pageviews":        p.get("pre_tourn_pageviews"),
            "event_name":       event_name,
            "event_id":         event_id,
            "course_name":      course_name,
            "current_round":    current_round,
            "last_updated":     last_updated,
            "fetched_at":       fetched_at,
        }
        # Pivot tee times: r1_teetime, r1_wave, r1_starthole, r2_...
        for tt in p.get("teetimes", []):
            rn = tt.get("round_num", "")
            row[f"r{rn}_teetime"]   = tt.get("teetime", "")
            row[f"r{rn}_wave"]      = tt.get("wave", "")
            row[f"r{rn}_starthole"] = tt.get("start_hole", "")
        rows.append(row)

    return pd.DataFrame(rows)


# ── Write pipeline-compatible field CSV ──────────────────────────────────────

def write_pipeline_field(field_df: pd.DataFrame, tid: str) -> Path:
    """Write data/fields/field_{tid}.csv with player_id,player_name columns.

    player_id = player_num (PGA Tour player ID from DG field data).
    player_name kept in 'Last, First' DG format to match existing pipeline.
    """
    pipeline_df = pd.DataFrame({
        "player_id":   field_df["player_num"],
        "player_name": field_df["player_name_dg"],  # keep "Last, First" format
    }).dropna(subset=["player_id"])
    pipeline_df["player_id"] = pipeline_df["player_id"].astype(int)

    out_path = FIELDS_DIR / f"field_{tid}.csv"
    pipeline_df.to_csv(out_path, index=False)
    print(f"[OK] Pipeline field → {out_path}  ({len(pipeline_df)} players)")
    return out_path


# ── Merge dg_id into latest_predictions.csv ──────────────────────────────────

def merge_into_predictions(field_df: pd.DataFrame) -> int:
    """Add dg_id, dg_rank, dg_name_key to latest_predictions.csv.

    Returns number of players matched.
    """
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not preds_path.exists():
        print(f"[WARN] {preds_path} not found — skipping merge.")
        return 0

    preds = pd.read_csv(preds_path)

    # Build lookup: norm_key → (dg_id, dg_rank, player_name_dg)
    field_df["_nkey"] = field_df["player_name"].apply(normalize_name)
    lookup = field_df.set_index("_nkey")[["dg_id", "dg_rank", "owgr_rank", "player_name_dg"]].to_dict("index")

    preds["_nkey"] = preds["player_name"].apply(normalize_name)

    matched = 0
    dg_ids, dg_ranks, owgr_ranks, dg_name_keys = [], [], [], []
    for nk in preds["_nkey"]:
        hit = lookup.get(nk)
        if hit:
            matched += 1
            dg_ids.append(hit["dg_id"])
            dg_ranks.append(hit["dg_rank"])
            owgr_ranks.append(hit["owgr_rank"])
            dg_name_keys.append(hit["player_name_dg"])
        else:
            dg_ids.append(None)
            dg_ranks.append(None)
            owgr_ranks.append(None)
            dg_name_keys.append(None)

    preds["dg_id"]       = dg_ids
    preds["dg_rank"]     = dg_ranks
    preds["owgr_rank"]   = owgr_ranks
    preds["dg_name_key"] = dg_name_keys
    preds.drop(columns=["_nkey"], inplace=True)

    preds.to_csv(preds_path, index=False)
    print(f"[OK] Merged dg_id/dg_rank into {preds_path.name}  ({matched}/{len(preds)} matched)")
    return matched


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf field + tee times")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026012")
    parser.add_argument(
        "--tour", default="auto",
        choices=["auto", "pga", "upcoming_pga"],
        help="DG tour param: auto (default) tries upcoming_pga then pga",
    )
    parser.add_argument("--merge-predictions", action="store_true",
                        help="Merge dg_id/dg_rank into outputs/latest_predictions.csv")
    args = parser.parse_args()
    tid = args.tournament_id.upper()

    print(f"[INFO] Fetching DG field (tour={args.tour})...")
    if args.tour == "auto":
        raw, tour_used = fetch_field_auto()
        print(f"[INFO] Using tour={tour_used}")
    else:
        raw = fetch_field(args.tour)
        tour_used = args.tour

    event_name = raw.get("event_name", "unknown")
    print(f"[INFO] Event: {event_name}  |  Round: {raw.get('current_round')}  |  Updated: {raw.get('last_updated')}")

    df = flatten_field(raw)
    print(f"[INFO] {len(df)} players")

    # Sort by dg_rank
    df = df.sort_values("dg_rank", na_position="last").reset_index(drop=True)

    # Save full DG CSV
    out_path = DG_DIR / f"dg_field_{tid}.csv"
    df.to_csv(out_path, index=False)
    print(f"[OK] DG field → {out_path}")

    latest_path = DG_DIR / "dg_field_latest.csv"
    df.to_csv(latest_path, index=False)
    print(f"[OK] Latest   → {latest_path}")

    # Save pipeline-compatible field CSV
    write_pipeline_field(df, tid)

    # Export tee times to data/live/tee_times_{tid}_r{n}.csv
    tz_offset = float(raw.get("tz_offset") or 0)
    write_tee_times_csv(df, tid, tz_offset=tz_offset)

    # Print top 15
    print(f"\nTop 15 by DG rank  [{event_name}]:")
    print(f"  {'Player':<28} {'DG':>4} {'WR':>4} {'Tour':>5}  {'R1 Tee':>12}  {'R2 Tee':>12}  {'R3 Tee':>12}")
    print("  " + "-" * 80)
    for _, r in df.head(15).iterrows():
        def tt(rn):
            v = str(r.get(f"r{rn}_teetime", "")).strip()
            return v.split(" ")[-1] if " " in v else v or "—"
        print(f"  {str(r['player_name']):<28} {str(r.get('dg_rank','—')):>4} "
              f"{str(r.get('owgr_rank','—')):>4} {str(r.get('tour_rank','—')):>5}  "
              f"{tt(1):>12}  {tt(2):>12}  {tt(3):>12}")

    if args.merge_predictions:
        print()
        merge_into_predictions(df)


def write_tee_times_csv(df: pd.DataFrame, tid: str, tz_offset: float = 0.0) -> list[Path]:
    """Export r1/r2/r3/r4 tee times from the DG field DataFrame.

    DG stores teetime as local time strings ('2026-06-11 14:27').
    We write data/live/tee_times_{tid}_r{n}.csv matching the format
    expected by the API's /api/tee-times endpoint.
    """
    from datetime import timedelta

    live_dir = DATA_DIR / "live"
    live_dir.mkdir(exist_ok=True)
    written = []

    rounds_present = set()
    for col in df.columns:
        if col.startswith("r") and col.endswith("_teetime"):
            try:
                rn = int(col[1])
                rounds_present.add(rn)
            except ValueError:
                pass

    for rn in sorted(rounds_present):
        tt_col  = f"r{rn}_teetime"
        wv_col  = f"r{rn}_wave"
        sh_col  = f"r{rn}_starthole"
        sub = df[df[tt_col].notna() & (df[tt_col] != "")].copy()
        if sub.empty:
            continue

        rows = []
        for _, r in sub.iterrows():
            raw_tt = str(r[tt_col]).strip()  # "2026-06-11 14:27" local
            try:
                local_dt = datetime.strptime(raw_tt, "%Y-%m-%d %H:%M")
                utc_dt   = local_dt - timedelta(hours=tz_offset)
                tee_time_local = local_dt.isoformat()
                tee_time_utc   = utc_dt.replace(tzinfo=timezone.utc).isoformat()
                tee_time_str   = local_dt.strftime("%-I:%M %p")
            except Exception:
                tee_time_local = raw_tt
                tee_time_utc   = raw_tt
                tee_time_str   = raw_tt

            rows.append({
                "player_id":     int(r["player_num"]) if pd.notna(r.get("player_num")) else "",
                "player_name":   r.get("player_name_dg", ""),
                "round":         rn,
                "tee_time_str":  tee_time_str,
                "tee_time_utc":  tee_time_utc,
                "tee_time_local": tee_time_local,
                "start_tee":     int(r[sh_col]) if pd.notna(r.get(sh_col)) and r.get(sh_col) != "" else 1,
            })

        out = live_dir / f"tee_times_{tid}_r{rn}.csv"
        pd.DataFrame(rows).sort_values("tee_time_local").to_csv(out, index=False)
        print(f"[OK] Tee times R{rn} → {out}  ({len(rows)} players)")
        written.append(out)

    return written


if __name__ == "__main__":
    main()
