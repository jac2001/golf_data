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
import re
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
    "DG Approach Skill": 60,
    "DG Skill Ratings": 60,
    "DG Decompositions": 60,
    "Predictions": 900,
    "Refresh Odds": 120,
    "Recommend Bets": 120,
    "Past Results": 120,
    "Form Stats": 900,
    # Post-tournament model refresh
    "Calibration Refresh": 120,
    "Training Data Merge": 1800,
    "Model Retrain": 3600,
    "SHAP Values": 300,
    "Player Explanations": 120,
}

RETRAIN_LOG = LOGS_DIR / "retrain_log.json"
TOURNAMENTS_PER_RETRAIN = 4


def _load_retrain_log() -> dict:
    """Read the retrain tracking log; return defaults if missing/corrupt."""
    if RETRAIN_LOG.exists():
        try:
            return json.loads(RETRAIN_LOG.read_text())
        except Exception:
            pass
    return {"last_retrain_tid": None, "tournaments_since_retrain": 0, "last_retrain_at": None}


def _update_retrain_log(tid: str, did_retrain: bool):
    """Increment the tournament counter; reset it (and record timestamp) when we retrain."""
    data = _load_retrain_log()
    if did_retrain:
        data["last_retrain_tid"] = tid
        data["tournaments_since_retrain"] = 0
        data["last_retrain_at"] = datetime.now().isoformat()
    else:
        data["tournaments_since_retrain"] = data.get("tournaments_since_retrain", 0) + 1
    RETRAIN_LOG.write_text(json.dumps(data, indent=2))


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


def deploy_site(reason: str, dry_run: bool = False) -> bool:
    """Commit refreshed data/outputs and push so Render redeploys the live site.

    Only stages data/ and outputs/ — never source code. No-op when nothing
    changed. Never raises: a git failure must not sink the pipeline.
    """
    log("-" * 40)
    log(f"Deploy Site ({reason})")

    if dry_run:
        log("[DRY RUN] Would commit data/ + outputs/ and push to origin main")
        return True

    def _git(*args, timeout=120):
        return subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            capture_output=True, text=True, timeout=timeout,
        )

    try:
        # Bail if a rebase/merge is mid-flight or we're not on main
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != "main":
            log(f"  [warn] On branch '{branch}', not main — skipping deploy")
            return False

        _git("add", "data/", "outputs/")

        staged = _git("diff", "--cached", "--quiet")
        if staged.returncode == 0:
            log("  No data changes to deploy")
            return True

        msg = f"Auto-deploy: {reason} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        commit = _git("commit", "-m", msg)
        if commit.returncode != 0:
            log(f"  [warn] Commit failed: {commit.stderr[:200]}")
            return False

        push = _git("push", "origin", "main", timeout=300)
        if push.returncode != 0:
            log(f"  [warn] Push failed: {push.stderr[:200]}")
            return False

        log("  ✓ Pushed — Render redeploy triggered")
        return True
    except Exception as e:
        log(f"  [warn] Deploy failed: {e}")
        return False


def run_parallel(tasks: list[tuple[str, list]], default_timeout: int = 120) -> list[tuple[str, bool]]:
    """Run a list of (description, cmd) tasks simultaneously and return results.

    Each task spawns its own subprocess. All run at once; we wait for the slowest.
    Safe to use when tasks hit different APIs or do independent computation.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _run_one(desc_cmd):
        desc, cmd = desc_cmd
        timeout = step_timeout(desc, default_timeout)
        log(f"  [parallel] Starting: {desc}")
        try:
            result = subprocess.run(
                cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                log(f"  [parallel] ✓ {desc}")
                return desc, True
            else:
                log(f"  [parallel] ✗ {desc}: {result.stderr[:150] if result.stderr else 'failed'}")
                return desc, False
        except subprocess.TimeoutExpired:
            log(f"  [parallel] ✗ {desc}: timeout after {timeout}s")
            return desc, False
        except Exception as e:
            log(f"  [parallel] ✗ {desc}: {e}")
            return desc, False

    results = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = {pool.submit(_run_one, t): t[0] for t in tasks}
        for fut in as_completed(futures):
            results.append(fut.result())
    return results


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

    # <= so the Sunday-night run sees the tournament that ended TODAY —
    # strict < resolved last week's event and delayed settlement to Monday.
    # If the event isn't actually finished (rain delay), is_tournament_official()
    # returns False and the run retries later, which is the correct behavior.
    past = df[df["end_dt"] <= today].sort_values("end_dt", ascending=False)
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
        ("League Picks", ["python3", "scripts/scrapers/fetch_league_picks.py"]),
        ("Fantasy Scorecard", ["python3", "scripts/scrapers/fetch_fantasy_scorecard.py"]),
        # DataGolf field: tries upcoming_pga first (earlier data), falls back to pga
        ("Field", ["python3", "scripts/scrapers/fetch_dg_field.py",
                   "--tournament-id", tournament_id, "--tour", "auto"]),
        # WD check runs immediately after field fetch so pre-tournament withdrawals
        # are removed from the field CSV before predictions are generated.
        ("WD Check", ["python3", "scripts/scrapers/fetch_withdrawals.py",
                      "--tournament-id", tournament_id, "--auto-update-field"]),
        ("Course Info", ["python3", "scripts/scrapers/fetch_course_characteristics.py",
                         "--tournament-id", tournament_id, "--profile"]),
        ("Power Rankings", ["python3", "scripts/scrapers/fetch_power_rankings.py",
                            "--slug", power_slug or tournament_name.lower().replace(" ", "-"), "--allow-fail"]),
        ("Betting Profiles", ["python3", "scripts/scrapers/fetch_betting_profiles.py",
                              "--tournament-id", tournament_id, "--field", field_path]),
        ("DG Approach Skill", ["python3", "scripts/scrapers/fetch_dg_approach_skill.py",
                               "--period", "l24"]),
        ("DG Skill Ratings", ["python3", "scripts/scrapers/fetch_dg_skill_ratings.py"]),
        ("DG Decompositions", ["python3", "scripts/scrapers/fetch_dg_decompositions.py",
                               "--tournament-id", tournament_id]),
        ("DG Pre-Tournament", ["python3", "scripts/scrapers/fetch_dg_pre_tournament.py",
                               "--tournament-id", tournament_id]),
        ("Predictions", ["python3", "scripts/run_pipeline.py",
                         "--tournament", tournament_name,
                         "--pga-id", tournament_id,
                         "--field", field_path,
                         "--use-schedule",
                         "--skip-refresh", "--calibrate", "--lineup"]),
        # Re-run DG field after predictions to merge dg_id/dg_rank into predictions CSV
        ("DG Field Merge", ["python3", "scripts/scrapers/fetch_dg_field.py",
                             "--tournament-id", tournament_id, "--tour", "auto",
                             "--merge-predictions"]),
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

    # Fetch extended hourly forecast for draw advantage
    if not dry_run and tournament_id and tournament_name:
        _coords = _find_course_coords(tournament_name)
        if _coords:
            _lat, _lon = _coords
            run_command(
                ["python3", "scripts/scrapers/fetch_weather_openmetro.py",
                 "--lat", str(_lat), "--lon", str(_lon),
                 "--tid", tournament_id, "--hourly"],
                "Hourly Weather Forecast",
                timeout=30,
            )

    # Fetch tee times + compute draw advantage for R1 and R2 (draw announced Mon/Tue)
    if not dry_run and tournament_id:
        for _rnd in [1, 2]:
            _tt_ok = run_command(
                ["python3", "scripts/scrapers/fetch_tee_times.py",
                 "--tid", tournament_id, "--round", str(_rnd)],
                f"Tee Times R{_rnd}",
                timeout=30,
            )
            if _tt_ok:
                run_command(
                    ["python3", "scripts/predictions/draw_advantage.py",
                     "--tid", tournament_id, "--round", str(_rnd)],
                    f"Draw Advantage R{_rnd}",
                    timeout=30,
                )

    return results


def run_tuesday_evening(dry_run: bool = False):
    """Odds refresh + DG pre-tournament check + predictions re-run."""
    log("=" * 60)
    log("TUESDAY EVENING - Odds + DG Pre-Tournament Refresh")
    log("=" * 60)

    tournament = get_current_tournament()
    if not tournament:
        log("No tournament found!")
        return []

    tournament_id = str(tournament.get("tournament_id", ""))
    tournament_name = str(tournament.get("tournament_name", ""))
    if not tournament_id:
        log("No tournament ID!")
        return []

    tasks = [
        ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                             "--tournament-id", tournament_id,
                             "--max-age-hours", "2",
                             "--fetch-profile", "fast",
                             "--no-snapshot"]),
        # DG publishes pre-tournament predictions Tue/Wed evening — fetch and re-run
        ("DG Pre-Tournament", ["python3", "scripts/scrapers/fetch_dg_pre_tournament.py",
                                "--tournament-id", tournament_id]),
        # DG betting odds: win/top10/top20/make_cut + round matchups across all books
        ("DG Betting Odds", ["python3", "scripts/scrapers/fetch_dg_odds.py",
                              "--tournament-id", tournament_id, "--market", "all"]),
        ("Predictions", ["python3", "scripts/run_pipeline.py",
                         "--tournament", tournament_name,
                         "--pga-id", tournament_id,
                         "--field", f"data/fields/field_{tournament_id}.csv",
                         "--use-schedule",
                         "--skip-refresh", "--calibrate", "--lineup"]),
        # Score bets after predictions are updated, using fresh DG odds.
        # Lower thresholds so the dashboard slider can filter — saves more candidates.
        ("Recommend Bets", ["python3", "scripts/models/recommend_bets.py",
                             "--tournament-id", tournament_id,
                             "--min-edge", "0.75", "--min-confidence", "0.45",
                             "--max-per-market", "15", "--top-n", "40"]),
        # Generate best bet card + send email notification.
        ("Best Bet Notification", ["python3", "scripts/notifications/send_best_bet.py",
                                    "--tournament-id", tournament_id,
                                    "--send-email"]),
        # Check tracked bets + fantasy picks for status changes; push + email if anything flipped.
        ("Bet Alerts", ["python3", "scripts/notifications/check_bet_alerts.py"]),
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


def run_pretournament_validation(tid: str, tournament_name: str) -> None:
    """
    Check that all required data is in place before a tournament starts.
    Writes a validation report to logs/pretournament_validation_{tid}.txt.
    """
    from datetime import timedelta
    now = datetime.now()
    stale_threshold = now - timedelta(hours=36)
    lines = []
    warnings = []

    lines.append("=" * 60)
    lines.append(f"PRE-TOURNAMENT VALIDATION — {tournament_name} ({tid})")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")

    def _check(label, path, min_rows=None, warn_if_missing=True):
        p = Path(path)
        if not p.exists():
            if warn_if_missing:
                warnings.append(f"{label}: file not found ({p.name})")
            lines.append(f"  [{'WARN' if warn_if_missing else 'INFO'}] {label:<30} MISSING")
            return
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        age_h = int((now - mtime).total_seconds() // 3600)
        stale = mtime < stale_threshold
        if stale:
            warnings.append(f"{label}: stale ({age_h}h old)")
        detail = ""
        if min_rows is not None:
            try:
                nrows = sum(1 for _ in open(p)) - 1  # fast row count
                detail = f"{nrows} rows  "
                if nrows < min_rows:
                    warnings.append(f"{label}: only {nrows} rows (expected {min_rows}+)")
            except Exception:
                detail = "unreadable  "
        flag = "WARN" if stale else "OK  "
        lines.append(f"  [{flag}] {label:<30} {detail}({age_h}h ago)")

    _check("Field players", DATA_DIR / "fields" / f"field_{tid}.csv", min_rows=50)

    # Predictions: check file + tournament_id match
    pred_path = PROJECT_ROOT / "outputs" / "latest_predictions.csv"
    if pred_path.exists():
        try:
            mtime = datetime.fromtimestamp(pred_path.stat().st_mtime)
            age_h = int((now - mtime).total_seconds() // 3600)
            stale = mtime < stale_threshold
            with open(pred_path) as f:
                header = f.readline()
                first = f.readline()
            cols = header.strip().split(",")
            vals = first.strip().split(",")
            row = dict(zip(cols, vals))
            pred_tid = row.get("tournament_id", "unknown")
            nrows = sum(1 for _ in open(pred_path)) - 1
            tid_match = pred_tid == tid
            flag = "WARN" if (stale or not tid_match) else "OK  "
            if not tid_match:
                warnings.append(f"Predictions: tid={pred_tid}, expected {tid}")
            if stale:
                warnings.append(f"Predictions: stale ({age_h}h old)")
            lines.append(f"  [{flag}] {'Predictions':<30} {nrows} rows, tid={pred_tid}  ({age_h}h ago)")
        except Exception as e:
            warnings.append(f"Predictions: unreadable ({e})")
            lines.append(f"  [WARN] {'Predictions':<30} unreadable")
    else:
        warnings.append("Predictions: latest_predictions.csv not found")
        lines.append(f"  [WARN] {'Predictions':<30} MISSING")

    _check("Odds (multi-book)", DATA_DIR / "odds" / "multi_book_odds_latest.csv", min_rows=30)
    _check("Expert picks", DATA_DIR / "expert_picks" / f"expert_picks_{tid}.csv",
           min_rows=5, warn_if_missing=False)
    _check("Betting profiles", DATA_DIR / "odds" / f"betting_profiles_{tid}.csv",
           min_rows=10, warn_if_missing=False)

    lines.append("")
    if warnings:
        lines.append(f"WARNINGS ({len(warnings)})")
        lines.append("-" * 40)
        for w in warnings:
            lines.append(f"  ! {w}")
    else:
        lines.append("All checks passed — ready for tournament.")
    lines.append("")

    out_path = LOGS_DIR / f"pretournament_validation_{tid}.txt"
    out_path.write_text("\n".join(lines))
    log(f"  Validation report → {out_path.name}")
    if warnings:
        log(f"  WARNINGS: {len(warnings)} issue(s) — check {out_path.name}")
    else:
        log("  Validation: all checks passed.")


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
        # WD check first — catches any overnight withdrawals before predictions rerun
        ("WD Check", ["python3", "scripts/scrapers/fetch_withdrawals.py",
                      "--tournament-id", tournament_id, "--auto-update-field"]),
        ("Expert Picks", ["python3", "scripts/scrapers/fetch_expert_picks_pga.py",
                          "--tournament-id", tournament_id]),
        ("Predictions", ["python3", "scripts/run_pipeline.py",
                         "--tournament", tournament_name,
                         "--pga-id", tournament_id,
                         "--field", f"data/fields/field_{tournament_id}.csv",
                         "--use-schedule",
                         "--skip-refresh", "--calibrate", "--lineup"]),
        ("Recommend Bets", ["python3", "scripts/models/recommend_bets.py",
                             "--tournament-id", tournament_id,
                             "--min-edge", "0.75", "--min-confidence", "0.45",
                             "--max-per-market", "15", "--top-n", "40"]),
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

    if not dry_run:
        run_pretournament_validation(tournament_id, tournament_name)

    return results


def run_live_refresh(dry_run: bool = False):
    """Live tournament updates — runs in three parallel tiers.

    Tier 1 (all independent fetches run simultaneously):
        Leaderboard, Hole Scores, DG Live Stats (all rounds), DG Betting Odds,
        DraftKings Odds, League Picks, Live Course Stats

    Tier 2 (depends on Tier 1 data):
        Refresh Odds (needs fresh leaderboard + DG odds)
        Live Prediction Update (needs fresh leaderboard)

    Tier 3 (depends on Tier 2 data):
        Recommend Bets, Live Bet Recommendations

    Sequential total was ~8 min; parallel tiers target ~2-3 min.
    """
    log("=" * 60)
    log("LIVE REFRESH - Tournament Updates (parallel)")
    log("=" * 60)

    tournament = get_current_tournament()
    tournament_id = str(tournament.get("tournament_id", "")) if tournament else ""

    results = []

    # ── Tier 1: independent fetches ───────────────────────────────────────────
    tier1 = [
        ("Live Leaderboard", ["python3", "scripts/scrapers/fetch_live_leaderboard.py"]),
        ("League Picks",     ["python3", "scripts/scrapers/fetch_league_picks.py"]),
    ]

    if tournament_id:
        tier1.append(("Hole Scores", ["python3", "scripts/scrapers/fetch_hole_scores.py",
                                      "--tournament-id", tournament_id]))
        tier1.append(("DG Live Stats", ["python3", "scripts/scrapers/fetch_dg_live_stats.py",
                                        "--tournament-id", tournament_id]))
        tier1.append(("Live Course Stats", ["python3", "scripts/scrapers/fetch_course_stats.py",
                                            "--tid", tournament_id]))
        tier1.append(("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                          "--tournament-id", tournament_id,
                                          "--max-age-hours", "0.5",
                                          "--fetch-profile", "fast",
                                          "--no-snapshot"]))
        tier1.append(("DG Betting Odds", ["python3", "scripts/scrapers/fetch_dg_odds.py",
                                          "--tournament-id", tournament_id, "--market", "all"]))

        # Per-round DG stats (one task per completed/active round)
        _meta_path = DATA_DIR / "live" / f"leaderboard_{tournament_id.lower()}_meta.json"
        _current_round = 1
        if _meta_path.exists():
            try:
                with open(_meta_path) as _f:
                    _current_round = int(json.load(_f).get("current_round") or 1)
            except Exception:
                pass
        for _rnd in range(1, _current_round + 1):
            tier1.append((f"DG Live Stats R{_rnd}", [
                "python3", "scripts/scrapers/fetch_dg_live_stats.py",
                "--tournament-id", tournament_id, "--round", str(_rnd),
            ]))

    log(f"Tier 1: launching {len(tier1)} fetches in parallel")
    if dry_run:
        results += [(desc, True) for desc, _ in tier1]
    else:
        results += run_parallel(tier1)

    # ── Tier 2: needs fresh leaderboard + odds ────────────────────────────────
    if tournament_id:
        tier2 = [
            ("Refresh Odds", ["python3", "scripts/predictions/refresh_odds.py",
                               "--tournament-id", tournament_id]),
            ("Live Prediction Update", ["python3", "scripts/predictions/live_update_predictions.py",
                                        "--tournament_id", tournament_id]),
        ]
        log(f"Tier 2: launching {len(tier2)} tasks in parallel")
        if dry_run:
            results += [(desc, True) for desc, _ in tier2]
        else:
            results += run_parallel(tier2)

        # ── Tier 3: needs updated predictions + odds ──────────────────────────
        tier3 = [
            ("Recommend Bets", ["python3", "scripts/models/recommend_bets.py",
                                 "--tournament-id", tournament_id,
                                 "--min-edge", "0.75", "--min-confidence", "0.45",
                                 "--max-per-market", "15", "--top-n", "40"]),
            ("Live Bet Recommendations", ["python3", "scripts/predictions/generate_live_bets.py",
                                          "--tid", tournament_id]),
        ]
        log(f"Tier 3: launching {len(tier3)} tasks in parallel")
        if dry_run:
            results += [(desc, True) for desc, _ in tier3]
        else:
            results += run_parallel(tier3)

    # ── Daily intel refresh (player news + trends) ───────────────────────────
    # Runs at most once per day — skipped if the file is <24h old.
    # Uses Claude web_search (~$1/run for 20 players) so we gate it carefully.
    if not dry_run and tournament_id:
        import time as _time_mod
        _intel_path = DATA_DIR / "intel" / f"tournament_intel_{tournament_id}.json"
        _intel_age_hours = 999.0
        if _intel_path.exists():
            _intel_age_hours = (_time_mod.time() - _intel_path.stat().st_mtime) / 3600
        if _intel_age_hours > 24:
            _tournament_name = str(tournament.get("tournament_name", "")) if tournament else ""
            _course_name = _tournament_name  # fallback; schedule may have course field
            try:
                import pandas as _pd
                _sched = _pd.read_csv(DATA_DIR / "raw" / f"schedule_{datetime.now().year}.csv", dtype=str)
                _row = _sched[_sched["tournament_id"].str.upper() == tournament_id.upper()]
                if not _row.empty and "course_name" in _sched.columns:
                    _course_name = str(_row["course_name"].iloc[0])
            except Exception:
                pass
            log(f"Intel refresh: file is {_intel_age_hours:.0f}h old — re-running")
            run_command(
                ["python3", "scripts/intel/fetch_tournament_intel.py",
                 "--tid", tournament_id,
                 "--tournament", _tournament_name,
                 "--course", _course_name],
                "Intel Refresh",
                timeout=300,
            )

    # ── Tee times + draw advantage for R3/R4 ─────────────────────────────────
    # R1/R2 tee times are fetched on Tuesday morning (run_tuesday_morning).
    # R3/R4 pairings are announced Friday evening after the cut — we fetch them
    # during the Saturday/Sunday 8am live refresh so they're ready before betting.
    # Draw advantage is recomputed each morning with the latest weather forecast.
    if not dry_run and tournament_id:
        now = datetime.now()
        day = now.strftime("%A").lower()
        hour = now.hour

        # Map day → round that starts today
        _round_for_day = {"thursday": 1, "friday": 2, "saturday": 3, "sunday": 4}
        todays_round = _round_for_day.get(day)

        if todays_round and hour < 14:  # morning refreshes only (8am run)
            log(f"Fetching tee times + draw advantage for R{todays_round} ({day})")
            _tt_ok = run_command(
                ["python3", "scripts/scrapers/fetch_tee_times.py",
                 "--tid", tournament_id, "--round", str(todays_round)],
                f"Tee Times R{todays_round}",
                timeout=30,
            )
            if _tt_ok:
                run_command(
                    ["python3", "scripts/predictions/draw_advantage.py",
                     "--tid", tournament_id, "--round", str(todays_round)],
                    f"Draw Advantage R{todays_round}",
                    timeout=30,
                )

    # Save once-per-live-run weather snapshot
    if not dry_run and tournament_id and tournament:
        tournament_name = str(tournament.get("tournament_name", ""))
        save_weather_snapshot(tournament_id, tournament_name)

    # ── Sync live data to DuckDB ──────────────────────────────────────────────
    if not dry_run and tournament_id:
        db_counts = sync_live_data_to_db(tournament_id)
        log(f"[DB] live_stats={db_counts['live_stats']} rows  live_leaderboard={db_counts['live_leaderboard']} rows")

    # ── Sync to Supabase ──────────────────────────────────────────────────────
    if not dry_run and tournament_id:
        try:
            from scripts.database.supabase_sync import sync_leaderboard, sync_predictions, sync_bets
            sync_leaderboard(tournament_id)
            sync_predictions(tournament_id)
            sync_bets(tournament_id)
        except Exception as e:
            log(f"[Supabase] sync failed (non-fatal): {e}")

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


def run_monday_noon_check(dry_run: bool = False):
    """
    Monday noon safety net for tournaments that finish late (weather delays, playoffs).
    Runs record + post-tournament if the last tournament completed but the sentinel
    hasn't been written yet (i.e. the 8am post-tournament run was too early).
    Does nothing if the post-tournament pipeline already ran successfully.
    """
    tournament = get_last_tournament()
    if not tournament:
        log("Monday noon check: no recent tournament found.")
        return []

    tid = str(tournament.get("tournament_id", ""))
    name = str(tournament.get("tournament_name", ""))
    sentinel = LOGS_DIR / f"post_tournament_{tid}.done"

    if sentinel.exists():
        log(f"Monday noon check: {name} ({tid}) already processed — nothing to do.")
        return []

    log(f"Monday noon check: {name} ({tid}) sentinel missing — running record + post-tournament.")
    results = run_record_results(dry_run)
    results += run_post_tournament_refresh(dry_run)
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


def sync_live_data_to_db(tid: str) -> dict:
    """Upsert live stats + live leaderboard CSVs into DuckDB after each refresh.

    Returns a dict with counts: {live_stats: N, live_leaderboard: N}.
    Safe to call every refresh cycle — uses DELETE+INSERT per tournament.
    """
    counts = {"live_stats": 0, "live_leaderboard": 0}
    try:
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
        from db import get_conn

        # ── Live SG stats ─────────────────────────────────────────────────────
        stats_path = DATA_DIR / "datagolf" / f"dg_live_stats_{tid}_latest.csv"
        if stats_path.exists():
            df = pd.read_csv(stats_path)
            if not df.empty:
                df["tournament_id"] = tid
                # event_avg stored as round_num=0; actual rounds as 1-4
                if "round_param" in df.columns:
                    df["round_num"] = df["round_param"].map({"event_avg": 0}).fillna(
                        pd.to_numeric(df["round_param"], errors="coerce")
                    ).fillna(0).astype(int)
                else:
                    df["round_num"] = pd.to_numeric(df.get("round", 0), errors="coerce").fillna(0).astype(int)
                df["thru"] = pd.to_numeric(df["thru"], errors="coerce")
                df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0).astype(int)
                for col in ["sg_ott","sg_app","sg_arg","sg_putt","sg_t2g","sg_total","driving_dist","driving_acc"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df["dg_id"] = df["dg_id"].astype(str) if "dg_id" in df.columns else ""

                with get_conn() as conn:
                    conn.register("_live_stats_view", df)
                    conn.execute(f"DELETE FROM live_stats WHERE tournament_id = '{tid}'")
                    conn.execute("""
                        INSERT INTO live_stats
                            (tournament_id, player_name, dg_id, round_num, position, total, thru,
                             sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, sg_total,
                             driving_dist, driving_acc, event_name, last_updated, fetched_at)
                        SELECT tournament_id, player_name, dg_id, round_num, position, total, thru,
                               sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, sg_total,
                               driving_dist, driving_acc, event_name, last_updated, fetched_at
                        FROM _live_stats_view
                    """)
                    counts["live_stats"] = len(df)

        # ── Live leaderboard ──────────────────────────────────────────────────
        lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
        if lb_path.exists():
            lb = pd.read_csv(lb_path)
            if not lb.empty:
                lb["tournament_id"] = tid
                lb["fetched_at"] = pd.Timestamp.utcnow().isoformat()
                lb["total_numeric"] = pd.to_numeric(lb.get("total_numeric", 0), errors="coerce").fillna(0).astype(int)
                lb["current_round"] = pd.to_numeric(lb.get("current_round", 1), errors="coerce").fillna(1).astype(int)
                for col in ["R1","R2","R3","R4","position_change"]:
                    if col in lb.columns:
                        lb[col] = pd.to_numeric(lb[col], errors="coerce")
                lb["made_cut"] = lb.get("made_cut", True).fillna(True).astype(bool) if "made_cut" in lb.columns else True
                lb["thru"] = lb["thru"].astype(str) if "thru" in lb.columns else ""

                with get_conn() as conn:
                    conn.register("_lb_view", lb)
                    conn.execute(f"DELETE FROM live_leaderboard WHERE tournament_id = '{tid}'")
                    conn.execute("""
                        INSERT INTO live_leaderboard
                            (tournament_id, player_name, position, total_numeric, thru,
                             current_round, r1, r2, r3, r4, made_cut, fetched_at)
                        SELECT tournament_id, player_name, position, total_numeric, thru,
                               current_round,
                               CAST(R1 AS DOUBLE), CAST(R2 AS DOUBLE),
                               CAST(R3 AS DOUBLE), CAST(R4 AS DOUBLE),
                               made_cut, fetched_at
                        FROM _lb_view
                    """)
                    counts["live_leaderboard"] = len(lb)

    except Exception as e:
        log(f"  [DB] live data sync failed: {e}")

    return counts


def is_tournament_official(tid: str) -> bool:
    """Return True if the tournament is fully official: R4 (or later) is complete.

    Guards against the R3-official false-positive: after R3 finishes, the API sets
    round_status='Official' for that round. We must also confirm current_round >= 4
    so the sentinel never fires mid-tournament.

    Fallback: if the API never sends 'official' (returns 'R4' instead), check the
    leaderboard CSV directly — all players showing status='complete' and thru='F'
    means the round is done regardless of the meta status string.
    """
    meta = DATA_DIR / "live" / f"leaderboard_{tid.lower()}_meta.json"
    if not meta.exists():
        return False
    with open(meta) as f:
        data = json.load(f)

    round_ok = int(data.get("current_round", 0)) >= 4
    if not round_ok:
        return False

    status = str(data.get("round_status", "")).lower()
    if "official" in status:
        return True

    # Fallback: API sometimes returns "R4" instead of "Official" after the round ends.
    # If every player in the leaderboard CSV is marked complete and finished, trust that.
    live_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
    if live_path.exists():
        try:
            lb = pd.read_csv(live_path)
            if len(lb) > 0 and "status" in lb.columns and "thru" in lb.columns:
                # WD/DQ/cut are terminal — a withdrawal must not hold the
                # tournament "unofficial" forever. Official = nobody is still
                # playing: every player is either finished (complete + thru=F)
                # or out of the event entirely.
                status = lb["status"].astype(str).str.lower()
                done_playing = (status == "complete") & (lb["thru"].astype(str) == "F")
                out_of_event = status.isin(["withdrawn", "disqualified", "cut", "wd", "dq"])
                if "position" in lb.columns:
                    out_of_event |= lb["position"].astype(str).str.upper() == "CUT"
                if (done_playing | out_of_event).all() and done_playing.any():
                    return True
        except Exception:
            pass

    return False


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



def write_post_tournament_summary(tid: str, name: str, results: list) -> None:
    """Write a human-readable post-tournament summary to logs/post_tournament_{tid}.txt."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"POST-TOURNAMENT SUMMARY — {name} ({tid})")                                                        
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)                                                                                           
    lines.append("")                                                                                                 

    # Pipeline status                                                                                                
    lines.append("PIPELINE STATUS")                       
    lines.append("-" * 40)
    for desc, success in results:
        lines.append(f"  [{'OK  ' if success else 'FAIL'}] {desc}")
    failed = [d for d, s in results if not s]                                                                        
    lines.append(f"\n  {len(results) - len(failed)}/{len(results)} tasks passed")
    if failed:                                                                                                       
        lines.append(f"  FAILED: {', '.join(failed)}")    
    lines.append("") 
    
      
    # Bet P&L 
    lines.append('BET RESULTS')
    lines.append("-" * 40)                                                                                           
    try:                                                  
        results_csv = DATA_DIR / "odds" / "recommended_bets_results.csv"
        if results_csv.exists():                                                                                     
            bets = pd.read_csv(results_csv)
            week = bets[bets["tournament_id"] == tid].copy()
            # Support both column naming conventions
            outcome_col = "outcome" if "outcome" in week.columns else "outcome_status"
            pnl_col = "pnl" if "pnl" in week.columns else ("pnl_per_1" if "pnl_per_1" in week.columns else None)
            graded = week[~week[outcome_col].astype(str).isin(["", "nan", "pending"])]
            wins = (graded[outcome_col] == "won").sum()
            pushes = (graded[outcome_col] == "push").sum()
            total = len(graded)
            pnl = graded[pnl_col].sum() if pnl_col else 0.0
            roi = (pnl / total * 100) if total > 0 else 0.0
            lines.append(f"  Graded: {total}  Wins: {wins}  Pushes: {pushes}  Losses: {total - wins - pushes}")
            lines.append(f"  Win rate: {wins/total*100:.1f}%  |  P&L: {pnl:+.2f} units  |  ROI: {roi:+.1f}%")
            if "market" in graded.columns and not graded.empty:
                lines.append("  By market:")
                for mkt, g in graded.groupby("market"):
                    mkt_pnl = g[pnl_col].sum() if pnl_col else 0.0
                    lines.append(
                        f"    {mkt:<22} {len(g):>2} bets  "
                        f"{(g[outcome_col]=='won').sum()} wins  P&L {mkt_pnl:+.2f}"
                    )
            else:
                lines.append("  No market breakdown available.")
    except Exception as e:
        lines.append(f" Error summarizing bet results: {e}")
            
    lines.append("")
    # Top 10 leaderboard — prefer live CSV (authoritative for recent tournaments)
    lines.append("LEADERBOARD (Top 10)")
    lines.append("-" * 40)
    try:
        year = int(str(tid)[1:5])
        live_lb_path = DATA_DIR / "live" / f"leaderboard_{tid.lower()}.csv"
        hist_path = DATA_DIR / "historical" / f"leaderboards_{year}.csv"
        if live_lb_path.exists():
            tid_rows = pd.read_csv(live_lb_path)
            tid_rows = tid_rows.rename(columns={"total_numeric": "to_par"})
        elif hist_path.exists():
            lb = pd.read_csv(hist_path)
            tid_rows = lb[lb["tournament_id"] == tid].copy()
        else:
            tid_rows = pd.DataFrame()
        if not tid_rows.empty:
            finishers = tid_rows[~tid_rows["position"].astype(str).isin(["CUT", "WD", "DQ", "MC"])].copy()
            finishers["_tp"] = pd.to_numeric(finishers["to_par"], errors="coerce")
            for _, row in finishers.sort_values("_tp").head(10).iterrows():
                tp = row.get("to_par", "")
                try:
                    tp_str = f"{int(float(tp)):+d}"
                except (ValueError, TypeError):
                    tp_str = str(tp)
                lines.append(f"  {str(row['position']):<6} {str(row['player_name']):<26} {tp_str}")
        else:
            lines.append("  No leaderboard file found.")
    except Exception as e:
        lines.append(f"  [Error loading leaderboard: {e}]")
    lines.append("")                                                                                                 
                                                        
    out_path = LOGS_DIR / f"post_tournament_summary_{tid}.txt"                                                       
    out_path.write_text("\n".join(lines))
    log(f"  Summary written → {out_path.name}")
        





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

    # Step 3: fetch canonical past-results from PGA Tour (earnings, FedEx points).
    # Runs BEFORE the live-leaderboard append so that the live CSV always wins
    # if the official page is stale (e.g. serving prior-year data for a major).
    # The validation guard in fetch_past_results.py will skip the write if the
    # scraped winner doesn't match the live leaderboard winner.
    if dry_run:
        log(f"[DRY RUN] Would run: Past Results")
    else:
        run_command(
            ["python3", "scripts/scrapers/fetch_past_results.py",
             "--tournament-id", tid, "--year", str(year)],
            "Past Results",
            timeout=step_timeout("Past Results", 120),
        )

    # Step 4+5: append live leaderboard to historical + write sentinel (idempotent).
    # Runs AFTER fetch_past_results so the live CSV is always the final word on
    # positions/scores for the current tournament.
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

    # DG historical sync — runs before form stats so that round_stats,
    # tournament_stats, and leaderboard rows are all updated from DG's
    # finalized data (driving dist/acc, GIR, scrambling, real sg_arg, etc.)
    # before anything downstream reads those tables.
    m = re.match(r"R(\d{4})(\d+)$", tid.upper())
    if m:
        dg_event_id = str(int(m.group(2)))  # strip leading zeros e.g. "034" → "34"
        dg_cmd = [
            "python3", "scripts/scrapers/fetch_dg_historical_results.py",
            "--year", str(year), "--event-id", dg_event_id,
        ]
        if dry_run:
            log(f"[DRY RUN] Would run: DG Historical Sync ({tid})")
        else:
            run_command(dg_cmd, f"DG Historical Sync ({tid})", timeout=180)

    # Steps 6-10: remaining scrapers (idempotent by design)
    tasks = [
        ("Tournament SG Stats", ["python3", "scripts/scrapers/fetch_tournament_stats.py",
                                  "--year", str(year), "--refresh-latest", "3"]),
        ("Form Stats", ["python3", "scripts/scrapers/fetch_form_stats.py", "--year", str(year)]),
        ("World Rankings", ["python3", "scripts/scrapers/fetch_world_rankings.py"]),
        ("Record Results", ["python3", "scripts/planning/auto_record_results.py"]),
        ("Fantasy League Usage", ["python3", "scripts/scrapers/fetch_fantasy_usage.py"]),
        ("Backfill Prediction Results", ["python3", "scripts/predictions/backfill_results.py"]),
        ("Grade Bets", ["python3", "scripts/models/grade_recommended_bets.py"]),
        ("Fantasy Tracker", ["python3", "scripts/post_tournament.py",
                              "--tournament-id", tid, "--step", "tracker"]),
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

    # Step 12: Assistant context file
    # Now that bet grading + backfill are done, regenerate the season-level
    # summary that feeds the chatbot (and any external LLM). It covers:
    # recent results, pick accuracy, bet ROI, CLV, and top SHAP features.
    log("-" * 40)
    log("Assistant Context")
    ctx_cmd = ["python3", "scripts/chat/build_assistant_context.py"]
    if dry_run:
        log("[DRY RUN] Would run: Assistant Context")
        results.append(("Assistant Context", True))
    else:
        success = run_command(ctx_cmd, "Assistant Context", timeout=60)
        results.append(("Assistant Context", success))

    # Step 13: Calibration refresh
    # Now that bet grading + prediction backfill are done, regenerate the
    # accuracy/calibration curves so the dashboard shows up-to-date model stats.
    log("-" * 40)
    log("Calibration Refresh")
    calib_cmd = ["python3", "scripts/validation/generate_calibration_data.py"]
    if dry_run:
        log("[DRY RUN] Would run: Calibration Refresh")
        results.append(("Calibration Refresh", True))
    else:
        success = run_command(calib_cmd, "Calibration Refresh", timeout=120)
        results.append(("Calibration Refresh", success))

    # Step 13: Monthly retrain check
    # We track how many tournaments have finished since the last model retrain.
    # At TOURNAMENTS_PER_RETRAIN (4), we run the full retrain pipeline:
    #   merge training data → retrain models → refresh SHAP → refresh player explanations
    # This keeps the model improving without retraining every single week (which
    # would overfit to the most recent tournament).
    log("-" * 40)
    retrain_data = _load_retrain_log()
    # +1 because this tournament hasn't been counted yet
    tournaments_since = retrain_data.get("tournaments_since_retrain", 0) + 1
    did_retrain = False

    if tournaments_since >= TOURNAMENTS_PER_RETRAIN:
        log(f"Retrain threshold reached: {tournaments_since} tournaments since last retrain — running full retrain pipeline")
        retrain_steps = [
            # 1. Pull new tournament results into master_training_data_*.csv
            ("Training Data Merge", ["python3", "scripts/features/merge_all_historical_data.py"]),
            # 2. Retrain all four models (win, top5, top10, top20) on the updated CSV
            ("Model Retrain", ["python3", "scripts/validation/train_final_models.py"]),
            # 3. Recompute SHAP values against the new models + current week's field
            ("SHAP Values", ["python3", "scripts/validation/compute_shap.py"]),
            # 4. Regenerate plain-English player card explanations from fresh SHAP values
            ("Player Explanations", ["python3", "scripts/predictions/generate_player_explanations.py"]),
        ]
        for desc, cmd in retrain_steps:
            if dry_run:
                log(f"[DRY RUN] Would run: {desc}")
                results.append((desc, True))
            else:
                success = run_command(cmd, desc, timeout=step_timeout(desc, 600))
                results.append((desc, success))
                if not success:
                    log(f"  Retrain step '{desc}' failed — stopping retrain pipeline")
                    break
        did_retrain = not dry_run
    else:
        log(f"Retrain check: {tournaments_since}/{TOURNAMENTS_PER_RETRAIN} tournaments since last retrain — no retrain needed")

    if not dry_run:
        _update_retrain_log(tid, did_retrain)
        write_post_tournament_summary(tid, name, results)
        log(f"  Retrain log updated (did_retrain={did_retrain}, count={0 if did_retrain else tournaments_since})")

        # ── Send weekly report email ──────────────────────────────────────────
        try:
            import importlib.util
            _rpt_path = PROJECT_ROOT / "scripts" / "reporting" / "send_report_email.py"
            _spec = importlib.util.spec_from_file_location("send_report_email", _rpt_path)
            _mod  = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)

            _report      = _mod.load_report_for_tid(tid)
            _model_picks = _mod.get_top_model_picks(n=5)
            _html        = _mod.build_html_email(_report, tid, _model_picks)
            _subject     = f"Golf Report: {name} Results + This Week's Picks"
            _mod.send_email(_subject, _html)
            log(f"  Weekly report email sent for {name}")
        except Exception as _email_err:
            log(f"  [warn] Email report failed: {_email_err}")

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
        "monday", "monday-noon", "tuesday-morning", "tuesday-evening",
        "wednesday-morning", "wednesday-evening",
        "live", "record", "post-tournament", "auto"
    ], default="auto", help="Which schedule to run (default: auto-detect)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously refresh live data while a round is in progress")
    parser.add_argument("--interval", type=int, default=5,
                        help="Minutes between refreshes in --watch mode (default: 5)")
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
    elif schedule == "monday-noon":
      results = run_monday_noon_check(args.dry_run)


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

    # Deploy: weekly runs push refreshed data so Render redeploys the live
    # site. Live refresh is excluded — it fires every 10 minutes and would
    # keep the site in a permanent rebuild loop.
    if schedule != "live" and results:
        deploy_ok = deploy_site(schedule, dry_run=args.dry_run)
        results.append(("Deploy Site", deploy_ok))

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

    if not args.dry_run:
        failed_tasks = [d for d, s in results if not s]
        if failed_tasks:
            _title = f"Golf Pipeline [{schedule}]: {success_count}/{total_count} ✗"
            _msg = "Failed: " + ", ".join(failed_tasks[:3])
        else:
            _title = f"Golf Pipeline [{schedule}]: All {total_count} tasks ✓"
            _msg   = "Pipeline completed successfully."
        try:
            import subprocess as _sp
            _sp.run(
                ["osascript", "-e",
                f'display notification "{_msg}" with title "{_title}"'],
                capture_output=True, timeout=5
            )
        except Exception:
            pass





    # Save run log
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "schedule": schedule,
        "dry_run": args.dry_run,
        "results": [{"task": d, "success": s} for d, s in results],
        "success_count": success_count,
        "total_count": total_count,
        "failed_tasks": [d for d, s in results if not s],
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
