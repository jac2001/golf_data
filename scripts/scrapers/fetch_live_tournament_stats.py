"""Fetch live in-tournament SG and stats from PGA Tour GraphQL scorecardStatsComparison.

Per-round values are fetched individually (round=1, round=2, etc.) and summed
to produce accurate cumulative totals that match what the PGA Tour website shows.

round=None returns the average of completed rounds (not cumulative) — we don't use it.
round=N returns stats for that specific round only.
Cumulative = sum of all per-round values.

Output: data/live/live_tournament_stats_{tid}.json

Usage:
    python scripts/scrapers/fetch_live_tournament_stats.py
    python scripts/scrapers/fetch_live_tournament_stats.py --tid R2026011 --top-n 30
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA = PROJECT_ROOT / "data"

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
HEADERS = {
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "content-type": "application/json",
}

CATEGORIES = [
    "STROKES_GAINED",
    "SCORING",
    "OFF_TEE",
    "APPROACH_GREEN",
    "AROUND_GREEN",
    "PUTTING",
]

QUERY = """
query ScorecardsStatsComparison($tournamentId: String!, $playerIds: [String!]!, $category: PlayerComparisonCategory!, $round: Int) {
  scorecardStatsComparison(tournamentId: $tournamentId, playerIds: $playerIds, category: $category, round: $round) {
    tournamentId
    roundNum
    roundDisplay
    noDataMessage
    table {
      header
      headerRow { playerId displayText }
      rows { statName statId values { displayValue bold rank rankDeviation } }
    }
  }
}
"""


def _detect_tournament_id() -> str | None:
    for mf in sorted((DATA / "live").glob("leaderboard_r*_meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(mf) as f:
                meta = json.load(f)
            rs = meta.get("round_status", "").lower()
            if not (rs == "official" and int(meta.get("current_round", 0)) == 4):
                return meta.get("tournament_id")
        except Exception:
            pass
    return None


def _get_current_round(tid: str) -> int:
    """Return the highest round number that has started (1-4)."""
    meta_path = DATA / "live" / f"leaderboard_{tid.lower()}_meta.json"
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        return int(meta.get("current_round", 1))
    except Exception:
        return 1


def fetch_round(tid: str, player_ids: list[str], category: str, round_num: int) -> dict | None:
    """Fetch one category for one specific round."""
    payload = {
        "operationName": "ScorecardsStatsComparison",
        "query": QUERY,
        "variables": {
            "tournamentId": tid,
            "playerIds": player_ids,
            "category": category,
            "round": round_num,
        },
    }
    try:
        r = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            return None
        return data["data"]["scorecardStatsComparison"]
    except Exception:
        return None


def _parse_round_data(data: dict, pid_list: list[str]) -> dict[str, dict[str, dict]]:
    """Parse one round's response into {pid: {stat_name: {value, rank, ...}}}."""
    result: dict[str, dict] = {}
    if not data or not data["table"]["rows"]:
        return result

    header   = data["table"]["headerRow"]
    rows     = data["table"]["rows"]
    pid_to_i = {h["playerId"]: i for i, h in enumerate(header)}

    for row in rows:
        stat = row["statName"]
        for pid, idx in pid_to_i.items():
            if idx < len(row["values"]):
                v = row["values"][idx]
                if pid not in result:
                    result[pid] = {}
                try:
                    float(v["displayValue"])
                    result[pid][stat] = {
                        "stat_id":        row["statId"],
                        "value":          v["displayValue"],
                        "rank":           v["rank"],
                        "rank_deviation": v["rankDeviation"],
                        "is_best":        v["bold"],
                    }
                except (TypeError, ValueError):
                    pass  # '-' or non-numeric = skip
    return result


def fetch_all(tid: str, top_n: int = 25) -> dict:
    """Fetch all categories per-round, compute cumulative totals."""
    lb_path = DATA / "live" / f"leaderboard_{tid.lower()}.csv"
    if not lb_path.exists():
        raise FileNotFoundError(f"Leaderboard not found: {lb_path}")

    lb = pd.read_csv(lb_path).head(top_n).copy()
    player_ids = [str(int(pid)) for pid in lb["player_id"].dropna().tolist()]
    player_map = {
        str(int(row["player_id"])): row["player_name"]
        for _, row in lb.iterrows() if pd.notna(row["player_id"])
    }

    current_round = _get_current_round(tid)
    rounds_to_fetch = list(range(1, current_round + 1))  # e.g. [1, 2, 3]

    print(f"Tournament: {tid} | Current round: {current_round} | Fetching rounds: {rounds_to_fetch}")
    print(f"Players: {len(player_ids)} | Categories: {len(CATEGORIES)}")

    result = {
        "tournament_id":  tid,
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "current_round":  current_round,
        "rounds_fetched": [],
        "player_ids":     player_ids,
        "player_map":     player_map,
        "categories":     {},
    }

    for cat in CATEGORIES:
        print(f"\n  Category: {cat}")
        cat_result = {
            "header":      "",
            "per_round":   {},   # {round_num: {pid: {stat: {...}}}}
            "cumulative":  {},   # {pid: {stat: {value (sum), rank (latest round)}}}
        }

        for rnd in rounds_to_fetch:
            print(f"    Round {rnd}...", end=" ")
            data = fetch_round(tid, player_ids, cat, rnd)
            if data:
                if not cat_result["header"] and data["table"].get("header"):
                    cat_result["header"] = data["table"]["header"]
                round_data = _parse_round_data(data, player_ids)
                if round_data:
                    cat_result["per_round"][str(rnd)] = round_data
                    if str(rnd) not in result["rounds_fetched"]:
                        result["rounds_fetched"].append(str(rnd))
                    n = sum(len(v) for v in round_data.values())
                    print(f"OK ({len(round_data)} players, {n // max(len(round_data),1)} stats each)")
                else:
                    print("no numeric data")
            else:
                print("no response")
            time.sleep(0.2)

        # SG stats are additive (sum across rounds).
        # Rate/average stats (distance, %, scoring avg) must be averaged not summed.
        # Detect by stat_id: SG stats start with "02" (02567, 02568, etc.)
        def _is_additive(stat_id: str) -> bool:
            return str(stat_id).startswith("02")

        # First pass: accumulate sums + counts
        _counts: dict[str, dict[str, int]] = {}
        for rnd_str, rnd_data in cat_result["per_round"].items():
            for pid, stats in rnd_data.items():
                if pid not in cat_result["cumulative"]:
                    cat_result["cumulative"][pid] = {}
                if pid not in _counts:
                    _counts[pid] = {}
                for stat, entry in stats.items():
                    try:
                        v = float(entry["value"])
                    except (TypeError, ValueError):
                        continue
                    if stat not in cat_result["cumulative"][pid]:
                        cat_result["cumulative"][pid][stat] = {
                            "stat_id":  entry["stat_id"],
                            "value":    0.0,
                            "rank":     entry["rank"],
                            "is_best":  False,
                            "additive": _is_additive(entry["stat_id"]),
                        }
                        _counts[pid][stat] = 0
                    cat_result["cumulative"][pid][stat]["value"] += v
                    cat_result["cumulative"][pid][stat]["rank"] = entry["rank"]
                    _counts[pid][stat] += 1

        # Second pass: average non-additive stats
        for pid in cat_result["cumulative"]:
            for stat, entry in cat_result["cumulative"][pid].items():
                n = _counts.get(pid, {}).get(stat, 1)
                if not entry.get("additive", True) and n > 0:
                    entry["value"] = entry["value"] / n
                entry["value"] = round(entry["value"], 3)

        # Mark category leaders (is_best flag on cumulative)
        for stat in set(s for p in cat_result["cumulative"].values() for s in p):
            best_val = max(
                (cat_result["cumulative"][pid].get(stat, {}).get("value", -999) for pid in cat_result["cumulative"]),
                default=-999
            )
            for pid in cat_result["cumulative"]:
                if stat in cat_result["cumulative"][pid]:
                    cat_result["cumulative"][pid][stat]["is_best"] = (
                        cat_result["cumulative"][pid][stat]["value"] == best_val
                    )

        result["categories"][cat] = cat_result

    return result


def save(result: dict, tid: str) -> Path:
    out_path = DATA / "live" / f"live_tournament_stats_{tid}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved → {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tid",   default=None, help="Tournament ID e.g. R2026011")
    parser.add_argument("--top-n", type=int, default=25, help="Number of leaderboard players to include")
    args = parser.parse_args()

    tid = args.tid or _detect_tournament_id()
    if not tid:
        print("Could not detect active tournament. Use --tid.")
        return

    result = fetch_all(tid, top_n=args.top_n)
    save(result, tid)

    # Quick sanity check
    sg = result["categories"].get("STROKES_GAINED", {}).get("cumulative", {})
    pmap = result["player_map"]
    print("\nSG Total cumulative (top 5):")
    sorted_pids = sorted(sg, key=lambda p: sg[p].get("SG: Total", {}).get("value", 0), reverse=True)[:5]
    for pid in sorted_pids:
        name = pmap.get(pid, pid)
        val  = sg[pid].get("SG: Total", {}).get("value", "?")
        rank = sg[pid].get("SG: Total", {}).get("rank", "?")
        print(f"  {name}: {val:+.3f} (#{rank})")


if __name__ == "__main__":
    main()
