#!/usr/bin/env python3
"""
Scheduled Data Refresh
======================

Automatically runs the appropriate scrapers based on day/time.
Can be run via cron, launchd, or manually.

Schedule:
- Monday 6:00 AM: Player database update (OWGR/form stats/SG stats handled by post-tournament)
- Tuesday 6:00 AM: Tournament prep (field, course info, betting profiles, predictions)
- Tuesday 6:00 PM: Odds refresh (DK, PGA odds)
- Wednesday 6:00 AM: Final prep (odds refresh, re-run predictions)
- Wednesday 6:00 PM: Final odds refresh
- Thursday-Sunday 8:00 AM: Live refresh (leaderboard, live odds)
- Thursday-Sunday 2:00 PM: Live refresh
- Thursday-Sunday 8:00 PM: Live refresh
- Sunday 9:00 PM: Post-tournament refresh (first attempt — checks Official status)
- Sunday 11:00 PM: Record results
- Monday 8:00 AM: Post-tournament fallback (if Mac was asleep Sunday)

Usage:
    # Run based on current day/time
    python3 scripts/scheduled_refresh.py

    # Force a specific schedule
    python3 scripts/scheduled_refresh.py --schedule monday
    python3 scripts/scheduled_refresh.py --schedule tuesday-morning
    python3 scripts/scheduled_refresh.py --schedule tuesday-evening
    python3 scripts/scheduled_refresh.py --schedule wednesday-morning
    python3 scripts/scheduled_refresh.py --schedule live
    python3 scripts/scheduled_refresh.py --schedule record
    python3 scripts/scheduled_refresh.py --schedule post-tournament

    # Dry run (show what would run)
    python3 scripts/scheduled_refresh.py --dry-run

Cron Examples (add to crontab -e):
    # Monday 6am - post tournament
    0 6 * * 1 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule monday >> logs/scheduler.log 2>&1

    # Tuesday 6am - tournament prep
    0 6 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-morning >> logs/scheduler.log 2>&1

    # Tuesday 6pm - odds refresh
    0 18 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-evening >> logs/scheduler.log 2>&1

    # Wednesday 6am - final prep
    0 6 * * 3 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule wednesday-morning >> logs/scheduler.log 2>&1

    # Thursday-Sunday 8am, 2pm, 8pm - live updates
    0 8,14,20 * * 4-7 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule live >> logs/scheduler.log 2>&1

    # Sunday 11pm - record results
    0 23 * * 0 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule record >> logs/scheduler.log 2>&1
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
SCHEDULE_PATH = DATA_DIR / "raw" / "schedule_2026.csv"

# Ensure logs directory exists
LOGS_DIR.mkdir(exist_ok=True)

# Course coordinates for weather snapshots (subset matching fetch_weather_openmetro.py)
_COURSE_COORDS = {
    "pebble beach": (36.5675, -121.9486),
    "torrey pines": (32.9005, -117.2516),
    "augusta national": (33.5021, -82.0232),
    "tpc scottsdale": (33.6417, -111.9083),
    "riviera": (34.0489, -118.5003),
    "bay hill": (28.4603, -81.5053),
    "tpc sawgrass": (30.1975, -81.3964),
    "harbour town": (32.1363, -80.8090),
    "quail hollow": (35.1089, -80.8519),
    "southern hills": (36.0631, -95.9408),
    "bethpage black": (40.7445, -73.4533),
    "valhalla": (38.2527, -85.4938),
    "pinehurst": (35.1894, -79.4694),
    "tpc san antonio": (29.5585, -98.6193),
    "innisbrook": (28.1531, -82.7338),
    "tpc louisiana": (29.9421, -90.1710),
    "pga national": (26.8373, -80.1169),
    "sedgefield": (36.0413, -79.8888),
    "muirfield village": (40.1037, -83.1418),
    "colonial": (32.7157, -97.3671),
    "east lake": (33.7215, -84.3019),
    "kapalua": (20.9931, -156.6647),
    "waialae": (21.2769, -157.7559),
}


def _find_course_coords(tournament_name: str):
    """Fuzzy-match tournament name to known course coordinates."""
    tname_lower = tournament_name.lower()
    for key, coords in _COURSE_COORDS.items():
        if key in tname_lower:
            return coords
    return None


def save_weather_snapshot(tid: str, tournament_name: str) -> bool:
    """Fetch tournament weather forecast from PGA Tour API and save to data/weather/{tid}.json.

    Returns True on success.
    """
    import requests as _requests
    import json as _json

    weather_dir = DATA_DIR / "weather"
    weather_dir.mkdir(parents=True, exist_ok=True)
    out_path = weather_dir / f"{tid}.json"

    try:
        resp = _requests.post(
            "https://orchestrator.pgatour.com/graphql",
            json={
                "query": """
query Weather($tournamentId: ID!) {
  weather(tournamentId: $tournamentId) {
    title
    hourly {
      title condition windDirection windSpeedKPH windSpeedMPH humidity precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
    daily {
      title condition windDirection windSpeedKPH windSpeedMPH humidity precipitation
      temperature {
        ... on StandardWeatherTemp { __typename tempC tempF }
        ... on RangeWeatherTemp { __typename minTempC minTempF maxTempC maxTempF }
      }
    }
  }
}
""",
                "variables": {"tournamentId": tid},
                "operationName": "Weather",
            },
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-pgat-platform": "web",
                "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
                "Origin": "https://www.pgatour.com",
                "Referer": "https://www.pgatour.com/",
            },
            timeout=15,
        )
        resp.raise_for_status()
        _body = resp.json()
        if _body.get("errors"):
            raise RuntimeError(_body["errors"][0].get("message", "Weather query failed"))
        _w = _body.get("data", {}).get("weather")
        if _w and _w.get("daily"):
            from datetime import datetime as _dt
            result = {
                "success": True,
                "source": "pgatour",
                "title": _w.get("title", ""),
                "daily": _w["daily"],
                "hourly": _w.get("hourly", []),
                "saved_at": _dt.now().isoformat(),
            }
            out_path.write_text(_json.dumps(result, indent=2))
            log(f"  Weather saved: {len(_w['daily'])} days for {tid}")
            return True
        else:
            log(f"  PGA Tour weather API returned no daily data for {tid}")
            return False
    except Exception as e:
        log(f"  Weather snapshot failed for {tid}: {e}")
        return False


STEP_TIMEOUTS = {
    "Tournament SG Stats": 1800,
    "Field": 300,
    "Course Info": 300,
    "Power Rankings": 300,
    "Expert Picks": 300,
    "Betting Profiles": 900,
    "DraftKings Odds": 360,
    "PGA Odds": 300,
    "Predictions": 900,
    "Refresh Odds": 120,
    "Recommend Bets": 120,
}


def log(message: str):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_command(cmd: list, description: str, timeout: int = 180) -> bool:
    """Run a command and return success status."""
    log(f"Running: {description}")
    log(f"  Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            log(f"  ✓ Success")
            return True
        else:
            log(f"  ✗ Failed: {result.stderr[:200] if result.stderr else 'Unknown error'}")
            return False
    except subprocess.TimeoutExpired:
        log(f"  ✗ Timeout after {timeout}s")
        return False
    except Exception as e:
        log(f"  ✗ Error: {e}")
        return False


def step_timeout(description: str, default: int = 180) -> int:
    """Return timeout based on task label."""
    return int(STEP_TIMEOUTS.get(description, default))


def get_current_tournament() -> dict:
    """Get current or next tournament from schedule."""
    if not SCHEDULE_PATH.exists():
        return {}

    df = pd.read_csv(SCHEDULE_PATH)
    df["start_dt"] = pd.to_datetime(df["start_date"])
    df["end_dt"] = pd.to_datetime(df["end_date"])
    today = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))

    # Current tournament
    current = df[(df["start_dt"] <= today) & (df["end_dt"] >= today)]
    if not current.empty:
        return current.iloc[0].to_dict()

    # Next tournament
    upcoming = df[df["start_dt"] > today].sort_values("start_dt")
    if not upcoming.empty:
        return upcoming.iloc[0].to_dict()

    return {}


def get_last_tournament() -> dict:
    """Get the most recently completed tournament."""
    if not SCHEDULE_PATH.exists():
        return {}

    df = pd.read_csv(SCHEDULE_PATH)
    df["end_dt"] = pd.to_datetime(df["end_date"])
    today = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))

    past = df[df["end_dt"] < today].sort_values("end_dt", ascending=False)
    if not past.empty:
        return past.iloc[0].to_dict()

    return {}


def run_monday_refresh(dry_run: bool = False):
    """Monday-only steps not covered by post-tournament refresh."""
    log("=" * 60)
    log("MONDAY REFRESH - Player Database")
    log("=" * 60)
    # World Rankings, Form Stats, and SG Stats are handled by run_post_tournament_refresh()
    # (post-monday-8am job). This job only runs the player database update, which is
    # not part of the post-tournament sequence.

    tasks = [
        ("Player Database", ["python3", "scripts/scrapers/fetch_player_database.py"]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            timeout = step_timeout(desc, 120)
            success = run_command(cmd, desc, timeout=timeout)
            results.append((desc, success))

    return results


def run_tuesday_morning(dry_run: bool = False):
    """Tournament prep - field, course info, profiles, predictions."""
    log("=" * 60)
    log("TUESDAY MORNING - Tournament Prep")
    log("=" * 60)

    tournament = get_current_tournament()
    if not tournament:
        log("No tournament found in schedule!")
        return []

    tournament_name = tournament.get("tournament_name", "")
    tournament_id = str(tournament.get("tournament_id", ""))
    power_slug = str(tournament.get("power_slug", ""))

    log(f"Tournament: {tournament_name} (ID: {tournament_id})")

    if not tournament_id:
        log("No tournament ID found!")
        return []

    field_path = f"data/fields/field_{tournament_id}.csv"

    tasks = [
        ("Field", ["python3", "scripts/scrapers/fetch_field_from_pgatour.py",
                   "--pga-id", tournament_id, "--output", field_path, "--match-ids"]),
        ("Course Info", ["python3", "scripts/scrapers/fetch_course_characteristics.py",
                         "--tournament-id", tournament_id, "--profile"]),
        ("Power Rankings", ["python3", "scripts/scrapers/fetch_power_rankings.py",
                            "--slug", power_slug or tournament_name.lower().replace(" ", "-"), "--allow-fail"]),
        ("Betting Profiles", ["python3", "scripts/scrapers/fetch_betting_profiles.py",
                              "--tournament-id", tournament_id, "--field", field_path]),
        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                      "--tournament-id", tournament_id]),
        ("Predictions", ["python3", "scripts/run_pipeline.py",
                         "--tournament", tournament_name,
                         "--pga-id", tournament_id,
                         "--field", field_path,
                         "--use-schedule",
                         "--skip-refresh", "--calibrate", "--lineup"]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            timeout = step_timeout(desc, 180)
            success = run_command(cmd, desc, timeout=timeout)
            results.append((desc, success))

    # Save weather snapshot after field fetch
    if not dry_run and tournament_id and tournament_name:
        save_weather_snapshot(tournament_id, tournament_name)

    return results


def run_tuesday_evening(dry_run: bool = False):
    """Odds refresh."""
    log("=" * 60)
    log("TUESDAY EVENING - Odds Refresh")
    log("=" * 60)

    tournament = get_current_tournament()
    if not tournament:
        log("No tournament found!")
        return []

    tournament_id = str(tournament.get("tournament_id", ""))
    if not tournament_id:
        log("No tournament ID!")
        return []

    tasks = [
        ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                             "--tournament-id", tournament_id,
                             "--max-age-hours", "2",
                             "--fetch-profile", "fast",
                             "--no-snapshot"]),
        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                      "--tournament-id", tournament_id]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            success = run_command(cmd, desc, timeout=step_timeout(desc, 120))
            results.append((desc, success))

    return results


def run_wednesday_morning(dry_run: bool = False):
    """Final prep - refresh odds, expert picks, and predictions."""
    log("=" * 60)
    log("WEDNESDAY MORNING - Final Prep")
    log("=" * 60)

    tournament = get_current_tournament()
    if not tournament:
        log("No tournament found!")
        return []

    tournament_name = tournament.get("tournament_name", "")
    tournament_id = str(tournament.get("tournament_id", ""))

    tasks = [
        ("Expert Picks", ["python3", "scripts/scrapers/fetch_expert_picks_pga.py",
                          "--tournament-id", tournament_id]),
        ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                             "--tournament-id", tournament_id,
                             "--max-age-hours", "2",
                             "--fetch-profile", "fast",
                             "--no-snapshot"]),
        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                      "--tournament-id", tournament_id]),
        ("Predictions", ["python3", "scripts/run_pipeline.py",
                         "--tournament", tournament_name,
                         "--pga-id", tournament_id,
                         "--field", f"data/fields/field_{tournament_id}.csv",
                         "--use-schedule",
                         "--skip-refresh", "--calibrate", "--lineup"]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            timeout = step_timeout(desc, 120)
            success = run_command(cmd, desc, timeout=timeout)
            results.append((desc, success))

    return results


def run_live_refresh(dry_run: bool = False):
    """Live tournament updates."""
    log("=" * 60)
    log("LIVE REFRESH - Tournament Updates")
    log("=" * 60)

    tournament = get_current_tournament()
    tournament_id = str(tournament.get("tournament_id", "")) if tournament else ""

    tasks = [
        ("Live Leaderboard", ["python3", "scripts/scrapers/fetch_live_leaderboard.py"]),
    ]

    if tournament_id:
        tasks.append(("Hole Scores", ["python3", "scripts/scrapers/fetch_hole_scores.py",
                                      "--tournament-id", tournament_id]))
        tasks.append(("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                          "--tournament-id", tournament_id,
                                          "--max-age-hours", "0.5",
                                          "--fetch-profile", "fast",
                                          "--no-snapshot"]))
        tasks.append(("Refresh Odds", ["python3", "scripts/predictions/refresh_odds.py",
                                       "--tournament-id", tournament_id]))
        tasks.append(("Recommend Bets", ["python3", "scripts/models/recommend_bets.py",
                                         "--tournament-id", tournament_id]))
        
        # After fetching the fresh leaderboard, immediately blend actual scores 
        # into the predictions so live_projected_score stays current 
        
        tasks.append(("Live Prediction Update", ['python3', 'scripts/predictions/live_update_predictions.py', 
                                                 "--tournament-id", tournament_id
                                                 ]))
        
        
        

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            timeout = step_timeout(desc, 120)
            success = run_command(cmd, desc, timeout=timeout)
            results.append((desc, success))

    # Save once-per-live-run weather snapshot
    if not dry_run and tournament_id and tournament:
        tournament_name = str(tournament.get("tournament_name", ""))
        save_weather_snapshot(tournament_id, tournament_name)

    return results


def run_record_results(dry_run: bool = False):
    """Record tournament results."""
    log("=" * 60)
    log("RECORD RESULTS - Post-Tournament")
    log("=" * 60)

    tasks = [
        ("Final Leaderboard", ["python3", "scripts/scrapers/fetch_live_leaderboard.py"]),
        ("Auto Record Results", ["python3", "scripts/planning/auto_record_results.py"]),
        ("Grade Recommended Bets", ["python3", "scripts/models/grade_recommended_bets.py"]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            success = run_command(cmd, desc, timeout=120)
            results.append((desc, success))

    return results


def sync_leaderboard_to_db(tid: str, year: int) -> int:
    """Upsert leaderboard rows for a tournament from CSV into DuckDB.

    Returns the number of rows upserted (0 on failure or no data).
    """
    hist_path = DATA_DIR / "historical" / f"leaderboards_{year}.csv"
    if not hist_path.exists():
        log(f"  Leaderboard CSV not found: {hist_path}")
        return 0

    try:
        import duckdb
        df = pd.read_csv(hist_path)
        rows = df[df["tournament_id"] == tid].copy()
        if rows.empty:
            log(f"  No rows for {tid} in CSV — skipping DB sync")
            return 0

        # Coerce types to match DB schema
        rows["player_id"] = rows["player_id"].astype(str)
        rows["total_score"] = pd.to_numeric(rows["total_score"], errors="coerce")
        rows["to_par"] = rows["to_par"].astype(str).replace("nan", None)
        rows["earnings"] = rows["earnings"].astype(str).replace("nan", None)
        rows["rounds_played"] = pd.to_numeric(rows["rounds_played"], errors="coerce").fillna(0).astype(int)

        db_path = PROJECT_ROOT / "data" / "golf_data.db"
        con = duckdb.connect(str(db_path))
        con.execute(f"DELETE FROM leaderboards WHERE tournament_id = '{tid}'")
        con.execute("""
            INSERT INTO leaderboards
                (tournament_id, tournament_name, year, player_id, player_name,
                 position, total_score, to_par, earnings, rounds_played, fedex_points)
            SELECT tournament_id, tournament_name, year, player_id, player_name,
                   position, total_score, to_par, earnings, rounds_played, fedex_points
            FROM rows
        """)
        con.close()
        return len(rows)
    except Exception as e:
        log(f"  DB sync failed: {e}")
        return 0


def is_tournament_official(tid: str) -> bool:
    """Return True if the most recent leaderboard meta marks the tournament as Official."""
    meta = DATA_DIR / "live" / f"leaderboard_{tid.lower()}_meta.json"
    if not meta.exists():
        return False
    with open(meta) as f:
        data = json.load(f)
    return str(data.get("round_status", "")).lower() == "official"


def append_leaderboard_to_historical(tid: str, tournament_name: str, year: int) -> int:
    """Convert live leaderboard CSV to historical rows and append to leaderboards_{year}.csv.

    Returns the number of rows appended (0 if live file missing).
    """
    live_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    hist_path = DATA_DIR / "historical" / f"leaderboards_{year}.csv"

    if not live_path.exists():
        log(f"  Live leaderboard not found: {live_path}")
        return 0

    live = pd.read_csv(live_path)
    rows = []
    for _, r in live.iterrows():
        pos = str(r["position"])
        if pos in ("CUT", "MC"):
            rounds_played = 2
            fedex_points = 0.0
        elif pos == "WD":
            rounds_played = int(r["current_round"]) if pd.notna(r.get("current_round")) else 1
            fedex_points = 0.0
        else:
            rounds_played = 4
            fedex_points = float("nan")

        total_score = int(r["total_strokes"]) if pd.notna(r.get("total_strokes")) else None
        rows.append({
            "tournament_id": tid,
            "year": year,
            "player_id": int(r["player_id"]),
            "player_name": r["player_name"],
            "position": pos,
            "total_score": total_score,
            "to_par": r.get("total_numeric"),
            "fedex_points": fedex_points,
            "earnings": None,
            "rounds_played": rounds_played,
            "tournament_name": tournament_name,
        })

    new_df = pd.DataFrame(rows)

    if hist_path.exists():
        hist = pd.read_csv(hist_path)
        # Remove any existing rows for this tournament (idempotent re-run)
        hist = hist[hist["tournament_id"] != tid]
        combined = pd.concat([hist, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(hist_path, index=False)
    return len(new_df)


def run_post_tournament_refresh(dry_run: bool = False):
    """Full post-tournament sequence: leaderboard append + stats + form + record + grade."""
    log("=" * 60)
    log("POST-TOURNAMENT REFRESH")
    log("=" * 60)

    tournament = get_last_tournament()
    if not tournament:
        log("No completed tournament found in schedule!")
        return []

    tid = str(tournament.get("tournament_id", ""))
    name = str(tournament.get("tournament_name", ""))
    year = int(str(tid)[1:5]) if len(tid) >= 5 else datetime.now().year

    log(f"Tournament: {name} (ID: {tid})")

    sentinel = LOGS_DIR / f"post_tournament_{tid}.done"

    # Step 1: fetch leaderboard to get fresh meta for official check
    if dry_run:
        log(f"[DRY RUN] Would run: Final Leaderboard")
    else:
        run_command(
            ["python3", "scripts/scrapers/fetch_live_leaderboard.py", "--tournament-id", tid],
            "Final Leaderboard",
            timeout=120,
        )

    # Step 2: official status check
    if not dry_run and not is_tournament_official(tid):
        log(f"  {tid} not yet official — will retry next scheduled run")
        return [("Official Check", False)]

    # Step 3+4: append leaderboard to historical + write sentinel (idempotent)
    if sentinel.exists():
        log(f"  Leaderboard already appended for {tid} (sentinel exists)")
    else:
        if dry_run:
            log(f"[DRY RUN] Would append leaderboard for {tid} → leaderboards_{year}.csv")
            log(f"[DRY RUN] Would sync {tid} leaderboard to DuckDB")
        else:
            n = append_leaderboard_to_historical(tid, name, year)
            log(f"  Appended {n} rows to leaderboards_{year}.csv")
            n_db = sync_leaderboard_to_db(tid, year)
            log(f"  Synced {n_db} rows to DuckDB leaderboards table")
            sentinel.touch()

    # Steps 5-10: remaining scrapers (idempotent by design)
    tasks = [
        ("Tournament SG Stats", ["python3", "scripts/scrapers/fetch_tournament_stats.py",
                                  "--year", str(year), "--refresh-latest", "3"]),
        ("Form Stats", ["python3", "scripts/scrapers/fetch_form_stats.py", "--year", str(year)]),
        ("World Rankings", ["python3", "scripts/scrapers/fetch_world_rankings.py"]),
        ("Record Results", ["python3", "scripts/planning/auto_record_results.py"]),
        ("Grade Bets", ["python3", "scripts/models/grade_recommended_bets.py"]),
        ("CLV Tracking", ["python3", "scripts/validation/track_clv.py",
                          "--tournament-id", tid, "--tournament-name", name]),
    ]

    results = []
    for desc, cmd in tasks:
        if dry_run:
            log(f"[DRY RUN] Would run: {desc}")
            results.append((desc, True))
        else:
            success = run_command(cmd, desc, timeout=step_timeout(desc, 300))
            results.append((desc, success))

    return results


def is_round_in_progress() -> bool:
    """Return True if a tournament round is currently active (meta JSON says In Progress)."""
    live_dir = DATA_DIR / "live"
    meta_files = sorted(
        live_dir.glob("leaderboard_*_meta.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not meta_files:
        return False
    try:
        with open(meta_files[0]) as f:
            meta = json.load(f)
        return meta.get("round_status", "").lower() in ("in progress", "active", "playing")
    except Exception:
        return False


def watch_loop(interval_minutes: int = 10, dry_run: bool = False):
    """Continuously refresh live data while a tournament round is in progress.

    - Active round: refresh every `interval_minutes` minutes
    - No active round: check again in 30 minutes
    Stop with Ctrl+C.
    """
    log(f"Watch mode started (interval={interval_minutes}m during active round, 30m otherwise).")
    log("Press Ctrl+C to stop.")
    try:
        while True:
            if is_round_in_progress():
                log(f"Round in progress — running live refresh")
                run_live_refresh(dry_run=dry_run)
                sleep_min = interval_minutes
            else:
                log("No active round detected — will check again in 30 minutes")
                sleep_min = 30
            wake_at = datetime.now().strftime("%H:%M")
            next_at = datetime.fromtimestamp(
                datetime.now().timestamp() + sleep_min * 60
            ).strftime("%H:%M")
            log(f"[{wake_at}] Sleeping {sleep_min}m — next check at {next_at}")
            time.sleep(sleep_min * 60)
    except KeyboardInterrupt:
        log("Watch mode stopped.")


def determine_schedule() -> str:
    """Determine which schedule to run based on current day/time."""
    now = datetime.now()
    day = now.strftime("%A").lower()
    hour = now.hour

    if day == "monday":
        return "monday"
    elif day == "tuesday":
        if hour < 12:
            return "tuesday-morning"
        else:
            return "tuesday-evening"
    elif day == "wednesday":
        if hour < 12:
            return "wednesday-morning"
        else:
            return "wednesday-evening"
    elif day in ["thursday", "friday", "saturday"]:
        return "live"
    elif day == "sunday":
        if hour >= 22:
            return "record"
        elif hour >= 21:
            return "post-tournament"
        else:
            return "live"

    return "none"


def main():
    parser = argparse.ArgumentParser(description="Scheduled data refresh")
    parser.add_argument("--schedule", choices=[
        "monday", "tuesday-morning", "tuesday-evening",
        "wednesday-morning", "wednesday-evening",
        "live", "record", "post-tournament", "auto"
    ], default="auto", help="Which schedule to run (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously refresh live data while a round is in progress")
    parser.add_argument("--interval", type=int, default=10,
                        help="Minutes between refreshes in --watch mode (default: 10)")
    args = parser.parse_args()

    # Watch mode: run indefinitely, refreshing during active rounds
    if args.watch:
        watch_loop(interval_minutes=args.interval, dry_run=args.dry_run)
        return

    # Determine schedule
    if args.schedule == "auto":
        schedule = determine_schedule()
        log(f"Auto-detected schedule: {schedule}")
    else:
        schedule = args.schedule

    log(f"Running schedule: {schedule}")

    # Run appropriate schedule
    if schedule == "monday":
        results = run_monday_refresh(args.dry_run)
    elif schedule == "tuesday-morning":
        results = run_tuesday_morning(args.dry_run)
    elif schedule == "tuesday-evening":
        results = run_tuesday_evening(args.dry_run)
    elif schedule == "wednesday-morning":
        results = run_wednesday_morning(args.dry_run)
    elif schedule == "wednesday-evening":
        results = run_tuesday_evening(args.dry_run)  # Same as Tuesday evening
    elif schedule == "live":
        results = run_live_refresh(args.dry_run)
    elif schedule == "record":
        results = run_record_results(args.dry_run)
    elif schedule == "post-tournament":
        results = run_post_tournament_refresh(args.dry_run)
    else:
        log("No schedule to run.")
        return

    # Summary
    log("")
    log("=" * 60)
    log("SUMMARY")
    log("=" * 60)

    success_count = sum(1 for _, s in results if s)
    total_count = len(results)

    for desc, success in results:
        status = "✓" if success else "✗"
        log(f"  {status} {desc}")

    log(f"\nCompleted: {success_count}/{total_count} tasks")

    # Save run log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "schedule": schedule,
        "dry_run": args.dry_run,
        "results": [{"task": d, "success": s} for d, s in results],
        "success_count": success_count,
        "total_count": total_count
    }

    log_file = LOGS_DIR / "scheduler_history.json"
    history = []
    if log_file.exists():
        try:
            history = json.loads(log_file.read_text())
        except:
            history = []

    history.append(log_entry)
    # Keep last 100 runs
    history = history[-100:]
    log_file.write_text(json.dumps(history, indent=2))


if __name__ == "__main__":
    main()
