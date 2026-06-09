#!/usr/bin/env python3
"""
Backfill Prediction Results
============================
Matches completed tournament leaderboards against prediction_history.csv and
fills in actual_position, actual_top5, actual_top10, actual_top20, actual_won.

Also de-duplicates prediction_history (each tournament was saved multiple times
under different date-based IDs; this canonicalises to R-prefixed IDs from the
schedule and keeps one row per player per tournament).

After backfilling, prints a calibration summary so you can see how well the
model's predicted probabilities matched actual outcomes.

Usage:
    python scripts/predictions/backfill_results.py
    python scripts/predictions/backfill_results.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TRACKING_DIR = DATA_DIR / "prediction_tracking"
PRED_HIST = TRACKING_DIR / "prediction_history.csv"
PRED_HIST_OUTPUTS = PROJECT_ROOT / "outputs" / "prediction_history.csv"
LB_FILE = DATA_DIR / "historical" / "leaderboards_2026.csv"
SCHED_FILE = DATA_DIR / "raw" / "schedule_2026.csv"


# ── Name normalisation ─────────────────────────────────────────────────────────

def _norm_name(name) -> str:
    """Lowercase, strip accents, remove suffixes, normalise whitespace.
    Handles 'Last, First' and 'First Last' formats.
    """
    if pd.isna(name):
        return ""
    s = str(name).strip()
    # NFD decompose → strip combining characters (accents)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    # 'Last, First' → 'first last'
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(suffix, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


# ── Tournament ID resolution ───────────────────────────────────────────────────

_MANUAL_TID_MAP: dict[str, str] = {
    # Early-season tournaments not in schedule CSV (added manually)
    "american_express":           "R2026002",
    "the_american_express":       "R2026002",
    "farmers_insurance_open":     "R2026004",
    "sony_open_in_hawaii":        "R2026006",
    "wm_phoenix_open":            "R2026003",
    "at_t_pebble_beach_pro_am":   "R2026005",
    "standard":                   "R2026007",  # The Genesis had a 'standard' alt-id
}


def _build_tid_lookup(sched: pd.DataFrame) -> dict[str, str]:
    """Build a mapping from normalised tournament name fragments → R-prefixed ID.

    We normalise schedule names and also generate short slugs so that
    date-based IDs like '2026-03-02_arnold_palmer_invitational' can be
    matched to R2026009.
    """
    lookup: dict[str, str] = {}
    for _, row in sched.iterrows():
        tid = str(row["tournament_id"]).strip()
        raw_name = str(row["tournament_name"]).strip()
        slug = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
        lookup[slug] = tid
        # Also store partial matches (first 3+ words)
        words = slug.split("_")
        if len(words) >= 3:
            lookup["_".join(words[:3])] = tid
        if len(words) >= 2:
            lookup["_".join(words[:2])] = tid
    return lookup


def _resolve_tid(raw_tid: str, lookup: dict[str, str]) -> str | None:
    """Try to map a date-based prediction ID to an R-prefixed schedule ID.

    Steps:
    1. If already R-prefixed, return as-is after verifying it's in lookup values.
    2. Strip the date prefix (YYYY-MM-DD_) and match the slug.
    3. Try progressively shorter slug prefixes.
    """
    raw = str(raw_tid).strip()

    # Already R-prefixed
    if re.match(r"^R\d{7}$", raw, re.IGNORECASE):
        return raw.upper()

    # Strip date prefix: '2026-03-02_arnold_palmer_invitational' → 'arnold_palmer_invitational'
    slug = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", raw)
    slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")

    # Check manual map first (early-season tournaments not in schedule CSV)
    if slug in _MANUAL_TID_MAP:
        return _MANUAL_TID_MAP[slug]

    if slug in lookup:
        return lookup[slug]

    # Try progressively shorter prefixes
    parts = slug.split("_")
    for n in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:n])
        if candidate in _MANUAL_TID_MAP:
            return _MANUAL_TID_MAP[candidate]
        if candidate in lookup:
            return lookup[candidate]

    return None


# ── Position parsing ───────────────────────────────────────────────────────────

def _parse_pos(raw) -> int | None:
    """Parse a position string like '1', 'T2', 'CUT', 'WD' etc. to int."""
    if pd.isna(raw):
        return None
    s = str(raw).strip().upper()
    if s in {"CUT", "MC", "WD", "DQ", "MDF", "WDJ", "RTD"}:
        return 999  # missed cut / withdrew
    s = re.sub(r"^T", "", s)  # strip T from ties
    try:
        return int(float(s))
    except ValueError:
        return None


# ── Core backfill ──────────────────────────────────────────────────────────────

def backfill(dry_run: bool = False) -> dict:
    # ── Load data ───────────────────────────────────────────────────────────────
    pred = pd.read_csv(PRED_HIST)
    lb   = pd.read_csv(LB_FILE)
    sched = pd.read_csv(SCHED_FILE, dtype=str)

    print(f"Loaded {len(pred)} prediction rows, {len(lb)} leaderboard rows")

    # ── Build tournament ID lookup ──────────────────────────────────────────────
    tid_lookup = _build_tid_lookup(sched)

    # ── Resolve canonical R-prefixed IDs for every prediction row ──────────────
    pred["_canon_tid"] = pred["tournament_id"].apply(
        lambda x: _resolve_tid(x, tid_lookup)
    )

    unresolved = pred[pred["_canon_tid"].isna()]["tournament_id"].unique()
    if len(unresolved):
        print(f"  Could not resolve {len(unresolved)} tournament IDs:")
        for u in unresolved:
            print(f"    {u}")

    # ── Build leaderboard lookup: (canon_tid, name_key) → row ──────────────────
    lb["_name_key"] = lb["player_name"].apply(_norm_name)
    lb["_pos_int"]  = lb["position"].apply(_parse_pos)
    lb_idx: dict[tuple, dict] = {}
    for _, row in lb.iterrows():
        key = (str(row["tournament_id"]).upper(), row["_name_key"])
        # Keep only one entry per (tid, player) — prefer lower position
        if key not in lb_idx or (row["_pos_int"] or 999) < (lb_idx[key].get("_pos_int") or 999):
            lb_idx[key] = row.to_dict()

    print(f"  Leaderboard index: {len(lb_idx)} entries across "
          f"{lb['tournament_id'].nunique()} tournaments")

    # ── Deduplicate prediction rows ─────────────────────────────────────────────
    # When multiple date-based IDs map to the same canon_tid + player,
    # keep the row with result_recorded=True first, then the most recent save.
    pred["_name_key"] = pred["player_name"].apply(_norm_name)

    # Sort so result_recorded=True rows come first, then by row index desc (most recent)
    pred["_has_result"] = pred["result_recorded"].fillna(False).astype(bool)
    pred_sorted = pred.sort_values(["_has_result", "tournament_id"], ascending=[False, False])
    pred_dedup = pred_sorted.drop_duplicates(subset=["_canon_tid", "_name_key"], keep="first").copy()
    pred_dedup = pred_dedup[pred_dedup["_canon_tid"].notna()].copy()

    print(f"  After dedup: {len(pred_dedup)} rows "
          f"({len(pred) - len(pred_dedup)} duplicates removed)")

    # ── Match results ───────────────────────────────────────────────────────────
    matched = filled = already = 0
    rows = []
    for _, row in pred_dedup.iterrows():
        canon_tid = row["_canon_tid"]
        name_key  = row["_name_key"]
        lb_row = lb_idx.get((canon_tid, name_key))

        new_row = row.to_dict()

        if lb_row is not None:
            matched += 1
            pos = lb_row.get("_pos_int")
            if pos is not None and not row.get("result_recorded"):
                filled += 1
                # Determine finish outcomes
                actual_top5  = bool(pos <= 5)
                actual_top10 = bool(pos <= 10)
                actual_top20 = bool(pos <= 20)
                actual_won   = bool(pos == 1)

                new_row["actual_position"] = pos
                new_row["actual_won"]      = actual_won
                new_row["actual_top5"]     = actual_top5
                new_row["actual_top10"]    = actual_top10
                new_row["actual_top20"]    = actual_top20
                new_row["result_recorded"] = True
            else:
                already += 1
        else:
            # Check if leaderboard has data for this tournament at all
            # (if not, the tournament may not be complete yet — skip silently)
            pass

        # Normalise tournament_id to canonical
        new_row["tournament_id"] = canon_tid
        rows.append(new_row)

    out = pd.DataFrame(rows)
    # Drop internal columns
    out = out[[c for c in out.columns if not c.startswith("_")]].copy()

    print(f"\nResults:")
    print(f"  Matched in leaderboard:      {matched}")
    print(f"  Newly filled (result_recorded set): {filled}")
    print(f"  Already had results:         {already}")
    print(f"  Output rows:                 {len(out)}")

    if not dry_run:
        # Back up original
        backup = PRED_HIST.with_suffix(".bak.csv")
        import shutil
        shutil.copy(PRED_HIST, backup)
        out.to_csv(PRED_HIST, index=False)
        # Mirror to outputs/ so dashboard and chatbot pick it up
        shutil.copy(PRED_HIST, PRED_HIST_OUTPUTS)
        print(f"\nSaved → {PRED_HIST}  (backup → {backup.name})")
        print(f"Mirrored → {PRED_HIST_OUTPUTS}")

        # Upsert into DuckDB
        try:
            import sys as _sys
            _sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
            from db import get_conn

            upsert = out.copy()
            upsert["player_id"] = upsert["player_id"].astype(str)
            for _bc in ["actual_won", "actual_top5", "actual_top10", "actual_top20", "result_recorded"]:
                if _bc in upsert.columns:
                    upsert[_bc] = upsert[_bc].astype(str).str.lower().map(
                        {"true": True, "false": False, "1": True, "0": False}
                    )

            with get_conn() as conn:
                conn.register("upsert_view", upsert)
                conn.execute("DELETE FROM prediction_history")
                conn.execute("""
                    INSERT INTO prediction_history
                    SELECT tournament_id, tournament_name, tournament_date, player_name, player_id,
                           predicted_win_prob, predicted_top5_prob, predicted_top10_prob,
                           predicted_top20_prob, predicted_ev, world_rank, course_fit,
                           CAST(actual_position AS VARCHAR),
                           CAST(actual_won AS BOOLEAN),
                           CAST(actual_top5 AS BOOLEAN),
                           CAST(actual_top10 AS BOOLEAN),
                           CAST(actual_top20 AS BOOLEAN),
                           CAST(result_recorded AS BOOLEAN)
                    FROM upsert_view
                """)
                n_db = conn.execute("SELECT COUNT(*) FROM prediction_history").fetchone()[0]
            print(f"DB upsert: {n_db} rows in prediction_history")
        except Exception as _e:
            print(f"[WARN] DB upsert failed (CSV is authoritative): {_e}")
    else:
        print("\n[DRY RUN] No files written.")

    return {"matched": matched, "filled": filled, "out_rows": len(out)}


# ── Calibration summary ────────────────────────────────────────────────────────

def _to_bool_series(s: pd.Series) -> pd.Series:
    """Robustly convert a column that may contain True/False/1/0/1.0/0.0/'True'/'False' to bool."""
    def _coerce(x) -> bool:
        if pd.isna(x):
            return False
        try:
            return bool(int(float(x)))   # handles 0, 1, 0.0, 1.0, '0', '1'
        except (ValueError, TypeError):
            pass
        return str(x).strip().lower() not in {"false", "no", "nan", "none", ""}
    return s.map(_coerce)


def calibration_summary() -> None:
    """Print a quick calibration report using the now-filled prediction_history."""
    pred = pd.read_csv(PRED_HIST)
    graded = pred[pred["result_recorded"] == True].copy()

    if graded.empty:
        print("No graded rows found.")
        return

    graded["predicted_win_prob"]   = pd.to_numeric(graded["predicted_win_prob"],   errors="coerce")
    graded["predicted_top5_prob"]  = pd.to_numeric(graded["predicted_top5_prob"],  errors="coerce")
    graded["predicted_top10_prob"] = pd.to_numeric(graded["predicted_top10_prob"], errors="coerce")
    if "predicted_top20_prob" in graded.columns:
        graded["predicted_top20_prob"] = pd.to_numeric(graded["predicted_top20_prob"], errors="coerce")

    # Convert outcome columns — they may be stored as 'True'/'False' strings or 0/1
    for col in ["actual_won", "actual_top5", "actual_top10", "actual_top20"]:
        if col in graded.columns:
            graded[col] = _to_bool_series(graded[col])

    print(f"\n=== Calibration Summary ({len(graded)} graded predictions) ===\n")

    for market, pred_col, actual_col in [
        ("Win",   "predicted_win_prob",   "actual_won"),
        ("Top 5", "predicted_top5_prob",  "actual_top5"),
        ("Top 10","predicted_top10_prob", "actual_top10"),
        ("Top 20","predicted_top20_prob", "actual_top20"),
    ]:
        if actual_col not in graded.columns:
            continue
        sub = graded[[pred_col, actual_col]].dropna()
        if sub.empty:
            continue
        pred_avg   = sub[pred_col].mean() * 100
        actual_avg = sub[actual_col].mean() * 100
        ratio      = actual_avg / pred_avg if pred_avg > 0 else float("nan")

        # Calibration by bucket
        sub["bucket"] = pd.cut(sub[pred_col], bins=[0,.02,.05,.10,.15,.25,.50,1.0], labels=False)
        bucket_stats = sub.groupby("bucket", observed=True).agg(
            n=(pred_col, "count"),
            pred=(pred_col, "mean"),
            actual=(actual_col, "mean"),
        )

        print(f"{market}:  pred avg={pred_avg:.2f}%  actual avg={actual_avg:.2f}%  "
              f"ratio={ratio:.2f}x  (n={len(sub)})")
        for _, brow in bucket_stats.iterrows():
            bar = "#" * int(brow["actual"] * 50)
            print(f"  pred {brow['pred']*100:5.1f}% → actual {brow['actual']*100:5.1f}%  "
                  f"n={brow['n']:4.0f}  {bar}")
        print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without writing files")
    parser.add_argument("--calibration-only", action="store_true",
                        help="Skip backfill, just print calibration summary")
    args = parser.parse_args()

    if not args.calibration_only:
        backfill(dry_run=args.dry_run)

    calibration_summary()


if __name__ == "__main__":
    main()
