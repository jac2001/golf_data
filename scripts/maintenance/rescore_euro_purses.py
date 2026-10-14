#!/usr/bin/env python3
"""
Rescore settled DP World Tour events with the purse table.
===========================================================
Euro earnings are ESTIMATED: purse x the standard DPWT payout share per
finish (fetch_euro_events.PAYOUT_PCT, ties split). Until Oct 14, 2026 most
events were scored at a flat $3M default; data/raw/euro_purses.csv now
holds the real 2026 purses. Payouts are linear in the purse, so
rescoring an event is one factor: table purse / purse it was scored at.

Idempotent: the scored-at purse is read back from the data itself (the
winner's share is PAYOUT_PCT[0] of the purse; a tie at 1st splits
1st+2nd), so a second run finds every event already at its table purse
and changes nothing.

Every game reads euro earnings live from these files through the API
(no earnings are stored in Neon), so standings, receipts and recaps
follow automatically.

Usage:
    python3 scripts/maintenance/rescore_euro_purses.py            # dry run
    python3 scripts/maintenance/rescore_euro_purses.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "scrapers"))
import euro_schedule  # noqa: E402
from fetch_euro_events import PAYOUT_PCT  # noqa: E402


def scored_at_purse(g: pd.DataFrame) -> float:
    """The purse an event was scored at, from its own payouts."""
    pos = g["position"].astype(str).str.upper().str.lstrip("T")
    winners = (pos == "1").sum()
    if winners == 0:
        raise ValueError("no winner row")
    share = sum(PAYOUT_PCT[:winners]) / winners / 100.0   # ties split the pool
    return float(g.loc[pos == "1", "earnings"].max()) / share


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    table = euro_schedule.load_purses()
    for path in sorted((ROOT / "data" / "historical").glob("leaderboards_euro_2*.csv")):
        lb = pd.read_csv(path)
        changed = False
        for tid, g in lb.groupby("tournament_id", sort=False):
            name = str(g["tournament_name"].iloc[0])
            new = euro_schedule.purse_for(name, table)
            if new is None:
                print(f"  {tid} {name}: no purse row — left as scored")
                continue
            old = scored_at_purse(g)
            if abs(new - old) / old < 0.005:          # already at the table purse
                print(f"  {tid} {name}: scored at ${old:,.0f} = table — unchanged")
                continue
            factor = new / old
            print(f"  {tid} {name}: ${old:,.0f} -> ${new:,.0f} (x{factor:.3f}), "
                  f"winner ${g['earnings'].max():,.0f} -> ${g['earnings'].max() * factor:,.0f}")
            lb.loc[g.index, "earnings"] = (g["earnings"] * factor).round(2)
            changed = True
        if changed and args.write:
            lb.to_csv(path, index=False)
            print(f"wrote {path.relative_to(ROOT)}")
        elif changed:
            print(f"(dry run — rerun with --write to update {path.name})")


if __name__ == "__main__":
    main()
