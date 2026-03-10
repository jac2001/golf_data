#!/usr/bin/env python3
"""
Fetch pre-tournament tee times from PGA Tour GraphQL teeTimes query.

Usage:
    python3 scripts/scrapers/fetch_tee_times.py --tid R2026011 --round 1
    python3 scripts/scrapers/fetch_tee_times.py --tid R2026011 --round 2
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIVE_DIR = DATA_DIR / "live"

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

TEE_TIMES_QUERY = """
query TeeTimes($id: ID!) {
  teeTimes(id: $id) {
    timezone
    rounds {
      roundInt
      groups {
        ... on Group {
          teeTime
          startTee
          players {
            ... on Player {
              id
              displayName
              firstName
              lastName
            }
          }
        }
      }
    }
  }
}
"""


def fetch_tee_times(tid: str, round_num: int) -> pd.DataFrame:
    """Fetch tee times from PGA Tour GraphQL for given tournament + round."""
    resp = requests.post(
        GRAPHQL_URL,
        json={
            "query": TEE_TIMES_QUERY,
            "variables": {"id": tid},
            "operationName": "TeeTimes",
        },
        headers=GRAPHQL_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    body = resp.json()

    if body.get("errors"):
        msg = body["errors"][0].get("message", "GraphQL error")
        raise RuntimeError(msg)

    data = body.get("data", {}).get("teeTimes", {})
    tz_str = data.get("timezone", "America/New_York")
    try:
        local_tz = ZoneInfo(tz_str)
    except Exception:
        local_tz = ZoneInfo("America/New_York")

    rounds = data.get("rounds", [])
    target_round = None
    for r in rounds:
        if r.get("roundInt") == round_num:
            target_round = r
            break

    if target_round is None:
        print(f"Round {round_num} not found in tee times (available rounds: {[r['roundInt'] for r in rounds]})")
        return pd.DataFrame()

    rows = []
    for group in target_round.get("groups", []):
        ts_ms = group.get("teeTime")
        start_tee = group.get("startTee", 1)
        if not ts_ms:
            continue

        # AWSTimestamp is milliseconds since epoch
        dt_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        dt_local = dt_utc.astimezone(local_tz)
        tee_time_str = dt_local.strftime("%-I:%M %p") + " " + _tz_abbr(dt_local)

        for player in group.get("players", []):
            pid = player.get("id", "")
            name = (
                player.get("displayName")
                or f"{player.get('firstName','')} {player.get('lastName','')}".strip()
            )
            if not pid and not name:
                continue
            rows.append({
                "player_id": pid,
                "player_name": name,
                "round": round_num,
                "tee_time_str": tee_time_str,
                "tee_time_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
                "tee_time_local": dt_local.strftime("%Y-%m-%dT%H:%M:%S"),
                "start_tee": start_tee,
            })

    return pd.DataFrame(rows).reset_index(drop=True)


def _tz_abbr(dt: datetime) -> str:
    """Return timezone abbreviation like 'EDT' from an aware datetime."""
    return dt.strftime("%Z") or "ET"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch pre-tournament tee times from PGA Tour")
    parser.add_argument("--tid", required=True, help="Tournament ID, e.g. R2026011")
    parser.add_argument("--round", type=int, default=1, dest="round_num", help="Round number (1-4)")
    parser.add_argument("--output", type=str, default="", help="Override output CSV path")
    args = parser.parse_args()

    print(f"Fetching tee times for {args.tid} round {args.round_num}...")
    df = fetch_tee_times(args.tid, args.round_num)

    if df.empty:
        print("No tee times found.")
        return 0

    out_path = args.output or str(LIVE_DIR / f"tee_times_{args.tid}_r{args.round_num}.csv")
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} players across {df['tee_time_str'].nunique()} tee times → {out_path}")
    print(df[["player_name", "tee_time_str", "start_tee"]].head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
