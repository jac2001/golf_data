#!/usr/bin/env python3
"""
PGA Tour Hole-Level Score Fetcher
==================================

Fetches per-hole scores for all players via PGA Tour GraphQL API.
Falls back to `scorecardV3` if `leaderboardV3` holes sub-field is unsupported.

Usage:
    python3 scripts/scrapers/fetch_hole_scores.py --tournament-id R2026009
    python3 scripts/scrapers/fetch_hole_scores.py --tournament-id R2026009 --round 1
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

# Try leaderboardV3 with holes sub-field first
LEADERBOARD_WITH_HOLES_QUERY = """
query LeaderboardV3WithHoles($id: ID!) {
  leaderboardV3(id: $id) {
    currentRound
    players {
      ... on PlayerRowV3 {
        player {
          id
          displayName
        }
        rounds {
          roundNumber
          score
          holes {
            holeNumber
            score
            parRelativeScore
          }
        }
      }
    }
  }
}
"""

# Fallback: scorecardV3 per player
SCORECARD_V3_QUERY = """
query ScorecardV3($tournamentId: ID!, $playerId: ID!) {
  scorecardV3(tournamentId: $tournamentId, playerId: $playerId) {
    rounds {
      roundNumber
      strokes
      holes {
        holeNumber
        strokes
        parRelativeScore
      }
    }
  }
}
"""

# Alternative: playerScorecard query
PLAYER_SCORECARD_QUERY = """
query PlayerScorecard($id: ID!, $playerId: ID!) {
  playerScorecard(id: $id, playerId: $playerId) {
    rounds {
      roundNumber
      strokes
      holes {
        holeNumber
        strokes
        parRelativeScore
      }
    }
  }
}
"""


def _build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _build_session()


def _gql(query: str, variables: dict) -> Optional[dict]:
    try:
        resp = SESSION.post(
            GRAPHQL_URL,
            headers=GRAPHQL_HEADERS,
            json={"query": query, "variables": variables},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("errors"):
            return None
        return data.get("data")
    except Exception:
        return None


def _safe_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def fetch_holes_via_leaderboard(tournament_id: str) -> Optional[List[dict]]:
    """
    Try to get hole scores from leaderboardV3 holes sub-field.
    Returns list of {player_id, player_name, round, h1..h18, front9, back9, total}
    or None if the query fails / holes field unsupported.
    """
    data = _gql(LEADERBOARD_WITH_HOLES_QUERY, {"id": tournament_id})
    if not data:
        return None

    lb = data.get("leaderboardV3", {})
    players = lb.get("players", [])
    if not players:
        return None

    # Check if any player has holes data
    sample = players[0] if players else {}
    rounds = sample.get("rounds", [])
    if not rounds or not rounds[0].get("holes"):
        print("  leaderboardV3 holes sub-field not supported")
        return None

    rows = []
    for p in players:
        pid = p.get("player", {}).get("id")
        pname = p.get("player", {}).get("displayName", "")
        for r in (p.get("rounds") or []):
            rnum = _safe_int(r.get("roundNumber"), 1)
            holes = r.get("holes") or []
            if not holes:
                continue
            row = {"player_id": pid, "player_name": pname, "round": rnum}
            for h in holes:
                hnum = _safe_int(h.get("holeNumber"))
                score = _safe_int(h.get("score") or h.get("strokes"))
                if hnum and score is not None:
                    row[f"h{hnum}"] = score
            if any(f"h{i}" in row for i in range(1, 19)):
                row["front9"] = sum(row.get(f"h{i}", 0) for i in range(1, 10))
                row["back9"] = sum(row.get(f"h{i}", 0) for i in range(10, 19))
                row["total"] = row["front9"] + row["back9"]
                rows.append(row)

    return rows if rows else None


def fetch_scorecard_for_player(tournament_id: str, player_id: str, player_name: str) -> List[dict]:
    """Fetch hole scores for a single player via scorecardV3 or playerScorecard."""
    rows = []

    for query, query_name in [
        (SCORECARD_V3_QUERY, "scorecardV3"),
        (PLAYER_SCORECARD_QUERY, "playerScorecard"),
    ]:
        data = _gql(query, {"tournamentId": tournament_id, "id": tournament_id,
                             "playerId": player_id})
        if not data:
            continue

        scorecard = data.get(query_name) or data.get("scorecardV3") or data.get("playerScorecard")
        if not scorecard:
            continue

        for r in (scorecard.get("rounds") or []):
            rnum = _safe_int(r.get("roundNumber"), 1)
            holes = r.get("holes") or []
            if not holes:
                continue
            row = {"player_id": player_id, "player_name": player_name, "round": rnum}
            for h in holes:
                hnum = _safe_int(h.get("holeNumber"))
                score = _safe_int(h.get("strokes") or h.get("score"))
                if hnum and score is not None:
                    row[f"h{hnum}"] = score
            if any(f"h{i}" in row for i in range(1, 19)):
                row["front9"] = sum(row.get(f"h{i}", 0) for i in range(1, 10))
                row["back9"] = sum(row.get(f"h{i}", 0) for i in range(10, 19))
                row["total"] = row["front9"] + row["back9"]
                rows.append(row)

        if rows:
            break

    return rows


def load_players_from_leaderboard(tournament_id: str) -> List[dict]:
    """Load player list from local leaderboard CSV for per-player fetching."""
    lb_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv"
    if not lb_path.exists():
        return []

    try:
        df = pd.read_csv(lb_path)
        if "player_id" not in df.columns or "player_name" not in df.columns:
            return []
        return df[["player_id", "player_name"]].dropna().to_dict("records")
    except Exception:
        return []


def fetch_all_hole_scores(tournament_id: str, round_num: Optional[int] = None) -> pd.DataFrame:
    """
    Main fetch function. Tries leaderboard bulk first, then per-player fallback.
    Returns DataFrame with columns: player_id, player_name, round, h1..h18, front9, back9, total
    """
    print(f"Fetching hole scores for {tournament_id}...")

    # Attempt 1: bulk via leaderboardV3 holes sub-field
    rows = fetch_holes_via_leaderboard(tournament_id)
    if rows:
        print(f"  Got {len(rows)} round rows via leaderboardV3 holes sub-field")
    else:
        print("  Falling back to per-player scorecard fetch...")
        players = load_players_from_leaderboard(tournament_id)
        if not players:
            print(f"  No player list available — run fetch_live_leaderboard.py first")
            return pd.DataFrame()

        rows = []
        for i, p in enumerate(players[:5]):  # limit to 5 players as probe
            pid = str(p["player_id"])
            pname = str(p["player_name"])
            player_rows = fetch_scorecard_for_player(tournament_id, pid, pname)
            if player_rows:
                rows.extend(player_rows)
                if i == 0:
                    print(f"  Scorecard fetch works for {pname} ({len(player_rows)} rounds)")

        if not rows:
            print("  Neither scorecard endpoint returned hole data — not yet available")
            return pd.DataFrame()

        # If probe worked, fetch full field
        print(f"  Fetching all {len(players)} players...")
        rows = []
        for p in players:
            pid = str(p["player_id"])
            pname = str(p["player_name"])
            player_rows = fetch_scorecard_for_player(tournament_id, pid, pname)
            rows.extend(player_rows)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Filter to specific round if requested
    if round_num is not None and "round" in df.columns:
        df = df[df["round"] == round_num].copy()

    # Ensure all h1..h18 columns exist
    for i in range(1, 19):
        col = f"h{i}"
        if col not in df.columns:
            df[col] = None

    # Reorder columns
    base_cols = ["player_id", "player_name", "round"]
    hole_cols = [f"h{i}" for i in range(1, 19)]
    summary_cols = ["front9", "back9", "total"]
    keep = base_cols + hole_cols + summary_cols
    keep = [c for c in keep if c in df.columns]
    df = df[keep].sort_values(["round", "player_name"]).reset_index(drop=True)

    return df


def save_hole_scores(df: pd.DataFrame, tournament_id: str) -> Path:
    """
    Save hole scores, merging with existing file (overwrite same round, append new rounds).
    """
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LIVE_DIR / f"hole_scores_{tournament_id.lower()}.csv"

    if out_path.exists() and not df.empty:
        existing = pd.read_csv(out_path)
        # Drop rounds being overwritten
        if "round" in existing.columns and "round" in df.columns:
            updated_rounds = df["round"].unique().tolist()
            existing = existing[~existing["round"].isin(updated_rounds)]
        df = pd.concat([existing, df], ignore_index=True)

    df.to_csv(out_path, index=False)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Fetch hole-level scores from PGA Tour")
    parser.add_argument("--tournament-id", required=True, help="Tournament ID e.g. R2026009")
    parser.add_argument("--round", type=int, default=None, help="Specific round to fetch")
    parser.add_argument("--output", help="Override output path")
    args = parser.parse_args()

    tid = args.tournament_id.upper()
    df = fetch_all_hole_scores(tid, round_num=args.round)

    if df.empty:
        print("No hole score data available.")
        return 1

    out_path = Path(args.output) if args.output else None
    if out_path is None:
        out_path = save_hole_scores(df, tid)
    else:
        df.to_csv(out_path, index=False)

    print(f"Saved {len(df)} rows to {out_path}")

    # Preview
    print(f"\nSample:")
    print(df.head(3).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
