#!/usr/bin/env python3
"""
PGA Tour Hole-Level Score Fetcher
==================================

Fetches per-hole scores for all players via PGA Tour GraphQL API.

Primary method: scorecardCompressedV3 — returns a gzip+base64 payload
containing full hole-by-hole data with actual par per hole and shot status
(BIRDIE, PAR, BOGEY, etc.) for each player.

Usage:
    python3 scripts/scrapers/fetch_hole_scores.py --tournament-id R2026009
    python3 scripts/scrapers/fetch_hole_scores.py --tournament-id R2026009 --round 1
"""

import argparse
import base64
import gzip
import json
from pathlib import Path
from typing import List, Optional

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

# ── Primary query: compressed scorecard per player ───────────────────────────
# Takes tournamentId + playerId as separate arguments (not combined).
# Returns a gzip+base64 "payload" we decode ourselves.
SCORECARD_COMPRESSED_QUERY = """
query ScorecardCompressedV3($tournamentId: ID!, $playerId: ID!) {
  scorecardCompressedV3(tournamentId: $tournamentId, playerId: $playerId) {
    id
    payload
  }
}
"""

# ── Status string → par-relative integer mapping ─────────────────────────────
# The decoded payload has a "status" field per hole (e.g. "BIRDIE", "BOGEY").
# We convert this to the same -2/-1/0/+1/+2 scale used throughout the dashboard.
STATUS_TO_REL = {
    "EAGLE": -2,
    "BIRDIE": -1,
    "PAR": 0,
    "BOGEY": 1,
    "DOUBLE_BOGEY": 2,
    "TRIPLE_BOGEY": 3,
}


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
    """POST a GraphQL query. Returns the 'data' dict or None on any error."""
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


def _decode_payload(payload_b64: str) -> Optional[dict]:
    """
    Decode the gzip+base64 payload returned by scorecardCompressedV3.

    The API returns a base64-encoded string. When decoded, it's gzip-compressed
    JSON. We decompress and parse it here.
    """
    try:
        compressed = base64.b64decode(payload_b64)
        raw_json = gzip.decompress(compressed)
        return json.loads(raw_json)
    except Exception:
        return None


def _parse_compressed_scorecard(data: dict, player_id: str, player_name: str) -> List[dict]:
    """
    Parse decoded scorecardCompressedV3 payload into our standard row format.

    The decoded structure looks like:
    {
      "currentRound": 1,
      "roundScores": [
        {
          "firstNine": {
            "holes": [{"holeNumber":1, "par":4, "score":"4", "status":"PAR"}, ...]
          },
          "secondNine": {
            "holes": [{"holeNumber":10, ...}, ...]
          }
        },
        ...  (one entry per round played)
      ]
    }

    Each entry in roundScores corresponds to one round (index 0 = round 1, etc.).
    """
    rows = []
    round_scores = data.get("roundScores") or []

    for round_idx, rdata in enumerate(round_scores):
        # Round number = 1-indexed position in the array
        rnum = round_idx + 1

        # Collect all 18 holes from firstNine + secondNine
        first_nine = (rdata.get("firstNine") or {}).get("holes") or []
        second_nine = (rdata.get("secondNine") or {}).get("holes") or []
        all_holes = first_nine + second_nine

        if not all_holes:
            continue

        row = {"player_id": player_id, "player_name": player_name, "round": rnum}

        for h in all_holes:
            hnum = _safe_int(h.get("holeNumber"))
            if not hnum:
                continue

            # Raw strokes on this hole (e.g. 4)
            strokes = _safe_int(h.get("score"))
            if strokes is not None:
                row[f"h{hnum}"] = strokes

            # Par for this hole (e.g. 4) — store directly so the dashboard
            # can show the PAR row without computing it from relative score
            par = _safe_int(h.get("par"))
            if par is not None:
                row[f"h{hnum}_par"] = par

            # Par-relative integer: -2=eagle, -1=birdie, 0=par, +1=bogey, +2=double
            status = str(h.get("status", "")).upper()
            if status in STATUS_TO_REL:
                rel = STATUS_TO_REL[status]
            else:
                # Unusual status (e.g. HOLE_IN_ONE) — compute from score - par
                if strokes is not None and par is not None:
                    rel = strokes - par
                else:
                    rel = None
            if rel is not None:
                row[f"h{hnum}_rel"] = rel

            # Running to-par score after this hole (e.g. "E", "-1", "+2")
            # This shows how the score changed hole-by-hole — same as the tour site
            running = h.get("roundScore")
            if running is not None:
                row[f"h{hnum}_running"] = str(running)

        # Only keep this round if we got at least some hole data
        if any(f"h{i}" in row for i in range(1, 19)):
            row["front9"] = sum(row.get(f"h{i}", 0) for i in range(1, 10))
            row["back9"]  = sum(row.get(f"h{i}", 0) for i in range(10, 19))
            row["total"]  = row["front9"] + row["back9"]
            rows.append(row)

    return rows


def fetch_compressed_scorecard(tournament_id: str, player_id: str, player_name: str) -> List[dict]:
    """
    Fetch hole scores for one player using scorecardCompressedV3.

    The API combines tournament + player into a single ID: "R2026009-50525".
    Returns list of rows (one per round played), or empty list if unavailable.
    """
    data = _gql(SCORECARD_COMPRESSED_QUERY, {"tournamentId": tournament_id, "playerId": player_id})
    if not data:
        return []

    sc = data.get("scorecardCompressedV3")
    if not sc or not sc.get("payload"):
        return []

    decoded = _decode_payload(sc["payload"])
    if not decoded:
        return []

    return _parse_compressed_scorecard(decoded, player_id, player_name)


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
    Main fetch function. Fetches scorecardCompressedV3 for every player in the field.

    Returns DataFrame with columns:
        player_id, player_name, round, h1..h18, h1_rel..h18_rel, front9, back9, total
    """
    print(f"Fetching hole scores for {tournament_id}...")

    players = load_players_from_leaderboard(tournament_id)
    if not players:
        print("  No player list available — run fetch_live_leaderboard.py first")
        return pd.DataFrame()

    # Probe first player to confirm the endpoint is working
    probe = players[0]
    probe_rows = fetch_compressed_scorecard(
        tournament_id, str(probe["player_id"]), str(probe["player_name"])
    )
    if not probe_rows:
        print("  scorecardCompressedV3 returned no data — scores not yet available")
        return pd.DataFrame()

    print(f"  Endpoint confirmed ({probe['player_name']}: {len(probe_rows)} round(s))")
    print(f"  Fetching all {len(players)} players...")

    rows = list(probe_rows)  # start with probe results already fetched
    for p in players[1:]:
        pid   = str(p["player_id"])
        pname = str(p["player_name"])
        player_rows = fetch_compressed_scorecard(tournament_id, pid, pname)
        rows.extend(player_rows)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Filter to specific round if requested
    if round_num is not None and "round" in df.columns:
        df = df[df["round"] == round_num].copy()

    # Ensure all h1..h18 columns exist (fill missing with None)
    for i in range(1, 19):
        if f"h{i}" not in df.columns:
            df[f"h{i}"] = None

    # Reorder columns: base | h1..h18 | h1_par..h18_par | h1_rel..h18_rel | h1_running..h18_running | totals
    base_cols    = ["player_id", "player_name", "round"]
    hole_cols    = [f"h{i}" for i in range(1, 19)]
    par_cols     = [f"h{i}_par"     for i in range(1, 19) if f"h{i}_par"     in df.columns]
    rel_cols     = [f"h{i}_rel"     for i in range(1, 19) if f"h{i}_rel"     in df.columns]
    running_cols = [f"h{i}_running" for i in range(1, 19) if f"h{i}_running" in df.columns]
    summary_cols = ["front9", "back9", "total"]
    keep = base_cols + hole_cols + par_cols + rel_cols + running_cols + summary_cols
    keep = [c for c in keep if c in df.columns]
    df = df[keep].sort_values(["round", "player_name"]).reset_index(drop=True)

    print(f"  Done — {len(df)} player-round rows ({df['round'].nunique()} round(s))")
    return df


def save_hole_scores(df: pd.DataFrame, tournament_id: str) -> Path:
    """
    Save hole scores, merging with existing file.
    Rounds in the new DataFrame overwrite the same rounds in the existing file.
    """
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LIVE_DIR / f"hole_scores_{tournament_id.lower()}.csv"

    if out_path.exists() and not df.empty:
        existing = pd.read_csv(out_path)
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
    print(f"\nSample:")
    print(df.head(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
