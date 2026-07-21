#!/usr/bin/env python3
"""
Fetch historical tournament results + SG stats directly from DataGolf —
a more reliable replacement for PGA Tour web scraping, now that the
account has access to /historical-raw-data (requires the higher DG tier;
the standard tier returns 403 on this endpoint).

DG's event_id maps directly onto our tournament_id scheme:
    tournament_id = f"R{year}{event_id:03d}"
Confirmed empirically across every 2026 PGA event — DG event_id 26 is
"R2026026" (U.S. Open), 23 is "R2026023" (Memorial), etc.

Player identity problem
------------------------
DG identifies players by dg_id (e.g. 23604 for Wyndham Clark), but our
leaderboards/tournament_stats tables use PGA Tour's own numeric player_id
(e.g. 51766 for the same player) — two completely different ID spaces with
no DG-provided crosswalk. This script builds one by matching player names
against everyone already in our `leaderboards` table (sorted-token
normalization — the same pattern used everywhere else in this codebase,
e.g. _name_key() in season_strategy.py). Verified 152/155 matches on the
2026 U.S. Open field; the handful of misses were players with zero prior
PGA Tour record in our data (e.g. U.S. Open open-qualifiers), which is
exactly what you'd expect, not a matching failure. Players with no match
get a "DG{dg_id}" string ID — guaranteed not to collide with the numeric
PGA ID space, since that column is VARCHAR, not numeric.

What this can't give us (compared to the PGA Tour scrape)
------------------------------------------------------------
No `earnings` or `fedex_points` — DataGolf doesn't track prize money.
Those columns stay NULL for DG-sourced rows. Everything else (position,
round-by-round scores, to-par, all 5 SG categories) is fully populated
and richer than what we got from scraping.

Usage:
    # One event
    python3 scripts/scrapers/fetch_dg_historical_results.py --year 2026 --event-id 26

    # Every PGA event for a year
    python3 scripts/scrapers/fetch_dg_historical_results.py --year 2026

    # Preview without writing to the database
    python3 scripts/scrapers/fetch_dg_historical_results.py --year 2026 --event-id 26 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "database"))
sys.path.insert(0, str(ROOT / "scripts" / "scrapers"))

from db import get_conn  # noqa: E402
from dg_client import dg_get  # noqa: E402

# DG stat key -> our existing stat_id convention (matches tournament_stats.stat_id
# used throughout the codebase, e.g. api/main.py's career endpoint pivot queries).
#
# "2570" is a NEW id for sg_arg (around-the-green) — there's never been a
# dedicated slot for it; T2G was always just OTT+APP+ARG summed together
# with ARG never broken out on its own. DG gives it to us directly now.
#
# driving_dist/driving_acc/gir/scrambling reuse the SAME stat_ids already
# used elsewhere in this codebase (predict_tournament.py's NON_SG_STATS,
# and confirmed against real stored values in form_stats) — 101/102/103/130.
# driving_acc/gir/scrambling come from DG as 0-1 fractions; the existing
# convention stores them as 0-100 percentages, so those three get *100.
#
# 2571-2579 are brand new — DG's per-round scoring distribution (birdies,
# bogies, doubles_or_worse, eagles_or_better, pars) and shot-quality/
# proximity metrics (great_shots, poor_shots, prox_fw, prox_rgh) that this
# codebase never had a slot for at all. Confirmed unused before picking
# this range — see tournament_stats audit earlier in this session.
STAT_ID_MAP = {
    "sg_total":          "2567",
    "sg_ott":             "2568",
    "sg_app":             "2569",
    "sg_putt":            "2564",
    "sg_t2g":             "2674",
    "sg_arg":             "2570",
    "driving_dist":       "101",
    "driving_acc":        "102",
    "gir":                "103",
    "scrambling":         "130",
    "birdies":            "2571",
    "bogies":             "2572",
    "doubles_or_worse":   "2573",
    "eagles_or_better":   "2574",
    "pars":               "2575",
    "great_shots":        "2576",
    "poor_shots":         "2577",
    "prox_fw":            "2578",
    "prox_rgh":           "2579",
}
STAT_NAME_MAP = {
    "2567": "Strokes Gained: Total",
    "2568": "Strokes Gained: Off-the-Tee",
    "2569": "Strokes Gained: Approach",
    "2564": "Strokes Gained: Putting",
    "2674": "Strokes Gained: Tee-to-Green",
    "2570": "Strokes Gained: Around-the-Green",
    "101":  "Driving Distance",
    "102":  "Driving Accuracy",
    "103":  "GIR Percentage",
    "130":  "Scrambling",
    "2571": "Birdies Per Round",
    "2572": "Bogies Per Round",
    "2573": "Doubles-or-Worse Per Round",
    "2574": "Eagles-or-Better Per Round",
    "2575": "Pars Per Round",
    "2576": "Great Shots Per Round",
    "2577": "Poor Shots Per Round",
    "2578": "Proximity to Hole - Fairway (ft)",
    "2579": "Proximity to Hole - Rough (ft)",
}
# These 3 are stored as 0-100 percentages elsewhere in the codebase; DG gives
# them as 0-1 fractions. Everything else (counts, proximity in feet) is
# stored as-is — no conversion needed.
_PCT_STATS = {"driving_acc", "gir", "scrambling"}


def name_key(name: str) -> str:
    """Sorted-token normalization so 'Last, First' and 'First Last' collapse
    to the same comparable key — same approach used elsewhere in this codebase."""
    s = str(name).strip()
    if "," in s:
        last, first = s.split(",", 1)
        s = f"{first.strip()} {last.strip()}"
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(sorted(s.lower().split()))


def build_player_crosswalk(conn) -> dict[str, str]:
    """name_key -> existing player_id, built from every player ever recorded.
    Keeps DG-sourced rows on the SAME player_id as their PGA-Tour-sourced
    history instead of fracturing it under a new identity."""
    df = conn.execute("SELECT DISTINCT player_id, player_name FROM leaderboards").df()
    crosswalk: dict[str, str] = {}
    for _, row in df.iterrows():
        crosswalk[name_key(row["player_name"])] = row["player_id"]
    return crosswalk


def resolve_player_id(dg_name: str, dg_id: int, crosswalk: dict[str, str]) -> str:
    """Existing player_id if this player has prior history; otherwise a
    DG-prefixed synthetic ID that can't collide with the numeric PGA space."""
    return crosswalk.get(name_key(dg_name)) or f"DG{dg_id}"


def parse_event(raw: dict, tid: str, year: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Convert one DG historical-rounds payload into leaderboard rows,
    long-format averaged SG stat rows, and per-round stat rows."""
    event_name = raw.get("event_name", "")
    leaderboard_rows, stat_rows, round_rows = [], [], []

    for player in raw.get("scores", []):
        dg_id = player["dg_id"]
        player_name = player["player_name"]

        rounds = [player.get(f"round_{i}") for i in range(1, 5)]
        played = [r for r in rounds if r]
        if not played:
            continue

        round_scores = [r.get("score") if r else None for r in rounds]
        total_score = sum(s for s in round_scores if s is not None) or None
        total_par = sum(r["course_par"] for r in played if r.get("course_par") is not None)
        to_par = (total_score - total_par) if (total_score is not None and total_par) else None

        leaderboard_rows.append({
            "tournament_id":   tid,
            "tournament_name": event_name,
            "year":            year,
            "player_id":       None,  # filled in once the crosswalk is resolved
            "player_name":     player_name,
            "position":        player.get("fin_text", ""),
            "total_score":     total_score,
            "to_par":          f"{to_par:+d}" if to_par is not None else None,
            "earnings":        None,   # not provided by DataGolf
            "rounds_played":   len(played),
            "fedex_points":    None,   # not provided by DataGolf
            "r1": round_scores[0],
            "r2": round_scores[1],
            "r3": round_scores[2],
            "r4": round_scores[3],
            "_dg_id": dg_id,
        })

        for dg_key, stat_id in STAT_ID_MAP.items():
            vals = [r[dg_key] for r in played if r.get(dg_key) is not None]
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            if dg_key in _PCT_STATS:
                avg *= 100  # DG gives 0-1 fractions; our convention stores 0-100
            stat_rows.append({
                "player_id":       None,
                "player_name":     player_name,
                "tournament_id":   tid,
                "tournament_name": event_name,
                "year":            year,
                "stat_id":         stat_id,
                "stat_name":       STAT_NAME_MAP[stat_id],
                "stat_component":  "Avg",
                "stat_value":      avg,
                "_dg_id":          dg_id,
            })

        # Per-round rows — one per round played
        for rnum, r in enumerate(rounds, start=1):
            if not r:
                continue
            def _pct(v):
                return round(v * 100, 2) if v is not None else None
            round_rows.append({
                "player_id":       None,
                "player_name":     player_name,
                "tournament_id":   tid,
                "tournament_name": event_name,
                "year":            year,
                "round_num":       rnum,
                "score":           r.get("score"),
                "course_par":      r.get("course_par"),
                "sg_total":        r.get("sg_total"),
                "sg_ott":          r.get("sg_ott"),
                "sg_app":          r.get("sg_app"),
                "sg_arg":          r.get("sg_arg"),
                "sg_putt":         r.get("sg_putt"),
                "sg_t2g":          r.get("sg_t2g"),
                "driving_dist":    r.get("driving_dist"),
                "driving_acc":     _pct(r.get("driving_acc")),
                "gir":             _pct(r.get("gir")),
                "scrambling":      _pct(r.get("scrambling")),
                "birdies":         r.get("birdies"),
                "bogies":          r.get("bogies"),
                "pars":            r.get("pars"),
                "eagles_or_better": r.get("eagles_or_better"),
                "doubles_or_worse": r.get("doubles_or_worse"),
                "great_shots":     r.get("great_shots"),
                "poor_shots":      r.get("poor_shots"),
                "prox_fw":         r.get("prox_fw"),
                "prox_rgh":        r.get("prox_rgh"),
                "_dg_id":          dg_id,
            })

    return leaderboard_rows, stat_rows, round_rows


def fetch_one_event(tour: str, event_id: int, year: int) -> dict | None:
    """Returns None (instead of raising) when DG has nothing for this event yet —
    e.g. it hasn't been played, or DG hasn't finished ingesting it. Callers treat
    that the same as "no data" and can fall back to another source."""
    try:
        raw = dg_get("/historical-raw-data/rounds", {
            "tour": tour, "event_id": str(event_id), "year": str(year), "file_format": "json",
        })
    except Exception as e:
        print(f"  DataGolf has no data for this event yet ({e})")
        return None
    if not raw or not raw.get("scores"):
        return None
    return raw


def list_events_for_year(tour: str, year: int) -> list[int]:
    events = dg_get("/historical-raw-data/event-list", {"file_format": "json"})
    return sorted(
        e["event_id"] for e in events
        if e.get("calendar_year") == year and e.get("tour") == tour
    )


def upsert(conn, leaderboard_rows: list[dict], stat_rows: list[dict], round_rows: list[dict], rounds_only: bool = False) -> None:
    if rounds_only:
        leaderboard_rows = []
        stat_rows = []
    for row in leaderboard_rows:
        # ON CONFLICT DO UPDATE (not INSERT OR REPLACE) — DataGolf doesn't provide
        # earnings or fedex_points, so a blind REPLACE would null out prize-money
        # data we already had from the PGA Tour scrape. COALESCE keeps whatever
        # was already there for those two columns; everything else (position,
        # scores, to_par) always takes the fresh DG value, since that's the
        # whole point of this script.
        conn.execute("""
            INSERT INTO leaderboards
                (tournament_id, tournament_name, year, player_id, player_name,
                 position, total_score, to_par, earnings, rounds_played,
                 fedex_points, r1, r2, r3, r4)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (player_id, tournament_id) DO UPDATE SET
                tournament_name = excluded.tournament_name,
                year            = excluded.year,
                player_name     = excluded.player_name,
                position        = excluded.position,
                total_score     = excluded.total_score,
                to_par          = excluded.to_par,
                earnings        = COALESCE(excluded.earnings, leaderboards.earnings),
                rounds_played   = excluded.rounds_played,
                fedex_points    = COALESCE(excluded.fedex_points, leaderboards.fedex_points),
                r1 = excluded.r1, r2 = excluded.r2, r3 = excluded.r3, r4 = excluded.r4
        """, [
            row["tournament_id"], row["tournament_name"], row["year"],
            row["player_id"], row["player_name"], row["position"],
            row["total_score"], row["to_par"], row["earnings"],
            row["rounds_played"], row["fedex_points"],
            row["r1"], row["r2"], row["r3"], row["r4"],
        ])
    for row in stat_rows:
        conn.execute("""
            INSERT OR REPLACE INTO tournament_stats
                (player_id, player_name, tournament_id, tournament_name, year,
                 stat_id, stat_name, stat_component, stat_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            row["player_id"], row["player_name"], row["tournament_id"],
            row["tournament_name"], row["year"], row["stat_id"],
            row["stat_name"], row["stat_component"], row["stat_value"],
        ])
    for row in round_rows:
        conn.execute("""
            INSERT OR REPLACE INTO round_stats
                (player_id, player_name, tournament_id, tournament_name, year, round_num,
                 score, course_par, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
                 driving_dist, driving_acc, gir, scrambling,
                 birdies, bogies, pars, eagles_or_better, doubles_or_worse,
                 great_shots, poor_shots, prox_fw, prox_rgh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            row["player_id"], row["player_name"], row["tournament_id"],
            row["tournament_name"], row["year"], row["round_num"],
            row["score"], row["course_par"],
            row["sg_total"], row["sg_ott"], row["sg_app"], row["sg_arg"], row["sg_putt"], row["sg_t2g"],
            row["driving_dist"], row["driving_acc"], row["gir"], row["scrambling"],
            row["birdies"], row["bogies"], row["pars"], row["eagles_or_better"], row["doubles_or_worse"],
            row["great_shots"], row["poor_shots"], row["prox_fw"], row["prox_rgh"],
        ])


def run_year(
    year: int, tour: str, event_id: int | None,
    crosswalk: dict[str, str], conn, dry_run: bool,
    new_players: set[str], rounds_only: bool = False,
) -> tuple[int, int, int]:
    """Fetch + write every event (or one event) for a single year.
    Returns (leaderboard_rows, stat_rows, round_rows) written."""
    event_ids = [event_id] if event_id else list_events_for_year(tour, year)
    print(f"\n=== {year}: {len(event_ids)} event(s) ===")

    total_lb = total_stats = total_rounds = 0
    for eid in event_ids:
        tid = f"R{year}{eid:03d}"
        print(f"\n{tid} (DG event_id={eid})...")
        raw = fetch_one_event(tour, eid, year)
        if raw is None:
            print("  No data returned — skipping")
            continue

        lb_rows, stat_rows, round_rows = parse_event(raw, tid, year)

        matched = 0
        for row in lb_rows + stat_rows + round_rows:
            pid = resolve_player_id(row["player_name"], row["_dg_id"], crosswalk)
            row["player_id"] = pid
            if pid.startswith("DG"):
                new_players.add(row["player_name"])
            else:
                matched += 1
            del row["_dg_id"]

        print(f"  {raw.get('event_name')}: {len(lb_rows)} players, {matched} matched, {len(round_rows)} round rows")

        if not dry_run:
            upsert(conn, lb_rows, stat_rows, round_rows, rounds_only=rounds_only)

        total_lb += len(lb_rows)
        total_stats += len(stat_rows)
        total_rounds += len(round_rows)

    return total_lb, total_stats, total_rounds


def main():
    parser = argparse.ArgumentParser(description="Fetch historical results + SG stats from DataGolf")
    parser.add_argument("--year", type=int, default=None, help="Single year")
    parser.add_argument("--start-year", type=int, default=None, help="First year of a range (inclusive)")
    parser.add_argument("--end-year", type=int, default=None, help="Last year of a range (inclusive)")
    parser.add_argument("--event-id", type=int, default=None,
                         help="Single DG event_id; omit to fetch every event for the year (only valid with --year)")
    parser.add_argument("--tour", default="pga")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rounds-only", action="store_true",
                        help="Skip leaderboard + tournament_stats upserts; only populate round_stats (faster for backfill)")
    args = parser.parse_args()

    if args.year is not None:
        years = [args.year]
    elif args.start_year is not None and args.end_year is not None:
        if args.event_id is not None:
            parser.error("--event-id can only be used with --year, not a year range")
        years = list(range(args.start_year, args.end_year + 1))
    else:
        parser.error("Provide either --year, or both --start-year and --end-year")

    conn = get_conn(read_only=False)
    crosswalk = build_player_crosswalk(conn)
    print(f"Player crosswalk: {len(crosswalk)} known players")

    total_lb = total_stats = total_rounds = 0
    new_players: set[str] = set()

    for year in years:
        lb, st, rnd = run_year(year, args.tour, args.event_id, crosswalk, conn, args.dry_run, new_players, rounds_only=args.rounds_only)
        total_lb += lb
        total_stats += st
        total_rounds += rnd

    conn.close()
    print(f"\nDone — {total_lb} leaderboard rows, {total_stats} stat rows, {total_rounds} round rows across {len(years)} year(s).")
    if new_players:
        preview = sorted(new_players)[:10]
        print(f"  {len(new_players)} players with no prior history (DG-prefixed IDs): "
              f"{preview}{'...' if len(new_players) > 10 else ''}")

    # Nonzero exit when nothing was found — lets callers (e.g. post_tournament.py)
    # detect "DG has no data for this yet" and fall back to another source.
    if total_lb == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
