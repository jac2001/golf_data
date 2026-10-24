#!/usr/bin/env python3
"""
Backfill official prize money into leaderboards_{year}.csv
==========================================================
Official money posts on PGA TOUR's past-results page, often a day after the
final round. Until Oct 24, 2026 the post-tournament append replaced each
event's rows from the live leaderboard (no money) right after the
past-results fetch wrote them, so every event settled that way kept $0 and
the site graded every week from the purse-split estimate.

For each PGA event in the season file with no money (or one --tournament-id),
fetch the past-results page and fill ONLY the earnings (and empty FedEx
points) of rows already there, matched by player_id. Positions and scores
are never touched.

Provenance (CLAUDE.md rule 1): the page must name the same tournament id,
its winner must be our leaderboard's winner, at least 90% of our players
must appear on it, and 99% of its money must land on our rows. Anything else is skipped and logged, never
merged under this event.

Usage:
    python scripts/scrapers/backfill_official_money.py --year 2026
    python scripts/scrapers/backfill_official_money.py --tournament-id R2026557
    python scripts/scrapers/backfill_official_money.py --year 2026 --dry-run
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fetch_past_results import HIST_DIR, fetch_past_results_page, parse_past_results, _tournament_slug  # noqa: E402

MIN_OVERLAP = 0.90
MIN_MONEY_MATCHED = 0.99


def _money(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _pid(v) -> str:
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def missing_money_events(lb: pd.DataFrame) -> list[str]:
    money = lb["earnings"].map(_money).groupby(lb["tournament_id"].str.upper()).sum()
    return sorted(t for t, m in money.items() if m <= 0 and t.startswith("R"))


def official_money(tid: str, ours: pd.DataFrame) -> dict[str, tuple[str, str]] | None:
    """player_id -> (earnings, fedex_points) from the page, or None if it fails provenance."""
    year = int(tid[1:5])
    raw = fetch_past_results_page(tid, year, _tournament_slug(tid))
    if raw is None:
        return None
    if str(raw.get("id", "")).upper() != tid:
        print(f"  SKIP {tid}: page is for {raw.get('id')!r}")
        return None
    rows = parse_past_results(raw, tid, year)
    page = {r["player_id"]: r for r in rows}
    page_winners = {r["player_id"] for r in rows if str(r["position"]).strip() == "1"}
    our_winners = {_pid(p) for p, pos in zip(ours["player_id"], ours["position"]) if str(pos).strip() == "1"}
    if not our_winners or page_winners != our_winners:
        print(f"  SKIP {tid}: page winner(s) {sorted(page_winners)} != ours {sorted(our_winners)}")
        return None
    our_ids = {_pid(p) for p in ours["player_id"]}
    overlap = len(our_ids & set(page)) / max(len(our_ids), 1)
    if overlap < MIN_OVERLAP:
        print(f"  SKIP {tid}: only {overlap:.0%} of our players are on the page")
        return None
    page_total = sum(_money(r["earnings"]) for r in rows)
    if page_total <= 0:
        print(f"  {tid}: official money not posted yet")
        return None
    # Money paid to a golfer we can't match would silently vanish from a lineup.
    matched = sum(_money(page[p]["earnings"]) for p in our_ids if p in page)
    if matched < MIN_MONEY_MATCHED * page_total:
        print(f"  SKIP {tid}: only ${matched:,.0f} of ${page_total:,.0f} official money matches our players")
        return None
    return {pid: (r["earnings"] or "", "" if r["fedex_points"] is None else str(r["fedex_points"]))
            for pid, r in page.items()}


def backfill(year: int, only: str | None, dry_run: bool) -> int:
    path = HIST_DIR / f"leaderboards_{year}.csv"
    if not path.exists():
        print(f"{path.name} not found")
        return 0
    lb = pd.read_csv(path, dtype=str, keep_default_na=False)
    tids = [only] if only else missing_money_events(lb)
    print(f"{len(tids)} event(s) to check: {', '.join(tids) or '-'}")
    filled = 0
    for i, tid in enumerate(tids):
        if i:
            time.sleep(1.5)
        mask = lb["tournament_id"].str.upper() == tid
        if not mask.any():
            print(f"  SKIP {tid}: not in {path.name}")
            continue
        money = official_money(tid, lb[mask])
        if not money:
            continue
        n = 0
        for idx in lb.index[mask]:
            hit = money.get(_pid(lb.at[idx, "player_id"]))
            if not hit:
                continue
            lb.at[idx, "earnings"] = hit[0]
            if not str(lb.at[idx, "fedex_points"]).strip() or str(lb.at[idx, "fedex_points"]) == "nan":
                lb.at[idx, "fedex_points"] = hit[1]
            n += 1
        total = lb.loc[mask, "earnings"].map(_money).sum()
        print(f"  {tid}: official money for {n}/{int(mask.sum())} players, ${total:,.0f} total")
        filled += 1
    if filled and not dry_run:
        tmp = path.with_suffix(".csv.tmp")
        lb.to_csv(tmp, index=False)
        tmp.replace(path)
        print(f"Wrote {path.name}")
    elif dry_run:
        print("[DRY RUN] nothing written")
    return filled


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--tournament-id", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tid = args.tournament_id.strip().upper() if args.tournament_id else None
    if tid and not re.fullmatch(r"R\d{7}", tid):
        sys.exit("--tournament-id must look like R2026557")
    year = int(tid[1:5]) if tid else (args.year or pd.Timestamp.now().year)
    backfill(year, tid, args.dry_run)


if __name__ == "__main__":
    main()
