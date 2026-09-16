#!/usr/bin/env python3
"""
Miss Analysis — where the 2026 picks leaked value
=================================================
Per league week: Jack's actual lineup vs the rolling-replay suggestion
(what strategy mode would have said THAT Tuesday, no lookahead) vs the
hindsight-best trio. The output is the data behind the Tuesday
decision-support view's "reasonable alternatives" panel — and the honest
scoreboard of where human beat machine and vice versa.

Output:
  outputs/strategy_miss_analysis_2026.csv  (one row per week)
  console summary

Usage:
    python3 scripts/strategy/miss_analysis.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "strategy"))

from season_optimizer import (  # noqa: E402
    build_ev_grid, rolling_replay, load_model_weeks,
)

TRACKER = PROJECT_ROOT / "data" / "fantasy" / "usage_tracker_2026.json"
OUT_CSV = PROJECT_ROOT / "outputs" / "strategy_miss_analysis_2026.csv"


def _last_name(pick: str) -> str:
    """Tracker pick label -> lowercase last name. Handles 'Gotterup',
    'B Griffin', 'MW Lee', 'Fitzpatrick, M', 'Cam Young', 'Tom Kim'."""
    s = str(pick).strip()
    if "," in s:                                   # 'Fitzpatrick, M'
        return s.split(",")[0].strip().lower()
    parts = s.split()
    return parts[-1].lower() if parts else s.lower()


def match_picks_to_field(picks: list[str], field: pd.DataFrame) -> dict:
    """Map tracker pick labels to (player_id, earn) via last-name match
    against that week's actual field. Returns {label: (pid|None, earn)}."""
    fld = field.copy()
    fld["last"] = fld["player_name"].str.split(",").str[0].str.strip().str.lower()
    out = {}
    for label in picks:
        ln = _last_name(label)
        hit = fld[fld["last"] == ln]
        if len(hit) > 1:                           # disambiguate by initial
            init = re.sub(r"[^A-Za-z]", "", str(label).replace(ln, ""))[:1].lower()
            if init:
                first = hit["player_name"].str.split(",").str[1].fillna("").str.strip().str.lower()
                narrowed = hit[first.str.startswith(init)]
                if len(narrowed):
                    hit = narrowed
        if len(hit) >= 1:
            r = hit.iloc[0]
            out[label] = (r["player_id"], float(r["earn"]))
        else:
            out[label] = (None, 0.0)
    return out


def main():
    with open(TRACKER) as f:
        tracker = json.load(f)
    lineups = {v["tournament"]: v for v in tracker["weekly_lineups"].values()
               if v.get("lineup")}

    global TID_TO_NAME
    sched = pd.read_csv(PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv")
    TID_TO_NAME = dict(zip(sched["tournament_id"].str.upper(), sched["tournament_name"]))

    grid, actual = build_ev_grid()
    replay = rolling_replay(grid, actual)
    weeks = load_model_weeks()

    id_name = actual.drop_duplicates("player_id").set_index("player_id")["player_name"].to_dict()

    rows = []
    for wk in weeks:
        field = actual[actual["event"] == wk["event"]]
        if field.empty:
            continue

        # Jack's picks: tid -> schedule tournament name -> tracker entry by
        # word overlap. Each tracker entry is consumed once (del after match).
        sched_name = TID_TO_NAME.get(wk["tid"], "")
        sched_words = set(re.findall(r"\w{4,}", sched_name.lower()))
        tr_key = next((name for name in lineups
                       if sched_words & set(re.findall(r"\w{4,}", name.lower()))), None)
        jack_names, jack_total, tr = [], None, None
        if tr_key is not None:
            tr = lineups.pop(tr_key)
        matched = {}
        if tr:
            matched = match_picks_to_field(tr["lineup"], field)
            jack_names = tr["lineup"]
            jack_total = tr.get("earnings_earned")
        jack_sum = sum(e for _, e in matched.values())

        rp = replay[replay["event"] == wk["event"]]
        rp_ids = rp["player_id"].tolist()
        rp_earn = field[field["player_id"].isin(rp_ids)].set_index("player_id")["earn"]
        rp_sum = float(rp_earn.sum())

        best3 = field.nlargest(3, "earn")
        rows.append({
            "event": wk["event"], "tid": wk["tid"], "date": wk["date"],
            "jack_picks": " | ".join(jack_names),
            "jack_earn": jack_total if jack_total is not None else jack_sum,
            "replay_picks": " | ".join(id_name.get(p, p) for p in rp_ids),
            "replay_earn": rp_sum,
            "best3_picks": " | ".join(best3["player_name"]),
            "best3_earn": float(best3["earn"].sum()),
        })

    df = pd.DataFrame(rows)
    df["delta_vs_replay"] = df["jack_earn"] - df["replay_earn"]
    df["capture_pct"] = (df["jack_earn"] / df["best3_earn"] * 100).round(1)
    df.to_csv(OUT_CSV, index=False)

    jack_wins = (df["delta_vs_replay"] > 0).sum()
    print(f"\n{'='*70}")
    print(f"  MISS ANALYSIS — {len(df)} weeks  (saved -> {OUT_CSV.name})")
    print(f"{'='*70}")
    print(f"  Jack beat the replay in {jack_wins}/{len(df)} weeks "
          f"(totals: ${df['jack_earn'].sum():,.0f} vs ${df['replay_earn'].sum():,.0f})")
    print(f"  Avg weekly capture of hindsight-best trio: {df['capture_pct'].mean():.0f}%")

    print("\n  Five biggest MISSES (replay >> Jack):")
    for _, r in df.nsmallest(5, "delta_vs_replay").iterrows():
        print(f"    {r['tid']}: you ${r['jack_earn']:>9,.0f} [{r['jack_picks']}]")
        print(f"    {'':>10} replay ${r['replay_earn']:>7,.0f} [{r['replay_picks']}]")

    print("\n  Five biggest EDGES (Jack >> replay):")
    for _, r in df.nlargest(5, "delta_vs_replay").iterrows():
        print(f"    {r['tid']}: you ${r['jack_earn']:>9,.0f} [{r['jack_picks']}]  "
              f"replay ${r['replay_earn']:,.0f}")


if __name__ == "__main__":
    main()
