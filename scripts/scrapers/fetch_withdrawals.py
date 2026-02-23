"""
Fetch Withdrawal Alerts
=======================
Detects player withdrawals (WD) using two sources:

1. Live leaderboard CSV — players with status == "WD" or "WITHDRAWN"
2. Field vs predictions comparison — player_ids in field but absent from
   predictions (suggesting a late withdrawal after predictions were run)

Saves results to:  data/news/withdrawals_{tournament_id}.json

Usage:
    python3 scripts/scrapers/fetch_withdrawals.py
    python3 scripts/scrapers/fetch_withdrawals.py --tournament-id R2026007
"""

import sys
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT   = Path(__file__).parent.parent.parent
DATA_DIR       = PROJECT_ROOT / "data"
LIVE_DIR       = DATA_DIR / "live"
FIELDS_DIR     = DATA_DIR / "fields"
NEWS_DIR       = DATA_DIR / "news"
OUTPUTS_DIR    = PROJECT_ROOT / "outputs"


def _latest_leaderboard(tournament_id: str | None = None) -> Path | None:
    """Return the most recent leaderboard CSV, optionally filtered by tournament."""
    candidates = sorted(
        LIVE_DIR.glob("leaderboard_r*.csv"),
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    if tournament_id:
        tid_lc = tournament_id.lower()
        filtered = [p for p in candidates if tid_lc in p.name.lower()]
        if filtered:
            return filtered[0]
    return candidates[0] if candidates else None


def _detect_from_leaderboard(lb_path: Path) -> list[dict]:
    """Find WD/Withdrawn entries in the live leaderboard."""
    wds = []
    try:
        df = pd.read_csv(lb_path)
        if "status" in df.columns and "player_name" in df.columns:
            wd_mask = df["status"].astype(str).str.upper().isin(["WD", "WITHDRAWN", "DQ"])
            for _, row in df[wd_mask].iterrows():
                wds.append({
                    "player_name": str(row["player_name"]).strip(),
                    "player_id":   str(row.get("player_id", "")).strip(),
                    "status":      str(row["status"]).strip().upper(),
                    "source":      "leaderboard",
                })
    except Exception as e:
        print(f"  Warning: could not read leaderboard {lb_path.name}: {e}")
    return wds


def _detect_from_field_vs_predictions(tournament_id: str | None) -> list[dict]:
    """
    Compare field CSV to latest_predictions.csv.
    Players present in the field but missing from predictions =
    likely withdrew after predictions were generated.
    """
    preds_path = OUTPUTS_DIR / "latest_predictions.csv"
    if not preds_path.exists():
        return []

    preds = pd.read_csv(preds_path)
    if "player_id" not in preds.columns:
        return []
    pred_ids = set(preds["player_id"].astype(str).str.strip())

    # Find best field file
    field_file = None
    if tournament_id:
        candidates = list(FIELDS_DIR.glob(f"*{tournament_id.lower()}*"))
        if candidates:
            field_file = max(candidates, key=lambda p: p.stat().st_mtime)

    if field_file is None:
        all_fields = sorted(FIELDS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if all_fields:
            field_file = all_fields[0]

    if field_file is None:
        return []

    wds = []
    try:
        field_df = pd.read_csv(field_file)
        if "player_id" in field_df.columns and "player_name" in field_df.columns:
            field_df["player_id"] = field_df["player_id"].astype(str).str.strip()
            missing = field_df[~field_df["player_id"].isin(pred_ids)]
            for _, row in missing.iterrows():
                wds.append({
                    "player_name": str(row["player_name"]).strip(),
                    "player_id":   str(row["player_id"]).strip(),
                    "status":      "POSSIBLE_WD",
                    "source":      "field_vs_predictions",
                })
    except Exception as e:
        print(f"  Warning: could not compare field file {field_file.name}: {e}")

    return wds


def fetch_withdrawals(tournament_id: str | None = None) -> list[dict]:
    lb_path = _latest_leaderboard(tournament_id)

    all_wds: list[dict] = []

    if lb_path:
        lb_wds = _detect_from_leaderboard(lb_path)
        all_wds.extend(lb_wds)
        print(f"  Leaderboard check: {len(lb_wds)} WD(s) found in {lb_path.name}")
    else:
        print("  No leaderboard file found — skipping leaderboard check")

    field_wds = _detect_from_field_vs_predictions(tournament_id)
    # Dedup against leaderboard-detected wds
    existing_ids = {w["player_id"] for w in all_wds if w["player_id"]}
    for w in field_wds:
        if w["player_id"] not in existing_ids:
            all_wds.append(w)
    if field_wds:
        print(f"  Field comparison: {len(field_wds)} possible WD(s) detected")

    # Stamp detection time
    for w in all_wds:
        w.setdefault("detected_at", datetime.now().isoformat())

    # Save
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    tid = tournament_id or "latest"
    out_path = NEWS_DIR / f"withdrawals_{tid}.json"
    with open(out_path, "w") as f:
        json.dump(all_wds, f, indent=2)

    print(f"  ✅ Saved {len(all_wds)} withdrawal record(s) → {out_path.name}")
    return all_wds


def main():
    parser = argparse.ArgumentParser(description="Detect player withdrawals")
    parser.add_argument("--tournament-id", "-t", default=None)
    args = parser.parse_args()

    print(f"\n🔍 Checking withdrawals (tournament: {args.tournament_id or 'auto'})")
    wds = fetch_withdrawals(args.tournament_id)
    if wds:
        print("\n  Withdrawals / Possible WDs:")
        for w in wds:
            print(f"    • {w['player_name']} ({w['status']}) via {w['source']}")
    else:
        print("  No withdrawals detected.")
    print()


if __name__ == "__main__":
    main()
