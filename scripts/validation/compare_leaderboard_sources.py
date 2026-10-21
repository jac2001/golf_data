#!/usr/bin/env python3
"""
compare_leaderboard_sources.py — do DataGolf's results agree with PGA TOUR's?
=============================================================================
The January retrain will move the model from the PGA TOUR leaderboard files
(leaderboards_{season}.csv) to DataGolf's (leaderboards_dg_{season}.csv).
Before it does, we need evidence the two describe the same tournaments the
same way. This compares every (event, player) pair both sources have.

    python3 scripts/validation/compare_leaderboard_sources.py            # 2016-2026
    python3 scripts/validation/compare_leaderboard_sources.py --worst 10

The interesting part is `agreement()` (Jack's). The plumbing below loads
the files and prints the result.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "data" / "historical"
COLS = ["tournament_id", "player_id", "player_name", "position"]


# ── TODO(Jack): agreement ─────────────────────────────────────────────────────
#
# pga, dg: DataFrames with at least tournament_id, player_id, position
#          (strings; positions look like "1", "T5", "CUT", "W/D", "WD", "DQ").
#
# Return a dict:
#   events:       number of tournament_ids in BOTH sources
#   pairs:        number of (tournament_id, player_id) pairs in both
#   match_rate:   share of those pairs whose positions agree (0.0 when pairs == 0)
#   only_pga:     players in a shared event that only PGA TOUR lists
#   only_dg:      players in a shared event that only DataGolf lists
#   worst:        list of (tournament_id, match_rate) for shared events, lowest
#                 first, at most `worst_n` of them
#
# Facts the tests pin:
#   - Only events both sources have are compared (an event only one source
#     has is a coverage gap, not a disagreement).
#   - "T5" and "T5" agree; "T5" and "T6" don't.
#   - Withdrawals are written two ways: PGA TOUR "W/D", DataGolf "WD". Same thing.
#   - Row order doesn't matter.
#
# Decisions that are yours (reason in a comment):
#   a. Does "5" agree with "T5"? (One source might drop the T on a tie.)
#   b. A player PGA TOUR lists as "CUT" and DataGolf as "WD" (withdrew after
#      missing the cut): agree or disagree? Either way they didn't play the
#      weekend, which is what "made the cut" lines care about.
#   c. What match_rate would make you trust DataGolf for the retrain? Put it
#      in TRUST_RATE with your reason; main() prints PASS/FAIL against it.
#
# Done when: python3 scripts/validation/test_compare_leaderboard_sources.py
# passes, plus one test of your own for decision (a) or (b).
# Yes, 5 should agree with T5 because its still worth the same place
# No a cut is different than a withdraw. WD should be treated differently no matter when it happens
# 
TRUST_RATE = 0.99


def agreement(pga: pd.DataFrame, dg: pd.DataFrame, worst_n: int = 5) -> dict:
    shared_events = set(pga['tournament_id']) & set(dg['tournament_id'])
    pga_shared = pga[pga['tournament_id'].isin(shared_events)]
    dg_shared = dg[dg["tournament_id"].isin(shared_events)]
    compared = pga_shared.merge(
        dg_shared,
        on=['tournament_id', 'player_id'],
        how='outer',
        suffixes=('_pga', '_dg'),
        indicator=True
    )
    both = compared[compared['_merge'] == 'both'].copy()
    for column in ["position_pga", "position_dg"]:
        both[column] = (
        both[column]
        .str.replace(r"^T(?=\d+$)", "", regex=True)
        .replace({"W/D": "WD"})
    )

    both["matches"] = both["position_pga"] == both["position_dg"]
    per_event = both.groupby('tournament_id')['matches'].mean().sort_values(kind='stable')
    return {
        "events": len(shared_events),
        "pairs": len(both),
        "match_rate": float(both["matches"].mean()) if len(both) else 0.0,
        "only_pga": int((compared["_merge"] == "left_only").sum()),
        "only_dg": int((compared['_merge'] == 'right_only').sum()),
        "worst": [(tid, float(rate)) for tid, rate in per_event.head(worst_n).items()],
    }

# ── plumbing ──────────────────────────────────────────────────────────────────

def load(pattern: str, first: int, last: int) -> pd.DataFrame:
    frames = []
    for season in range(first, last + 1):
        f = HIST / pattern.format(season=season)
        if f.exists():
            frames.append(pd.read_csv(f, usecols=COLS, dtype=str))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--first", type=int, default=2016)
    ap.add_argument("--last", type=int, default=2026)
    ap.add_argument("--worst", type=int, default=5)
    args = ap.parse_args()

    pga = load("leaderboards_{season}.csv", args.first, args.last)
    dg = load("leaderboards_dg_{season}.csv", args.first, args.last)
    r = agreement(pga, dg, worst_n=args.worst)
    print(f"Shared events: {r['events']}   shared players: {r['pairs']}")
    print(f"Positions agree: {r['match_rate']:.2%}")
    print(f"Listed only by PGA TOUR: {r['only_pga']}   only by DataGolf: {r['only_dg']}")
    print("Worst events:")
    for tid, rate in r["worst"]:
        print(f"  {tid}  {rate:.1%}")
    if TRUST_RATE is not None:
        print("PASS" if r["match_rate"] >= TRUST_RATE else "FAIL", f"(trust threshold {TRUST_RATE:.0%})")


if __name__ == "__main__":
    main()
