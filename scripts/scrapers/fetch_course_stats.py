#!/usr/bin/env python3
"""
Fetch live in-tournament course stats from PGA Tour GraphQL.

Uses courseHolesStats query — returns aggregate scoring stats per hole
across all completed rounds. Updated live throughout the tournament.

Output: data/live/course_stats_{tid}.json

Usage:
    python scripts/scrapers/fetch_course_stats.py
    python scripts/scrapers/fetch_course_stats.py --tid R2026011
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "content-type": "application/json",
}

COURSE_STATS_QUERY = """
query CourseStats($tournamentId: ID!) {
  courseStats(tournamentId: $tournamentId) {
    tournamentId
    courses {
      courseId
      courseName
      par
      yardage
    }
  }
}
"""

HOLE_STATS_QUERY = """
query CourseHolesStats($tournamentId: ID!, $courseId: ID!) {
  courseHolesStats(tournamentId: $tournamentId, courseId: $courseId) {
    holeNum
    scoringAverage
    eagles
    eaglesPercent
    birdies
    birdiesPercent
    pars
    parsPercent
    bogeys
    bogeysPercent
    doubleBogeys
    doubleBogeysPercent
  }
}
"""


def _detect_tid() -> str | None:
    for mf in sorted((DATA / "live").glob("leaderboard_r*_meta.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(mf) as f:
                meta = json.load(f)
            rs = meta.get("round_status", "").lower()
            if not (rs in {"official", "complete", "final"} and int(meta.get("current_round", 0)) == 4):
                return meta.get("tournament_id")
        except Exception:
            pass
    return None


def fetch(tid: str) -> dict | None:
    # Step 1: get course ID and name
    r = requests.post(GRAPHQL_URL, headers=HEADERS, json={
        "operationName": "CourseStats",
        "query": COURSE_STATS_QUERY,
        "variables": {"tournamentId": tid},
    }, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        print(f"  courseStats error: {data['errors'][0]['message']}")
        return None

    courses = data["data"]["courseStats"]["courses"]
    if not courses:
        print("  No courses returned.")
        return None

    course = courses[0]
    course_id = course["courseId"]
    course_name = course["courseName"]
    print(f"  Course: {course_name} (ID: {course_id})")

    time.sleep(0.3)

    # Step 2: get hole stats
    r2 = requests.post(GRAPHQL_URL, headers=HEADERS, json={
        "operationName": "CourseHolesStats",
        "query": HOLE_STATS_QUERY,
        "variables": {"tournamentId": tid, "courseId": course_id},
    }, timeout=15)
    r2.raise_for_status()
    data2 = r2.json()
    if "errors" in data2:
        print(f"  courseHolesStats error: {data2['errors'][0]['message']}")
        return None

    holes = data2["data"]["courseHolesStats"]
    print(f"  Holes: {len(holes)}")

    return {
        "tournament_id": tid,
        "course_id": course_id,
        "course_name": course_name,
        "par": course.get("par"),
        "yardage": course.get("yardage"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "holes": holes,
    }


def save(result: dict, tid: str) -> Path:
    out = DATA / "live" / f"course_stats_{tid}.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  Saved -> {out}")
    return out


def print_summary(result: dict) -> None:
    holes = result["holes"]
    hardest = sorted(holes, key=lambda h: float(h["scoringAverage"]), reverse=True)[:3]
    easiest = sorted(holes, key=lambda h: float(h["scoringAverage"]))[:3]
    print(f"\n  Hardest holes (this week):")
    for h in hardest:
        print(f"    Hole {h['holeNum']:2d}  avg {h['scoringAverage']:>6}  birdie={h['birdiesPercent']}%  bogey={h['bogeysPercent']}%")
    print(f"  Easiest holes (birdie chances):")
    for h in easiest:
        print(f"    Hole {h['holeNum']:2d}  avg {h['scoringAverage']:>6}  birdie={h['birdiesPercent']}%  bogey={h['bogeysPercent']}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tid", default=None)
    args = parser.parse_args()

    tid = args.tid or _detect_tid()
    if not tid:
        print("Could not detect active tournament. Use --tid.")
        return

    print(f"Fetching live course stats: {tid}")
    result = fetch(tid)
    if result:
        save(result, tid)
        print_summary(result)
    else:
        print("No data returned.")


if __name__ == "__main__":
    main()
