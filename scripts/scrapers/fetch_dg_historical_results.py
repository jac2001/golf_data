#!/usr/bin/env python3
"""
Fetch historical tournament results + SG stats directly from DataGolf —
a more reliable replacement for PGA Tour web scraping, now that the
account has access to /historical-raw-data (requires the higher DG tier;
the standard tier returns 403 on this endpoint).

DG's event_id maps onto our tournament_id as R{season}{event_id:03d}, where
the SEASON comes from the event's date (event_dates.season_for), not DG's
calendar year: before 2024 a season began the previous fall, so DG's
2020-11-15 Masters is our R2021014. Every event is checked against what we
already have (name, date, winner) before it's written: check_event().

Writes data/historical/leaderboards_dg_{season}.csv (works on GitHub
Actions), and DuckDB too when the local database exists.

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

from dg_client import dg_get  # noqa: E402
from event_guard import names_match  # noqa: E402

sys.path.insert(0, str(ROOT))
from scripts.features.event_dates import load_events, load_overrides, season_for, training_event_date  # noqa: E402

import pandas as pd  # noqa: E402

HIST = ROOT / "data" / "historical"
DB_PATH = ROOT / "data" / "golf_data.db"
# Same layout as leaderboards_{season}.csv (the PGA TOUR-sourced files) plus
# dg_id. A separate file on purpose: the model reads leaderboards_20*.csv and
# was trained on what those hold; it moves to these at the January retrain
# (stats-reviewer). The why lines (golfer_form) read both now.
DG_CSV = "leaderboards_dg_{season}.csv"
CSV_COLS = ["tournament_id", "year", "player_id", "player_name", "position", "total_score", "to_par",
            "fedex_points", "earnings", "rounds_played", "r1_score", "r2_score", "r3_score", "r4_score",
            "r1_to_par", "r2_to_par", "r3_to_par", "r4_to_par", "tournament_name", "dg_id"]
MAX_DATE_GAP_DAYS = 10

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


# Letters NFD can't take apart ("Thorbjørn", "Søren").
_FOLD = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "ł": "l", "Ł": "L"})
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

# DataGolf id -> our PGA TOUR player_id for players the two sources spell
# differently. Each checked by hand against our files (Oct 20). Ambiguous
# names (two Richard Lees, two Richard Johnsons) stay unmatched on purpose:
# a wrong match puts one golfer's record on another's why line.
DG_ALIASES = {
    17646: "40098",   # Matthew Fitzpatrick = Matt Fitzpatrick
    17786: "45157",   # Cameron Davis = Cam Davis
    13497: "32791",   # Kyoung-Hoon Lee = K.H. Lee
    11117: "29289",   # Seung-Yul Noh = S.Y. Noh
    25908: "51894",   # Vincent Whaley = Vince Whaley
    24766: "55182",   # Joohyung Kim = Tom Kim
    8262:  "25191",   # Gonzalo Fdez-Castano = Gonzalo Fernandez-Castaño
    14696: "34265",   # Willy Wilcox = Will Wilcox
    12530: "31273",   # Gavin Kyle Green = Gavin Green
    9675:  "29772",   # Michael Lorenzo-Vera = Mike Lorenzo-Vera
    15310: "35296",   # Hao Tong Li = Haotong Li
    12317: "30957",   # Maximilian Kieffer = Max Kieffer
    20722: "48867",   # Matthias Schmid = Matti Schmid
    6986:  "24024",   # Zach Johnson (the major winner; our files have two Zach Johnsons)
    17619: "29747",   # Zach Johnson (the other: 2018/2020 PGA Championships, R2026554)
}


def name_key(name: str) -> str:
    """Order-free, accent-free, punctuation-free key, so 'Potter, Jr., Ted'
    (DataGolf) and 'Ted Potter, Jr.' (PGA TOUR) collapse together.
    Suffixes (Jr, III) are dropped."""
    s = unicodedata.normalize("NFD", str(name).translate(_FOLD))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower().replace(",", " ")
    words = ("".join(c for c in w if c.isalnum()) for w in s.replace("-", " ").split())
    return " ".join(sorted(w for w in words if w and w not in _SUFFIXES))


def _pga_leaderboards() -> pd.DataFrame:
    files = sorted(HIST.glob("leaderboards_20[0-9][0-9].csv"))
    if not files:
        return pd.DataFrame(columns=["tournament_id", "player_id", "player_name", "position", "tournament_name"])
    return pd.concat([pd.read_csv(f, usecols=["tournament_id", "player_id", "player_name", "position", "tournament_name"],
                                  dtype=str) for f in files], ignore_index=True)


def build_player_crosswalk(lb: pd.DataFrame) -> dict[str, str]:
    """name_key -> existing player_id, built from every player in the
    PGA TOUR-sourced leaderboard CSVs. Keeps DG-sourced rows on the SAME
    player_id as their history instead of fracturing it under a new identity."""
    # Older files zero-pad ids ("06567"), 2026's don't ("6567"): one player.
    # `lb` is in season order, so the last form seen is the current one.
    ids: dict[str, dict[str, str]] = {}
    for pid, name in lb[["player_id", "player_name"]].drop_duplicates().itertuples(index=False):
        # Never map onto an earlier run's synthetic DG id.
        if pd.notna(pid) and pd.notna(name) and not str(pid).startswith("DG"):
            ids.setdefault(name_key(name), {})[str(pid).lstrip("0")] = str(pid)
    # A name two players share matches neither (fail closed).
    return {k: next(iter(v.values())) for k, v in ids.items() if len(v) == 1}


def load_our_events(lb: pd.DataFrame) -> dict[str, dict]:
    """tid -> {name, date, winner} for every event we already know (PGA
    leaderboards + tournament_stats), so a DG event can be checked before
    it's written under one of our ids."""
    names = [lb[["tournament_id", "tournament_name"]]]
    for f in sorted(HIST.glob("tournament_stats_20*.csv")):
        names.append(pd.read_csv(f, usecols=["tournament_id", "tournament_name"], dtype=str).drop_duplicates())
    names = pd.concat(names).dropna().drop_duplicates("tournament_id").set_index("tournament_id")["tournament_name"]
    won = lb[lb["position"].astype(str).str.strip() == "1"].drop_duplicates("tournament_id").set_index("tournament_id")
    winners, winner_ids = won["player_name"], won["player_id"]
    ev, ov = load_events(), load_overrides()

    def date_of(tid: str, name: str):
        try:
            return training_event_date(tid, name, ev, ov)
        except ValueError:          # seasons before the date table (pre-2015)
            return None

    return {tid: {"name": name, "date": date_of(tid, name), "winner": winners.get(tid), "winner_id": winner_ids.get(tid)}
            for tid, name in names.items()}


def _same_winner(known: dict, dg_winner: str | None, dg_winner_id: str | None) -> bool | None:
    """True/False when both sides name a winner, None when either doesn't.
    Player ids first (spelling-proof), names when an id is synthetic."""
    if not (known["winner"] and dg_winner):
        return None
    if dg_winner_id and not dg_winner_id.startswith("DG") and known.get("winner_id") \
            and not str(known["winner_id"]).startswith("DG"):
        return str(known["winner_id"]).lstrip("0") == dg_winner_id.lstrip("0")
    return name_key(known["winner"]) == name_key(dg_winner)


def check_event(tid: str, dg_name: str, dg_date: pd.Timestamp, dg_winner: str | None,
                ours: dict[str, dict], dg_winner_id: str | None = None) -> str | None:
    """None when it's safe to write this DG event under `tid`, else why not.
    Ids collide across seasons (our R2021014 is the November 2020 Masters;
    DataGolf's April 2021 Masters maps to the same id), so a name match
    alone isn't enough: the date and, when we have it, the winner must agree.
    An event we don't know is skipped if it's one of ours under another id."""
    known = ours.get(tid)
    if known:
        if not names_match(dg_name, known["name"]):
            # Sponsors rename events (Mayakoba -> World Wide Technology). The
            # date AND the winner agreeing identify it better than the name.
            same_day = known["date"] is not None and abs((dg_date - known["date"]).days) <= MAX_DATE_GAP_DAYS
            if same_day and _same_winner(known, dg_winner, dg_winner_id):
                print(f"  renamed: DG '{dg_name}' = ours '{known['name']}' (same date and winner)")
                return None
            return f"name mismatch: DG '{dg_name}' vs ours '{known['name']}'"
        if known["date"] is not None and abs((dg_date - known["date"]).days) > MAX_DATE_GAP_DAYS:
            return f"date mismatch: DG {dg_date.date()} vs ours {known['date'].date()}"
        if _same_winner(known, dg_winner, dg_winner_id) is False:
            return f"winner mismatch: DG {dg_winner} vs ours {known['winner']}"
        return None
    for other, k in ours.items():
        if k["date"] is not None and abs((dg_date - k["date"]).days) <= MAX_DATE_GAP_DAYS \
                and names_match(dg_name, k["name"]):
            return f"already ours as {other} ('{k['name']}')"
    return None


def write_csv(season: int, tid: str, lb_rows: list[dict]) -> Path:
    """Replace tid's rows in leaderboards_dg_{season}.csv (idempotent)."""
    path = HIST / DG_CSV.format(season=season)
    new = pd.DataFrame([{
        **{k: r[k] for k in ("tournament_id", "player_id", "position", "total_score",
                             "to_par", "fedex_points", "earnings", "rounds_played", "tournament_name")},
        "player_name": first_last(r["player_name"]),
        "year": season,
        **{f"r{i}_score": r[f"r{i}"] for i in range(1, 5)},
        **{f"r{i}_to_par": r["_r_to_par"][i - 1] for i in range(1, 5)},
        "dg_id": r["_dg_id"],
    } for r in lb_rows], columns=CSV_COLS)
    if path.exists():
        old = pd.read_csv(path, dtype=str)
        new = pd.concat([old[old["tournament_id"] != tid], new.astype(str).replace({"None": "", "nan": ""})])
    new = new.sort_values(["tournament_id", "player_name"], kind="stable")
    new.to_csv(path, index=False)
    return path


def first_last(name: str) -> str:
    """DataGolf's 'Rahm, Jon' -> 'Jon Rahm' and 'Potter, Jr., Ted' ->
    'Ted Potter, Jr.', the layout our files use."""
    parts = [x.strip() for x in str(name).split(",")]
    if len(parts) == 3:
        return f"{parts[2]} {parts[0]}, {parts[1]}"
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    return str(name).strip()


def resolve_player_id(dg_name: str, dg_id: int, crosswalk: dict[str, str]) -> str:
    """Existing player_id if this player has prior history; otherwise a
    DG-prefixed synthetic ID that can't collide with the numeric PGA space."""
    return DG_ALIASES.get(int(dg_id)) or crosswalk.get(name_key(dg_name)) or f"DG{dg_id}"


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
            "_r_to_par": [(r["score"] - r["course_par"]) if r and r.get("score") is not None and r.get("course_par") is not None
                          else None for r in rounds],
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


def list_events(tour: str) -> list[dict]:
    """DG's event list with a parsed date and OUR season id attached."""
    ev = load_events()
    out = []
    for e in dg_get("/historical-raw-data/event-list", {"file_format": "json"}):
        # Our season windows (event_dates) start with the 2015 calendar year;
        # nothing reads history before the 2016 season.
        if e.get("tour") != tour or not e.get("date") or int(e.get("calendar_year", 0)) < 2015:
            continue
        date = pd.Timestamp(e["date"])
        season = season_for(date, ev)
        out.append({**e, "date": date, "season": season, "tid": f"R{season}{int(e['event_id']):03d}"})
    return out


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


def run_season(
    season: int, events: list[dict], event_id: int | None, crosswalk: dict[str, str],
    ours: dict[str, dict], conn, dry_run: bool, missing_only: bool,
    new_players: set[str], rounds_only: bool = False,
) -> tuple[int, int, int]:
    """Fetch + write every DG event in one of OUR seasons (or one event).
    Returns (leaderboard_rows, stat_rows, round_rows) written."""
    todo = [e for e in events if e["season"] == season and (event_id is None or e["event_id"] == event_id)]
    # Season ids are unique across DG's list (2015+, checked Oct 20: a second
    # edition in one season gets its own event_id, e.g. "The Masters #2" = 536).
    have: set[str] = set()
    if missing_only:
        path = HIST / DG_CSV.format(season=season)
        if path.exists():
            have = set(pd.read_csv(path, usecols=["tournament_id"], dtype=str)["tournament_id"])
        todo = [e for e in todo if e["tid"] not in have]
    print(f"\n=== season {season}: {len(todo)} event(s) ===")

    total_lb = total_stats = total_rounds = 0
    for e in todo:
        tid, eid = e["tid"], int(e["event_id"])
        # DG's date is the final round. A sweep leaves anything that ended in
        # the last two days alone (a Monday finish could still be in play);
        # asking for one event (post-tournament, gated on "official") doesn't.
        cutoff = pd.Timestamp.now().normalize() - (pd.Timedelta(0) if event_id else pd.Timedelta(days=1))
        if e["date"] >= cutoff + pd.Timedelta(days=1) or (event_id is None and e["date"] >= cutoff):
            continue
        print(f"\n{tid} (DG {e['calendar_year']} event_id={eid}, {e['date'].date()} {e['event_name']})...")
        raw = fetch_one_event(e["tour"], eid, int(e["calendar_year"]))
        if raw is None:
            print("  No data returned — skipping")
            continue

        lb_rows, stat_rows, round_rows = parse_event(raw, tid, season)
        for row in lb_rows + stat_rows + round_rows:
            row["player_id"] = resolve_player_id(row["player_name"], row["_dg_id"], crosswalk)
        champ = next((r for r in lb_rows if str(r["position"]).strip() == "1"), None)
        winner, winner_id = (champ["player_name"], champ["player_id"]) if champ else (None, None)
        why = check_event(tid, raw.get("event_name") or e["event_name"], e["date"], winner, ours, winner_id)
        if why:
            print(f"  SKIPPED: {why}")
            continue

        matched = 0
        for row in lb_rows:
            if row["player_id"].startswith("DG"):
                new_players.add(row["player_name"])
            else:
                matched += 1

        print(f"  {raw.get('event_name')}: {len(lb_rows)} players, {matched} matched, winner {winner}")

        if not dry_run:
            path = write_csv(season, tid, lb_rows)
            print(f"  wrote {path.name}")
            if conn is not None:
                upsert(conn, lb_rows, stat_rows, round_rows, rounds_only=rounds_only)

        total_lb += len(lb_rows)
        total_stats += len(stat_rows)
        total_rounds += len(round_rows)

    return total_lb, total_stats, total_rounds


def main():
    parser = argparse.ArgumentParser(description="Fetch historical results + SG stats from DataGolf")
    parser.add_argument("--year", type=int, default=None, help="Single PGA TOUR season (our id's year)")
    parser.add_argument("--start-year", type=int, default=None, help="First season of a range (inclusive)")
    parser.add_argument("--end-year", type=int, default=None, help="Last season of a range (inclusive)")
    parser.add_argument("--event-id", type=int, default=None,
                         help="Single DG event_id; omit to fetch every event for the season (only valid with --year)")
    parser.add_argument("--tour", default="pga")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--missing-only", action="store_true",
                        help="Skip events already in leaderboards_dg_{season}.csv (catch-up runs)")
    parser.add_argument("--no-db", action="store_true", help="Don't touch DuckDB even if it exists")
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

    # DuckDB lives only on Jack's Mac. In the cloud the CSV is the record.
    conn = None
    if DB_PATH.exists() and not args.no_db and not args.dry_run:
        sys.path.insert(0, str(ROOT / "scripts" / "database"))
        from db import get_conn
        conn = get_conn(read_only=False)

    lb = _pga_leaderboards()
    crosswalk = build_player_crosswalk(lb)
    ours = load_our_events(lb)
    events = list_events(args.tour)
    print(f"Player crosswalk: {len(crosswalk)} known players; {len(ours)} known events")

    total_lb = total_stats = total_rounds = 0
    new_players: set[str] = set()
    for season in years:
        lbn, st, rnd = run_season(season, events, args.event_id, crosswalk, ours, conn, args.dry_run,
                                  args.missing_only, new_players, rounds_only=args.rounds_only)
        total_lb += lbn
        total_stats += st
        total_rounds += rnd

    if conn is not None:
        conn.close()
    print(f"\nDone — {total_lb} leaderboard rows, {total_stats} stat rows, {total_rounds} round rows across {len(years)} season(s).")
    if new_players:
        preview = sorted(new_players)[:10]
        print(f"  {len(new_players)} players with no prior history (DG-prefixed IDs): "
              f"{preview}{'...' if len(new_players) > 10 else ''}")

    # Nonzero exit when a single requested event wasn't found — lets callers
    # detect "DG has no data for this yet". A catch-up run with nothing new is fine.
    if total_lb == 0 and args.event_id is not None:
        sys.exit(1)


if __name__ == "__main__":
    main()
