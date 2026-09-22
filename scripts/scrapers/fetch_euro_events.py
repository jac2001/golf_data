#!/usr/bin/env python3
"""
DP World Tour events for the Friends Game (picks only, no model)
=================================================================
Three jobs, all from DataGolf:

  --schedule   write data/raw/schedule_euro_{year}.csv (ids E{year}{eventid})
  --field      write data/fields/field_E{...}.csv for the current euro event
  --results    when the current euro event is finished, append final
               positions to data/historical/leaderboards_euro_{year}.csv
               with EARNINGS ESTIMATED from purse x the standard DPWT
               payout distribution (DG carries no euro prize money) —
               flagged via earnings_source=estimated.

The picks game grades by these rows exactly like PGA weeks; the model
never sees euro data (parked until a proper retrain with euro history).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
FIELDS_DIR = PROJECT_ROOT / "data" / "fields"
HIST_DIR = PROJECT_ROOT / "data" / "historical"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dg_client import dg_get  # noqa: E402

# Standard DPWT prize distribution by finish position (fraction of purse).
# Approximate but stable season to season; used ONLY for friends-game
# scoring, always labeled estimated. Ties split the covered positions'
# pool evenly, like real payouts.
PAYOUT_PCT = [
    16.66, 11.11, 6.26, 5.00, 4.24, 3.50, 3.00, 2.58, 2.30, 2.10,
    1.94, 1.80, 1.68, 1.58, 1.50, 1.42, 1.34, 1.27, 1.21, 1.15,
    1.09, 1.05, 1.01, 0.97, 0.93, 0.89, 0.86, 0.83, 0.80, 0.77,
    0.74, 0.71, 0.68, 0.65, 0.62, 0.59, 0.57, 0.55, 0.53, 0.51,
    0.49, 0.47, 0.45, 0.43, 0.41, 0.39, 0.37, 0.35, 0.33, 0.32,
    0.31, 0.30, 0.29, 0.28, 0.27, 0.26, 0.25, 0.24, 0.23, 0.22,
    0.21, 0.20, 0.19, 0.18, 0.17,
]
DEFAULT_PURSE = 3_000_000  # standard DPWT event, flagged as estimate

# Known bigger events (rough, still estimates)
PURSE_OVERRIDES = {
    "bmw pga championship": 9_000_000,
    "dp world tour championship": 10_500_000,
    "abu dhabi championship": 9_000_000,
    "genesis championship": 4_000_000,
    "alfred dunhill links championship": 5_000_000,
}


def eid(year: int, event_id) -> str:
    v = int(event_id)
    # DG euro event ids already embed the season (e.g. 2026136); short ids get it prefixed.
    return f"E{v}" if v >= 10000 else f"E{year}{v:03d}"


def cmd_schedule(year: int) -> None:
    data = dg_get("/get-schedule", {"tour": "euro", "season": str(year),
                                    "upcoming_only": "no", "file_format": "json"})
    sched = data.get("schedule", data) if isinstance(data, dict) else data
    rows = []
    for ev in sched:
        if not str(ev.get("event_id", "")).strip().isdigit():
            continue  # placeholder rows (event_id "TBD") — no field/results anyway
        start = date.fromisoformat(ev["start_date"])
        purse = PURSE_OVERRIDES.get(ev["event_name"].lower(), DEFAULT_PURSE)
        rows.append({
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=3)).isoformat(),
            "tournament_name": ev["event_name"],
            "tour": "euro",
            "location": ev.get("location", ""),
            "course": ev.get("course", ""),
            "purse": purse,
            "purse_source": "estimate",
            "tournament_id": eid(year, ev["event_id"]),
        })
    df = pd.DataFrame(rows).sort_values("start_date").reset_index(drop=True)
    out = RAW_DIR / f"schedule_euro_{year}.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} euro events -> {out.relative_to(PROJECT_ROOT)}")


def _current_event(year: int) -> tuple[str, str, dict]:
    """The euro event DG's field endpoint currently serves."""
    raw = dg_get("/field-updates", {"tour": "euro", "file_format": "json"})
    name = str(raw.get("event_name", ""))
    sched = pd.read_csv(RAW_DIR / f"schedule_euro_{year}.csv")
    row = sched[sched["tournament_name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"Euro event '{name}' not in schedule_euro_{year}.csv — refetch --schedule")
    return str(row.iloc[0]["tournament_id"]), name, raw


def cmd_field(year: int) -> None:
    tid, name, raw = _current_event(year)
    players = [{"player_name": p.get("player_name", ""), "dg_id": p.get("dg_id")}
               for p in raw.get("field", [])]
    df = pd.DataFrame(players)
    out = FIELDS_DIR / f"field_{tid}.csv"
    df.to_csv(out, index=False)
    print(f"{name} ({tid}): {len(df)} players -> {out.relative_to(PROJECT_ROOT)}")


def cmd_preds(year: int) -> None:
    """DataGolf's pre-tournament predictions for the current euro event.

    Our model doesn't cover the DPWT (January retrain) — until it does,
    DG's euro model powers the picks board, clearly labeled as DG's.
    Keyed by the payload's OWN event_name like everything euro: a feed
    that serves "the current event" never gets to pick its label.
    """
    # dead_heat=yes: top-N probabilities adjusted for ties — matches the
    # raw feed Jack reads, so the site and the feed never disagree.
    raw = dg_get("/preds/pre-tournament", {"tour": "euro", "dead_heat": "yes", "file_format": "json"})
    name = str(raw.get("event_name", ""))
    sched = pd.read_csv(RAW_DIR / f"schedule_euro_{year}.csv")
    row = sched[sched["tournament_name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"preds event '{name}' not in schedule_euro_{year}.csv — refusing to write")
    tid = str(row.iloc[0]["tournament_id"])

    players = raw.get("baseline_history_fit") or raw.get("baseline") or []
    df = pd.DataFrame([{
        "tournament_id": tid,
        "player_name": p.get("player_name", ""),
        "dg_id": p.get("dg_id"),
        "win_prob": p.get("win"),
        "top5_prob": p.get("top_5"),
        "top10_prob": p.get("top_10"),
        "top20_prob": p.get("top_20"),
        "cut_prob": p.get("make_cut"),
    } for p in players if p.get("player_name")])
    if df.empty:
        raise SystemExit(f"DG served no euro predictions for '{name}'")
    df = df.sort_values("win_prob", ascending=False)

    dg_dir = PROJECT_ROOT / "data" / "datagolf"
    dg_dir.mkdir(parents=True, exist_ok=True)
    out = dg_dir / f"dg_preds_{tid}.csv"
    df.to_csv(out, index=False)
    print(f"{name} ({tid}): DG euro predictions for {len(df)} players -> {out.relative_to(PROJECT_ROOT)}")


def _event_from_inplay(year: int, live: dict) -> tuple[str, str]:
    """Resolve (tid, name) from the in-play payload's OWN event label.

    The field feed flips to next week's event the moment one ends, while
    in-play still holds the finished event — trusting the field feed once
    settled BMW PGA's results under the Open de France id. Data must be
    keyed by what the data says it is, not by what another feed is
    currently pointing at.
    """
    name = str((live.get("info") or {}).get("event_name", ""))
    if not name:
        raise SystemExit("in-play payload carries no event_name — refusing to guess")
    sched = pd.read_csv(RAW_DIR / f"schedule_euro_{year}.csv")
    row = sched[sched["tournament_name"].str.lower() == name.lower()]
    if row.empty:
        raise SystemExit(f"in-play event '{name}' not in schedule_euro_{year}.csv")
    return str(row.iloc[0]["tournament_id"]), name


def cmd_results(year: int, force: bool = False) -> None:
    live = dg_get("/preds/in-play", {"tour": "euro", "file_format": "json"})
    tid, name = _event_from_inplay(year, live)
    data = live.get("data", live) if isinstance(live, dict) else live
    df = pd.DataFrame(data)
    if df.empty:
        raise SystemExit("No in-play data for euro event")

    # Finished = every player has an R4 (or is cut/wd). Rough but works
    # once the event is over; --force settles whatever is there.
    finished = df["R4"].notna() | df["current_pos"].astype(str).str.upper().isin(["CUT", "WD", "DQ"])
    if not finished.all() and not force:
        raise SystemExit(f"{name} not finished ({int((~finished).sum())} players mid-round) — rerun after Sunday or --force")

    sched = pd.read_csv(RAW_DIR / f"schedule_euro_{year}.csv")
    purse = float(sched.loc[sched["tournament_id"] == tid, "purse"].iloc[0])

    def pos_num(p) -> int | None:
        s = str(p).strip().upper()
        if s in {"CUT", "WD", "DQ", "DNS", "NAN", ""}:
            return None
        return int(float(s.replace("T", "")))

    df["_pos"] = df["current_pos"].map(pos_num)

    # Dead-heat payouts: everyone tied at position p splits the pool of
    # positions [p, p+ties-1], exactly like the real prize table.
    counts = df["_pos"].value_counts()
    def earnings(p) -> float:
        # _pos is a float64 column (NaN forces the dtype): NaN fails the
        # None check and floats break range() — normalize first.
        if p is None or p != p or p > len(PAYOUT_PCT):
            return 0.0
        p = int(p)
        n = int(counts.get(p, 1))
        slots = [PAYOUT_PCT[i - 1] for i in range(p, min(p + n, len(PAYOUT_PCT) + 1))]
        return round(purse * (sum(slots) / 100.0) / n, 2)

    rows = pd.DataFrame({
        "tournament_id": tid,
        "year": year,
        "player_name": df["player_name"],
        "position": df["current_pos"].astype(str),
        "earnings": df["_pos"].map(earnings),
        "earnings_source": "estimated",
        "tournament_name": name,
    })

    out = HIST_DIR / f"leaderboards_euro_{year}.csv"
    if out.exists():
        old = pd.read_csv(out)
        old = old[old["tournament_id"] != tid]  # settle is idempotent
        rows = pd.concat([old, rows], ignore_index=True)
    rows.to_csv(out, index=False)
    print(f"Settled {name} ({tid}) -> {out.relative_to(PROJECT_ROOT)} "
          f"(winner ~${rows[rows['tournament_id']==tid]['earnings'].max():,.0f} of ${purse:,.0f} est. purse)")


def cmd_rounds(year: int) -> None:
    """Mid-event snapshot of per-round scores -> data/live/rounds_{tid}.csv.
    Powers the Round Game's grading for euro events; run daily while a
    euro event is live (results settle still uses --results on Monday)."""
    live = dg_get("/preds/in-play", {"tour": "euro", "file_format": "json"})
    tid, name = _event_from_inplay(year, live)
    data = live.get("data", live) if isinstance(live, dict) else live
    df = pd.DataFrame(data)
    if df.empty:
        raise SystemExit("No in-play data for euro event")
    keep = [c for c in ["player_name", "current_pos", "current_score", "R1", "R2", "R3", "R4", "thru", "today"] if c in df.columns]
    out = PROJECT_ROOT / "data" / "live" / f"rounds_{tid}.csv"
    df[keep].to_csv(out, index=False)
    print(f"{name} ({tid}): rounds snapshot -> {out.relative_to(PROJECT_ROOT)} ({len(df)} players)")


def main() -> None:
    ap = argparse.ArgumentParser(description="DPWT events for the Friends Game")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--schedule", action="store_true")
    ap.add_argument("--field", action="store_true")
    ap.add_argument("--results", action="store_true")
    ap.add_argument("--rounds", action="store_true", help="mid-event round-score snapshot")
    ap.add_argument("--preds", action="store_true", help="DataGolf pre-tournament predictions for the current euro event")
    ap.add_argument("--force", action="store_true", help="settle even if mid-event")
    args = ap.parse_args()
    if args.schedule:
        cmd_schedule(args.year)
    if args.field:
        cmd_field(args.year)
    if args.results:
        cmd_results(args.year, force=args.force)
    if args.rounds:
        cmd_rounds(args.year)
    if args.preds:
        cmd_preds(args.year)
    if not (args.schedule or args.field or args.results or args.rounds or args.preds):
        ap.error("pick at least one of --schedule --field --results --rounds --preds")


if __name__ == "__main__":
    main()
