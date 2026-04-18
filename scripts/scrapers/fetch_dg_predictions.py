#!/usr/bin/env python3
"""
DataGolf Pre-Tournament Predictions Fetcher
============================================

Fetches DataGolf's pre-tournament model predictions (win/top5/top10/top20/make_cut)
for the current week's PGA Tour event.

Saves raw predictions to:
    data/datagolf/dg_predictions_{tid}.csv

Optionally blends DG predictions into outputs/latest_predictions.csv using:
    --blend   (default blend weight: 15% DG, 85% our model)

DataGolf API:
    GET https://feeds.datagolf.com/preds/pre-tournament
    Params: tour=pga, odds_format=percent, dead_heat=yes, key=<API_KEY>

Two model variants:
    baseline            — current form only
    baseline_history_fit — current form + course history fit (preferred)

Usage:
    python scripts/scrapers/fetch_dg_predictions.py --tournament-id R2026012
    python scripts/scrapers/fetch_dg_predictions.py --tournament-id R2026012 --blend
    python scripts/scrapers/fetch_dg_predictions.py --tournament-id R2026012 --blend --blend-weight 0.20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DG_DIR = DATA_DIR / "datagolf"
DG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))
from scripts.scrapers.dg_client import dg_get


# ── Name normalization ────────────────────────────────────────────────────────

def normalize_name_key(name: str) -> str:
    """Lowercase, strip suffixes, remove non-alphanumeric for matching."""
    s = str(name).strip().lower()
    # Convert "Last, First" → "first last"
    if "," in s:
        parts = s.split(",", 1)
        s = f"{parts[1].strip()} {parts[0].strip()}"
    for suffix in [" jr.", " jr", " iii", " ii", " iv"]:
        s = s.replace(suffix, "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


# ── API fetch ─────────────────────────────────────────────────────────────────

def fetch_dg_predictions(model: str = "baseline_history_fit") -> dict:
    """Fetch pre-tournament predictions from DataGolf API."""
    return dg_get("/preds/pre-tournament", {
        "tour": "pga",
        "odds_format": "percent",
        "dead_heat": "yes",
    })


def parse_response(data: dict, model: str = "baseline_history_fit") -> pd.DataFrame:
    """Parse DG JSON response into a flat DataFrame.

    Columns: dg_id, player_name, country, am, model, win, top_5, top_10, top_20, make_cut,
             sample_size, event_name, last_updated
    """
    if model not in data:
        available = [k for k in data if isinstance(data[k], list)]
        raise ValueError(f"Model '{model}' not found. Available: {available}")

    rows = data[model]
    event_name = data.get("event_name", "")
    last_updated = data.get("last_updated", "")

    records = []
    for r in rows:
        records.append({
            "dg_id":        r.get("dg_id"),
            "player_name":  r.get("player_name", ""),
            "country":      r.get("country", ""),
            "am":           r.get("am", 0),
            "dg_model":     model,
            "dg_win_prob":      r.get("win", None),
            "dg_top5_prob":     r.get("top_5", None),
            "dg_top10_prob":    r.get("top_10", None),
            "dg_top20_prob":    r.get("top_20", None),
            "dg_make_cut_prob": r.get("make_cut", None),
            "dg_sample_size":   r.get("sample_size", None),
            "dg_event_name":    event_name,
            "dg_last_updated":  last_updated,
        })

    df = pd.DataFrame(records)
    df["name_key"] = df["player_name"].apply(normalize_name_key)
    return df


# ── Blend into latest_predictions.csv ────────────────────────────────────────

def blend_into_predictions(
    dg_df: pd.DataFrame,
    tid: str,
    blend_weight: float = 0.15,
) -> pd.DataFrame:
    """Merge DG predictions into latest_predictions.csv and blend probabilities.

    Blend formula (weighted average):
        blended_win_prob  = (1 - w) * our_win_prob  + w * dg_win_prob
        blended_top10_prob = (1 - w) * our_top10 + w * dg_top10
        etc.

    The blend preserves our model's rank ordering while anchoring toward DG's
    independent estimates, which are well-calibrated and include course history.

    Args:
        dg_df: DataFrame from parse_response()
        tid: Tournament ID e.g. "R2026012"
        blend_weight: Fraction to weight toward DG (default 0.15 = 15% DG)

    Returns:
        Updated predictions DataFrame (also saves to outputs/latest_predictions.csv)
    """
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not preds_path.exists():
        print(f"[WARN] {preds_path} not found — skipping blend.")
        return pd.DataFrame()

    preds = pd.read_csv(preds_path, dtype={"player_id": str})
    preds["name_key"] = preds["player_name"].apply(normalize_name_key)

    # Build DG lookup by name_key
    dg_lookup = dg_df.set_index("name_key")

    # ── Add raw DG columns ──
    dg_cols = {
        "dg_win_prob":      "dg_win_prob",
        "dg_top5_prob":     "dg_top5_prob",
        "dg_top10_prob":    "dg_top10_prob",
        "dg_top20_prob":    "dg_top20_prob",
        "dg_make_cut_prob": "dg_make_cut_prob",
        "dg_sample_size":   "dg_sample_size",
        "dg_id":            "dg_id",
    }
    for dg_col, out_col in dg_cols.items():
        preds[out_col] = preds["name_key"].map(
            dg_lookup[dg_col] if dg_col in dg_lookup.columns else {}
        )

    matched = preds["dg_win_prob"].notna().sum()
    total = len(preds)
    print(f"[INFO] DG name match: {matched}/{total} players")

    # ── Blend probabilities ──
    # Markets to blend: win, top5, top10, top20
    blend_map = {
        ("win_prob",         "dg_win_prob"):   "win_prob",
        ("top5_prob",        "dg_top5_prob"):  "top5_prob",
        ("top10_prob",       "dg_top10_prob"): "top10_prob",
        ("top20_prob",       "dg_top20_prob"): "top20_prob",
    }

    w = blend_weight
    for (our_col, dg_col), out_col in blend_map.items():
        if our_col not in preds.columns:
            continue
        our_vals = pd.to_numeric(preds[our_col], errors="coerce")
        dg_vals  = pd.to_numeric(preds[dg_col],  errors="coerce")

        # Only blend where DG data is available; otherwise keep our value unchanged
        has_dg = dg_vals.notna()
        blended = our_vals.copy()
        blended[has_dg] = (1 - w) * our_vals[has_dg] + w * dg_vals[has_dg]

        # Save original then overwrite
        preds[f"{our_col}_pre_dg"] = our_vals   # keep original for comparison
        preds[out_col] = blended

    preds["dg_blend_weight"] = blend_weight
    preds["dg_blend_model"] = "baseline_history_fit"
    preds.drop(columns=["name_key"], inplace=True, errors="ignore")

    preds.to_csv(preds_path, index=False)
    print(f"[OK] Blended {w:.0%} DG into {preds_path.name}")

    return preds


# ── Comparison helper ─────────────────────────────────────────────────────────

def print_comparison(preds: pd.DataFrame, top_n: int = 15) -> None:
    """Print side-by-side our model vs DG for top players."""
    cols = ["player_name", "win_prob_pre_dg", "dg_win_prob", "win_prob",
            "top10_prob_pre_dg", "dg_top10_prob", "top10_prob"]
    available = [c for c in cols if c in preds.columns]
    if len(available) < 3:
        return

    df = preds[available].copy()
    df = df.sort_values("win_prob", ascending=False).head(top_n)

    print(f"\n{'Player':<25} {'Our Win':>8} {'DG Win':>8} {'Blended':>8} "
          f"{'Our T10':>8} {'DG T10':>8} {'Blend T10':>9}")
    print("-" * 80)
    for _, row in df.iterrows():
        name = str(row["player_name"])[:24]
        def pct(col):
            v = row.get(col)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return "  —  "
            return f"{float(v)*100:6.1f}%"
        print(f"{name:<25} {pct('win_prob_pre_dg'):>8} {pct('dg_win_prob'):>8} "
              f"{pct('win_prob'):>8} {pct('top10_prob_pre_dg'):>8} "
              f"{pct('dg_top10_prob'):>8} {pct('top10_prob'):>9}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch DataGolf pre-tournament predictions")
    parser.add_argument("--tournament-id", required=True, help="e.g. R2026012")
    parser.add_argument("--model", default="baseline_history_fit",
                        choices=["baseline", "baseline_history_fit"],
                        help="Which DG model to use (default: baseline_history_fit)")
    parser.add_argument("--blend", action="store_true",
                        help="Blend DG predictions into latest_predictions.csv")
    parser.add_argument("--blend-weight", type=float, default=0.15,
                        help="DG blend weight 0.0–1.0 (default: 0.15)")
    parser.add_argument("--no-save", action="store_true",
                        help="Fetch and print only, do not save CSV")
    args = parser.parse_args()

    tid = args.tournament_id.upper()

    # ── Fetch ──
    print(f"[INFO] Fetching DG pre-tournament predictions (model={args.model})...")
    try:
        data = fetch_dg_predictions()
    except requests.HTTPError as e:
        print(f"[ERROR] API request failed: {e}")
        sys.exit(1)

    event_name = data.get("event_name", "unknown")
    last_updated = data.get("last_updated", "")
    models_available = data.get("models_available", [])
    print(f"[INFO] Event: {event_name} | Last updated: {last_updated}")
    print(f"[INFO] Models available: {models_available}")

    dg_df = parse_response(data, model=args.model)
    print(f"[INFO] Parsed {len(dg_df)} players")

    # ── Save raw CSV ──
    if not args.no_save:
        out_path = DG_DIR / f"dg_predictions_{tid}.csv"
        dg_df.to_csv(out_path, index=False)
        print(f"[OK] Saved → {out_path}")

        # Also save metadata
        meta = {
            "tournament_id": tid,
            "event_name": event_name,
            "last_updated": last_updated,
            "model": args.model,
            "models_available": models_available,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "player_count": len(dg_df),
        }
        meta_path = DG_DIR / f"dg_predictions_{tid}_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"[OK] Metadata → {meta_path}")

    # ── Blend ──
    if args.blend:
        print(f"\n[INFO] Blending DG predictions (weight={args.blend_weight:.0%})...")
        preds = blend_into_predictions(dg_df, tid, blend_weight=args.blend_weight)
        if not preds.empty:
            print_comparison(preds)

    # ── Quick summary ──
    print(f"\nTop 10 by DG win probability ({args.model}):")
    top10 = dg_df.nlargest(10, "dg_win_prob")[
        ["player_name", "dg_win_prob", "dg_top10_prob", "dg_top20_prob", "dg_make_cut_prob"]
    ]
    for _, row in top10.iterrows():
        print(f"  {row['player_name']:<28} win={row['dg_win_prob']*100:5.1f}%  "
              f"top10={row['dg_top10_prob']*100:5.1f}%  "
              f"top20={row['dg_top20_prob']*100:5.1f}%  "
              f"cut={row['dg_make_cut_prob']*100:5.1f}%")


if __name__ == "__main__":
    main()
