#!/usr/bin/env python3
"""
Sync WineTime fantasy scorecard → usage_tracker_2026.json

This is the single source of truth. Enter picks on the fantasy site;
run this script (or let the scheduler do it) and the tracker auto-updates.

URL: https://connection.protourfantasygolf.com/scorecard/individual/2026/0/133
  year=2026, period=0 (full season), team_id=133 (WineTime)

Run:
    python scripts/scrapers/fetch_fantasy_scorecard.py
    python scripts/scrapers/fetch_fantasy_scorecard.py --dry-run
"""
from pathlib import Path
import os, sys, re, json, argparse, csv
from datetime import datetime

import requests
from bs4 import BeautifulSoup
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

PROJECT_ROOT  = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

SCORECARD_URL  = "https://connection.protourfantasygolf.com/scorecard/individual/2026/0/133"
WEEKLY_LINEUP_URL = "https://connection.protourfantasygolf.com/weekly_lineup"
BASE_URL       = "https://connection.protourfantasygolf.com"
TRACKER_FILE   = PROJECT_ROOT / "data" / "fantasy" / "usage_tracker_2026.json"
SCHEDULE_FILE  = PROJECT_ROOT / "data" / "raw" / "schedule_2026.csv"
MAX_USES       = 3
ENV_FILE       = PROJECT_ROOT / ".env"


# ---------------------------------------------------------------------------
# Schedule lookup
# ---------------------------------------------------------------------------

def _load_schedule() -> dict:
    """week_num (int) -> {tournament_name, start_date, tournament_id}"""
    mapping = {}
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE) as f:
            for row in csv.DictReader(f):
                try:
                    mapping[int(row["week"])] = {
                        "tournament_name": row["tournament_name"],
                        "start_date":      row.get("start_date", ""),
                        "tournament_id":   row.get("tournament_id", ""),
                    }
                except (ValueError, KeyError):
                    pass
    return mapping


# ---------------------------------------------------------------------------
# Parse earnings
# ---------------------------------------------------------------------------

def _parse_earnings(text: str) -> int:
    text = str(text).strip().replace(",", "").replace("$", "").replace("—", "").replace("-", "")
    try:
        v = int(float(text))
        return v if v >= 0 else 0
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Scrape
# ---------------------------------------------------------------------------

def fetch_scorecard() -> list[dict]:
    """Return list of week dicts scraped from the fantasy site."""
    resp = requests.get(SCORECARD_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table", id="weeklyResultsTable")
    if not table:
        raise RuntimeError("weeklyResultsTable not found — page structure may have changed")

    rows = []
    for tr in table.find_all("tr")[1:]:   # skip header row
        cells = tr.find_all("td")
        if len(cells) < 9:
            continue

        week_text = cells[0].get_text(strip=True)
        try:
            week = int(week_text)
        except ValueError:
            continue

        tournament = cells[1].get_text(strip=True)
        if not tournament:
            continue

        # WRP: sortable_custom_key is zero-padded rank string e.g. "0002"
        wrp_raw = cells[2].get("sortable_custom_key", "").lstrip("0") or None
        wrp = int(wrp_raw) if wrp_raw and wrp_raw.isdigit() else None

        players = []
        for col in (3, 5, 7):
            td_name  = cells[col]     if col     < len(cells) else None
            td_earn  = cells[col + 1] if col + 1 < len(cells) else None

            if td_name is None:
                continue

            name = td_name.get_text(strip=True)
            if not name or name in ("—", "-", ""):
                continue

            # finish from title attribute e.g. "Place = T10", "Place = CUT"
            title   = td_name.get("title", "")
            finish_m = re.search(r"Place\s*=\s*(.+)", title)
            finish  = finish_m.group(1).strip() if finish_m else None

            # winner flag
            winner = bool(td_name.find("span", class_="weeklyResultsWinningGolfer"))

            earnings = _parse_earnings(td_earn.get_text(strip=True)) if td_earn else 0

            players.append({
                "name":     name,
                "finish":   finish,
                "winner":   winner,
                "earnings": earnings,
            })

        total_text = cells[9].get_text(strip=True) if len(cells) > 9 else ""
        total      = _parse_earnings(total_text) if total_text not in ("", "—", "-") else None
        pending    = (total is None and bool(players))

        rows.append({
            "week":       week,
            "tournament": tournament,
            "wrp":        wrp,
            "players":    players,
            "total":      total,
            "pending":    pending,
        })

    return rows


# ---------------------------------------------------------------------------
# Current-week pending lineup (logged-in only)
# ---------------------------------------------------------------------------

def fetch_pending_lineup() -> dict | None:
    """Fetch the currently selected lineup from /weekly_lineup using auth session.

    Returns dict with keys: week (int), tournament (str), players (list[str]),
    alternate (str | None) — or None if credentials missing or request fails.

    The scorecard page shows '-- XXXXXXXXX --' placeholders for a submitted-but-
    unrevealed current-week lineup. This function reads the actual selected options
    from the lineup form so the tracker reflects the real picks immediately.
    """
    if load_dotenv is None:
        return None
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    email    = os.environ.get("PTFG_EMAIL", "")
    password = os.environ.get("PTFG_PASSWORD", "")
    if not email or not password:
        return None

    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Mozilla/5.0"})
        sess.get(f"{BASE_URL}/login", timeout=15)
        r = sess.post(
            f"{BASE_URL}/login",
            data={"user[login]": email, "user[password]": password, "remember_me": "1"},
            allow_redirects=True,
            timeout=15,
        )
        if "/login" in r.url:
            print("[WARN] fetch_pending_lineup: login failed — skipping")
            return None

        r2   = sess.get(WEEKLY_LINEUP_URL, timeout=15)
        soup = BeautifulSoup(r2.text, "html.parser")

        # Week + tournament from page heading
        heading = soup.get_text(separator="\n", strip=True)
        week_m  = re.search(r"Week\s+(\d+):\s*([^\n(]+)", heading)
        week_num   = int(week_m.group(1)) if week_m else None
        tournament = week_m.group(2).strip() if week_m else ""

        def _selected_name(select_name: str) -> str | None:
            sel = soup.find("select", {"name": select_name})
            if not sel:
                return None
            opt = sel.find("option", selected=True)
            if not opt:
                return None
            # Strip trailing usage count " (N)" from option text
            text = opt.get_text(strip=True)
            text = re.sub(r"\s*\(\d+\)\s*$", "", text).strip()
            return text if text else None

        players   = [n for n in [
            _selected_name("golfer1[id]"),
            _selected_name("golfer2[id]"),
            _selected_name("golfer3[id]"),
        ] if n]
        alternate = _selected_name("alternate_golfer[id]")

        if not players:
            return None

        return {
            "week":       week_num,
            "tournament": tournament,
            "players":    players,   # "Last, First" site format
            "alternate":  alternate,
        }
    except Exception as e:
        print(f"[WARN] fetch_pending_lineup failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Rebuild tracker
# ---------------------------------------------------------------------------

def rebuild_tracker(rows: list[dict], schedule: dict, dry_run: bool = False) -> dict:
    """
    Build a fresh tracker dict from scraped rows.
    Preserves the same JSON schema as usage_tracker_2026.json.
    """
    picks   = {}   # player_name -> PlayerUsage dict
    lineups = {}   # week_key    -> lineup dict

    for row in rows:
        week      = row["week"]
        tourney   = row["tournament"]
        players   = row["players"]
        total     = row["total"]
        week_key  = f"week_{week}"

        # Canonical tournament name from schedule (fallback to site name)
        sched_info   = schedule.get(week, {})
        canon_tourney = sched_info.get("tournament_name", tourney)
        start_date    = sched_info.get("start_date", "")

        lineup_names = []

        for p in players:
            site_name = p["name"]
            # Normalise site "Last, First" → tracker canonical key
            canon = _to_canonical(site_name, picks)

            lineup_names.append(canon)

            if canon not in picks:
                picks[canon] = {
                    "times_used":       0,
                    "remaining_uses":   MAX_USES,
                    "tournaments_used": [],
                    "total_earnings":   0,
                    "total_points":     0,
                }

            player = picks[canon]

            # Avoid duplicate tournament entries
            already = any(
                t.get("week") == week or t.get("tournament") == canon_tourney
                for t in player["tournaments_used"]
            )
            if not already:
                player["tournaments_used"].append({
                    "tournament": canon_tourney,
                    "week":       week,
                    "date":       start_date,
                    "result":     p.get("finish"),
                    "earnings":   p.get("earnings", 0),
                })
                player["times_used"]     += 1
                player["remaining_uses"]  = max(0, MAX_USES - player["times_used"])
                player["total_earnings"] += p.get("earnings", 0)

        lineups[week_key] = {
            "tournament":      canon_tourney,
            "week":            week,
            "date":            start_date,
            "lineup":          lineup_names,
            "wrp":             row.get("wrp"),
            "earnings_earned": total,
            "points_earned":   total,
        }

    # Sort tournaments_used by week for each player
    for p in picks.values():
        p["tournaments_used"].sort(key=lambda t: t.get("week", 0))

    tracker = {
        "season":              "2026",
        "max_uses_per_player": MAX_USES,
        "players_per_lineup":  3,
        "last_updated":        datetime.now().isoformat(),
        "last_synced_from":    SCORECARD_URL,
        "picks":               picks,
        "weekly_lineups":      lineups,
        "summary": {
            "total_weeks":    len(lineups),
            "total_players":  len(picks),
            "total_earnings": sum(
                v.get("earnings_earned") or 0 for v in lineups.values()
            ),
        },
    }
    return tracker


def _to_canonical(site_name: str, existing_picks: dict) -> str:
    """
    Convert site format 'Last, First' to 'First Last'.
    If an existing key in picks matches by last name + first initial, reuse it.
    Handles both 'Last, First' and already-canonical 'First Last' formats.
    """
    site_name = site_name.strip()

    if "," in site_name:
        parts     = [p.strip() for p in site_name.split(",", 1)]
        last_name = parts[0]
        first     = parts[1] if len(parts) > 1 else ""
    else:
        # Already 'First Last' or single name
        words     = site_name.split()
        last_name = words[-1] if words else site_name
        first     = " ".join(words[:-1]) if len(words) > 1 else ""

    first_init = first[0].lower() if first else ""
    last_lower = last_name.lower()

    # Check existing picks for a match (last name + optional first initial)
    for key in existing_picks:
        k_words = key.split()
        k_last  = k_words[-1].lower() if k_words else ""
        k_first = k_words[0][0].lower() if k_words else ""
        if k_last == last_lower and (not first_init or k_first == first_init):
            return key

    # Build canonical form: "First Last"
    if first:
        return f"{first} {last_name}"
    return last_name


# ---------------------------------------------------------------------------
# Season log rebuild
# ---------------------------------------------------------------------------

def rebuild_season_log(tracker: dict):
    """Write outputs/season_log.csv from tracker data."""
    import csv as _csv
    out_path = PROJECT_ROOT / "outputs" / "season_log.csv"
    rows     = []

    for wk, entry in sorted(tracker["weekly_lineups"].items(),
                             key=lambda x: int(x[0].split("_")[1])):
        week_num = entry.get("week", "")
        tourney  = entry.get("tournament", "")
        lineup   = entry.get("lineup", [])
        total    = entry.get("earnings_earned")
        wrp      = entry.get("wrp")

        player_cols = []
        for i, name in enumerate(lineup[:3]):
            p     = tracker["picks"].get(name, {})
            t_rec = next(
                (t for t in p.get("tournaments_used", []) if t.get("week") == week_num),
                {}
            )
            player_cols += [
                name,
                t_rec.get("result", ""),
                t_rec.get("earnings", 0),
            ]
        while len(player_cols) < 9:
            player_cols += ["", "", 0]

        rows.append([
            week_num, tourney, wrp or "",
            player_cols[0], player_cols[1], player_cols[2],
            player_cols[3], player_cols[4], player_cols[5],
            player_cols[6], player_cols[7], player_cols[8],
            total or "",
        ])

    with open(out_path, "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow([
            "week", "tournament", "wrp",
            "player_1", "result_1", "earnings_1",
            "player_2", "result_2", "earnings_2",
            "player_3", "result_3", "earnings_3",
            "total_earnings",
        ])
        w.writerows(rows)

    print(f"[OK] Season log → {out_path} ({len(rows)} weeks)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync WineTime fantasy scorecard → tracker")
    parser.add_argument("--dry-run", action="store_true", help="Print without saving")
    args = parser.parse_args()

    schedule = _load_schedule()

    print(f"[INFO] Fetching scorecard from {SCORECARD_URL}")
    rows = fetch_scorecard()
    print(f"[INFO] Parsed {len(rows)} weeks\n")

    # Patch current-week row if it has placeholder names (picks submitted but unrevealed)
    print("[INFO] Fetching current-week lineup from /weekly_lineup...")
    pending = fetch_pending_lineup()
    if pending and pending.get("players"):
        week_num = pending["week"]
        # Find the matching row (by week number) or the one with placeholder names
        _PLACEHOLDER = re.compile(r"^-+\s*X+\s*-+$")
        patched = False
        for r in rows:
            if r["week"] == week_num:
                has_placeholder = any(_PLACEHOLDER.match(p["name"]) for p in r["players"])
                is_empty = not r["players"]
                if has_placeholder or is_empty:
                    r["players"] = [
                        {"name": n, "finish": None, "winner": False, "earnings": 0}
                        for n in pending["players"]
                    ]
                    r["pending"] = True
                    print(f"  Patched wk {week_num} with live picks: {', '.join(pending['players'])}")
                    if pending.get("alternate"):
                        print(f"  Alternate: {pending['alternate']}")
                    patched = True
                break
        if not patched and week_num:
            # Week not in scorecard yet — inject it
            sched_info = schedule.get(week_num, {})
            rows.append({
                "week":       week_num,
                "tournament": sched_info.get("tournament_name", pending["tournament"]),
                "wrp":        None,
                "players":    [
                    {"name": n, "finish": None, "winner": False, "earnings": 0}
                    for n in pending["players"]
                ],
                "total":   None,
                "pending": True,
            })
            print(f"  Injected wk {week_num}: {', '.join(pending['players'])}")
    else:
        print("  No pending lineup found (credentials missing or picks not yet submitted)")

    for r in rows:
        status  = "pending" if r["pending"] else (f"${r['total']:,}" if r["total"] else "no data")
        players = ", ".join(
            f"{p['name']} ({p['finish'] or '?'})" + (" WIN" if p["winner"] else "")
            for p in r["players"]
        )
        print(f"  Wk {r['week']:>2} | {r['tournament'][:32]:<32} | {players} → {status}")

    print()
    tracker = rebuild_tracker(rows, schedule, dry_run=args.dry_run)

    total_earn = tracker["summary"]["total_earnings"]
    print(f"[INFO] {len(rows)} weeks | {tracker['summary']['total_players']} players | "
          f"${total_earn:,} total earnings")

    if not args.dry_run:
        TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKER_FILE, "w") as f:
            json.dump(tracker, f, indent=2)
        print(f"[OK] Tracker saved → {TRACKER_FILE}")
        rebuild_season_log(tracker)
    else:
        print("[DRY RUN] No files written.")


if __name__ == "__main__":
    main()
