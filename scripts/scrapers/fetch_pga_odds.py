#!/usr/bin/env python3
"""
PGA Tour Odds Scraper
=====================

Fetches betting odds directly from PGA Tour's GraphQL API.

This is more reliable than third-party APIs because:
1. It's the official source shown on pgatour.com
2. No API key needed
3. Always has data for current/upcoming PGA Tour events

HOW BETTING ODDS WORK:
---------------------
American odds format:
  +500  = Underdog. Bet $100 to win $500 profit. Implied prob = 100/(500+100) = 16.7%
  +2000 = Long shot. Bet $100 to win $2000. Implied prob = 100/(2000+100) = 4.8%
  +350  = Favorite (in golf context). Bet $100 to win $350. Implied prob = 22.2%

Note: Golf rarely has negative odds since even favorites are long shots to win.

Usage:
    # Fetch odds for a specific tournament
    python3 scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002

    # Fetch odds for current/upcoming tournament
    python scripts/scrapers/fetch_pga_odds.py --current

Output columns:
    - player_id: PGA Tour player ID
    - player_name: Player name
    - odds_to_win: American odds string (e.g., "+500")
    - odds_numeric: Numeric odds value (e.g., 500)
    - implied_prob: Probability implied by odds
    - fair_prob: Probability with vig removed (sums to 100%)
    - odds_swing: Movement indicator (UP, DOWN, CONSTANT)
"""

import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

# ============================================================================
# Configuration
# ============================================================================

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

# Output directory
OUTPUT_DIR = Path("data/odds")
PREDICTIONS_DIR = Path("outputs")

# GraphQL query for tournament odds
TOURNAMENT_ODDS_QUERY = """
query TournamentOddsToWin($tournamentId: ID!) {
  tournamentOddsToWin(tournamentId: $tournamentId) {
    tournamentId
    tournamentName
    players {
      playerId
      oddsToWin
      oddsSwing
      oddsSort
      oddsDirection
    }
  }
}
"""

TOURNAMENT_ODDS_QUERY_FALLBACK = """
query TournamentOddsToWin($tournamentId: ID!) {
  tournamentOddsToWin(tournamentId: $tournamentId) {
    tournamentId
    tournamentName
    players {
      playerId
      oddsToWin
      oddsSwing
      oddsSort
    }
  }
}
"""

# Query to get player names (since odds query only returns IDs)
PLAYER_INFO_QUERY = """
query LeaderboardV3($id: ID!) {
  leaderboardV3(id: $id) {
    players {
      ... on PlayerRowV3 {
        player {
          id
          firstName
          lastName
          displayName
        }
      }
    }
  }
}
"""


# ============================================================================
# Odds Conversion Functions
# ============================================================================

def parse_american_odds(odds_str: Any) -> Optional[int]:
    """
    Parse American odds string to numeric value.

    Args:
        odds_str: Odds string like "+500" or "-150"

    Returns:
        Numeric odds value (500 for "+500", -150 for "-150")
    """
    if odds_str is None or odds_str == "":
        return None
    try:
        # Numeric payloads are already American odds.
        if isinstance(odds_str, (int, float)) and not pd.isna(odds_str):
            return int(odds_str)
        # Handle dict payloads such as {"american": "+1600"}.
        if isinstance(odds_str, dict):
            raw = (
                odds_str.get("american")
                or odds_str.get("oddsAmerican")
                or odds_str.get("odds")
                or odds_str.get("value")
            )
            return parse_american_odds(raw)
        s = str(odds_str).strip()
        if not s:
            return None
        # Remove "+" prefix if present
        s = s.replace("+", "")
        return int(float(s))
    except (ValueError, TypeError, AttributeError):
        return None


def american_odds_to_probability(odds_str: str) -> float:
    """
    Convert American odds string (e.g., '+185') to implied probability.

    Returns:
        Probability on [0, 1], or None if invalid.
    """
    odds_numeric = parse_american_odds(odds_str)
    return american_to_implied_prob(odds_numeric)


def american_to_implied_prob(american_odds: int) -> float:
    """
    Convert American odds to implied probability.

    Formula:
    - Positive: prob = 100 / (odds + 100)
    - Negative: prob = |odds| / (|odds| + 100)

    Examples:
        +500  -> 100 / 600 = 16.67%
        +2000 -> 100 / 2100 = 4.76%
        -150  -> 150 / 250 = 60%

    Args:
        american_odds: Numeric odds (e.g., 500, -150)

    Returns:
        Implied probability (0.0 to 1.0)
    """
    if american_odds is None:
        return None

    if american_odds >= 0:
        # Underdog (or slight favorite in golf context)
        return 100 / (american_odds + 100)
    else:
        # Heavy favorite
        return abs(american_odds) / (abs(american_odds) + 100)


def remove_vig(probabilities: list) -> list:
    """
    Remove the vigorish (vig) from implied probabilities.

    Sportsbooks build in a margin (vig) so probabilities sum to >100%.
    This normalizes them to sum to 100% for "fair" probabilities.

    Args:
        probabilities: List of implied probabilities (may sum to >1.0)

    Returns:
        List of fair probabilities (sums to 1.0)
    """
    # Filter out None values for calculation
    valid_probs = [p for p in probabilities if p is not None]
    total = sum(valid_probs)

    if total == 0:
        return probabilities

    # Normalize
    return [p / total if p is not None else None for p in probabilities]


def _name_key(name: str) -> str:
    """Normalize player name for loose matching."""
    if pd.isna(name):
        return ""
    cleaned = str(name).replace(",", " ").replace(".", " ").replace("-", " ").lower().strip()
    tokens = [t for t in cleaned.split() if t]
    tokens = [t for t in tokens if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    tokens.sort()
    return " ".join(tokens)


def _walk(obj: Any):
    """Yield dict nodes recursively."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk(x)


def _extract_players_from_odds_payload(odds_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract player-level odds rows from varying PGA payload shapes.
    Primary shape is odds_data["players"], but schema can drift.
    """
    if not isinstance(odds_data, dict):
        return []

    if isinstance(odds_data.get("players"), list):
        return [p for p in odds_data.get("players", []) if isinstance(p, dict)]

    # Fallback: search recursively for list fields containing playerId + odds.
    candidates: List[Dict[str, Any]] = []
    for node in _walk(odds_data):
        for key in ("players", "playerOdds", "entries", "selections", "outcomes"):
            arr = node.get(key)
            if not isinstance(arr, list):
                continue
            for item in arr:
                if not isinstance(item, dict):
                    continue
                has_player = any(k in item for k in ("playerId", "player_id", "id"))
                has_odds = any(k in item for k in ("oddsToWin", "odds", "americanOdds", "oddsAmerican", "displayOdds"))
                if has_player and has_odds:
                    candidates.append(item)
    return candidates


def _normalize_player_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not pd.isna(value):
            return int(value)
        s = str(value).strip()
        if not s:
            return None
        # player IDs are numeric; tolerate accidental wrappers.
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else None
    except Exception:
        return None


def _extract_odds_value(player_row: Dict[str, Any]) -> Any:
    """Extract american odds value from multiple row shapes."""
    if player_row.get("oddsToWin") is not None:
        return player_row.get("oddsToWin")
    if player_row.get("oddsAmerican") is not None:
        return player_row.get("oddsAmerican")
    if player_row.get("americanOdds") is not None:
        return player_row.get("americanOdds")
    if player_row.get("odds") is not None:
        return player_row.get("odds")
    display = player_row.get("displayOdds")
    if isinstance(display, dict):
        return display.get("american")
    return None


def load_cached_odds_df(tournament_id: str) -> pd.DataFrame:
    """Load last saved odds as fallback if live fetch is empty/unavailable."""
    path = OUTPUT_DIR / f"pga_odds_{tournament_id}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame()
        # Mark source for visibility in logs/dashboard if needed.
        if "line_source" not in df.columns:
            df["line_source"] = "pga_odds_cache"
        return df
    except Exception:
        return pd.DataFrame()


def _load_predictions_for_edge(tournament_id: str) -> pd.DataFrame:
    """Load best-available predictions file for edge calculation."""
    candidates = [
        PREDICTIONS_DIR / f"{tournament_id}_predictions.csv",
        PREDICTIONS_DIR / f"{tournament_id.lower()}_predictions.csv",
        PREDICTIONS_DIR / "latest_predictions.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    return df
            except Exception:
                continue
    return pd.DataFrame()


def add_model_edge_columns(odds_df: pd.DataFrame, tournament_id: str) -> pd.DataFrame:
    """
    Add model probability + edge columns for value-bet analysis.

    Edge is defined as:
        edge_win_prob = model_win_prob - fanduel_implied_prob
    """
    df = odds_df.copy()
    if df.empty:
        return df

    # Cached odds files may already include these columns; recompute cleanly.
    edge_cols = ["model_win_prob", "edge_win_prob", "edge_pct_points", "is_value_bet"]
    drop_cols = [c for c in edge_cols if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols, errors="ignore")

    if "implied_prob" in df.columns:
        df["implied_prob"] = pd.to_numeric(df["implied_prob"], errors="coerce")

    preds = _load_predictions_for_edge(tournament_id)
    if preds.empty or "win_prob" not in preds.columns:
        df["model_win_prob"] = np.nan
        df["edge_win_prob"] = np.nan
        df["edge_pct_points"] = np.nan
        df["is_value_bet"] = False
        return df

    # Prefer exact ID join when possible.
    if "player_id" in preds.columns:
        left = df.copy()
        right = preds[["player_id", "win_prob"]].copy()
        left["player_id"] = pd.to_numeric(left["player_id"], errors="coerce").astype("Int64")
        right["player_id"] = pd.to_numeric(right["player_id"], errors="coerce").astype("Int64")
        merged = left.merge(right, on="player_id", how="left")
    else:
        left = df.copy()
        right = preds[["player_name", "win_prob"]].copy()
        left["name_key"] = left["player_name"].apply(_name_key)
        right["name_key"] = right["player_name"].apply(_name_key)
        merged = left.merge(right[["name_key", "win_prob"]], on="name_key", how="left")
        merged = merged.drop(columns=["name_key"], errors="ignore")

    merged = merged.rename(columns={"win_prob": "model_win_prob"})
    merged["model_win_prob"] = pd.to_numeric(merged["model_win_prob"], errors="coerce")
    merged["edge_win_prob"] = merged["model_win_prob"] - merged["implied_prob"]
    merged["edge_pct_points"] = merged["edge_win_prob"] * 100.0
    merged["is_value_bet"] = merged["edge_win_prob"] > 0
    return merged


def build_fanduel_odds_view(df: pd.DataFrame) -> pd.DataFrame:
    """Create a dedicated FanDuel odds dataset with explicit column naming."""
    out = df.copy()
    if out.empty:
        return out

    out["sportsbook"] = "FanDuel"
    out["market"] = "winner"
    out["fanduel_odds"] = out["odds_to_win"]
    out["fanduel_implied_prob"] = out["implied_prob"]
    out["fanduel_fair_prob"] = out["fair_prob"]
    if "odds_direction" not in out.columns:
        out["odds_direction"] = out.get("odds_swing", "")
    if "odds_swing" not in out.columns:
        out["odds_swing"] = ""
    if "fetched_at" not in out.columns:
        out["fetched_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    out["odds_movement_direction"] = out["odds_direction"].fillna("").astype(str)
    out["odds_movement_swing"] = out["odds_swing"].fillna("").astype(str)

    priority_cols = [
        "tournament_id",
        "tournament_name",
        "sportsbook",
        "market",
        "player_id",
        "player_name",
        "fanduel_odds",
        "odds_numeric",
        "fanduel_implied_prob",
        "fanduel_fair_prob",
        "odds_sort",
        "odds_rank",
        "odds_movement_direction",
        "odds_movement_swing",
        "model_win_prob",
        "edge_win_prob",
        "edge_pct_points",
        "is_value_bet",
        "fetched_at",
    ]
    remaining = [c for c in out.columns if c not in priority_cols]
    return out[priority_cols + remaining]


# ============================================================================
# API Functions
# ============================================================================

def fetch_tournament_odds(tournament_id: str) -> pd.DataFrame:
    """
    Fetch betting odds for a tournament.

    Args:
        tournament_id: PGA Tour tournament ID (e.g., "R2026002")

    Returns:
        DataFrame with odds for all players
    """
    print(f"  Fetching odds for tournament {tournament_id}...")

    payload = {
        "operationName": "TournamentOddsToWin",
        "variables": {"tournamentId": tournament_id},
        "query": TOURNAMENT_ODDS_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)

        if resp.status_code != 200:
            print(f"    Error: HTTP {resp.status_code}")
            return pd.DataFrame()

        data = resp.json()

        if data.get("errors"):
            # PGA schema can vary; retry with conservative query.
            print("    Enhanced odds query failed; retrying fallback fields...")
            payload["query"] = TOURNAMENT_ODDS_QUERY_FALLBACK
            resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)
            if resp.status_code != 200:
                print(f"    Error: HTTP {resp.status_code} on fallback query")
                return pd.DataFrame()
            data = resp.json()
            if data.get("errors"):
                print(f"    GraphQL errors: {data['errors']}")
                return pd.DataFrame()

        odds_data = data.get("data", {}).get("tournamentOddsToWin")
        if not odds_data:
            print(f"    No odds data found")
            return pd.DataFrame()

        tournament_name = odds_data.get("tournamentName", tournament_id)
        players = _extract_players_from_odds_payload(odds_data)

        if not players:
            print(f"    No player odds found")
            return pd.DataFrame()

        # Build DataFrame
        records = []
        for p in players:
            player_id = _normalize_player_id(p.get("playerId", p.get("player_id", p.get("id"))))
            if not player_id:
                continue

            odds_raw = _extract_odds_value(p)
            odds_numeric = parse_american_odds(odds_raw)
            if odds_numeric is None:
                continue

            odds_str = f"+{odds_numeric}" if odds_numeric > 0 else str(odds_numeric)
            odds_numeric = parse_american_odds(odds_str)
            implied_prob = american_odds_to_probability(odds_str)

            records.append({
                "tournament_id": tournament_id,
                "tournament_name": tournament_name,
                "player_id": int(player_id),
                "odds_to_win": odds_str,
                "odds_numeric": odds_numeric,
                "implied_prob": implied_prob,
                "odds_swing": p.get("oddsSwing", ""),
                "odds_direction": p.get("oddsDirection", p.get("oddsSwing", "")),
                "odds_sort": p.get("oddsSort", p.get("oddsRank", 0)),
                "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            })

        df = pd.DataFrame(records)
        if df.empty:
            print(f"    No valid odds rows after parsing")
            return pd.DataFrame()

        # Calculate fair probabilities (remove vig)
        df["fair_prob"] = remove_vig(df["implied_prob"].tolist())

        print(f"    Found odds for {len(df)} players")

        return df

    except requests.RequestException as e:
        print(f"    Request error: {e}")
        return pd.DataFrame()


def fetch_player_names(tournament_id: str) -> dict:
    """
    Fetch player names from the leaderboard.

    Args:
        tournament_id: PGA Tour tournament ID

    Returns:
        Dict mapping player_id to player_name
    """
    print(f"  Fetching player names...")

    payload = {
        "operationName": "LeaderboardV3",
        "variables": {"id": tournament_id},
        "query": PLAYER_INFO_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=30)

        if resp.status_code != 200:
            return {}

        data = resp.json()
        players = data.get("data", {}).get("leaderboardV3", {}).get("players", [])

        name_map = {}
        for p in players:
            player_info = p.get("player", {})
            pid = _normalize_player_id(player_info.get("id", 0))
            player_id = int(pid) if pid else 0
            display_name = player_info.get("displayName", "")
            if player_id and display_name:
                name_map[player_id] = display_name

        print(f"    Found {len(name_map)} player names")
        return name_map

    except requests.RequestException:
        return {}


def fetch_and_merge_odds(tournament_id: str) -> pd.DataFrame:
    """
    Fetch odds and merge with player names.

    Args:
        tournament_id: PGA Tour tournament ID

    Returns:
        DataFrame with odds and player names
    """
    # Fetch odds
    odds_df = fetch_tournament_odds(tournament_id)

    if len(odds_df) == 0:
        cache_df = load_cached_odds_df(tournament_id)
        if not cache_df.empty:
            print(f"  Live odds unavailable; using cached odds file for {tournament_id}")
            return cache_df
        return pd.DataFrame()

    # Fetch player names
    name_map = fetch_player_names(tournament_id)

    # Merge names
    odds_df["player_name"] = odds_df["player_id"].map(name_map)

    # Fill missing names with "Unknown (ID)"
    odds_df["player_name"] = odds_df.apply(
        lambda row: row["player_name"] if pd.notna(row["player_name"])
        else f"Unknown ({row['player_id']})",
        axis=1
    )

    # Sort by odds (favorites first)
    odds_df = odds_df.sort_values("odds_sort")

    # Add rank
    odds_df["odds_rank"] = range(1, len(odds_df) + 1)

    return odds_df


# ============================================================================
# Main Function
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch golf betting odds from PGA Tour",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Fetch odds for American Express 2026
    python scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002

    # Fetch and save to specific file
    python scripts/scrapers/fetch_pga_odds.py --tournament-id R2026002 --output data/odds/amex_2026.csv

Tournament IDs:
    Format: R{year}{number} (e.g., R2026002 for American Express 2026)
    Find IDs on pgatour.com tournament URLs
        """
    )

    parser.add_argument("--tournament-id", required=True,
                       help="PGA Tour tournament ID (e.g., R2026002)")
    parser.add_argument("--output", type=str, default=None,
                       help="Output CSV path")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  PGA TOUR ODDS SCRAPER")
    print("=" * 60)

    # Fetch odds with player names
    df = fetch_and_merge_odds(args.tournament_id)

    if len(df) == 0:
        print("\n  No odds data found!")
        return 1

    # Add model-vs-book edge columns (if predictions available)
    df = add_model_edge_columns(df, args.tournament_id)

    # Determine output path for legacy/general odds file
    if args.output:
        output_path = Path(args.output)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"pga_odds_{args.tournament_id}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save legacy/general odds file
    df.to_csv(output_path, index=False)

    # Save dedicated FanDuel odds file for value-bet workflow
    fanduel_df = build_fanduel_odds_view(df)
    fanduel_output_path = OUTPUT_DIR / f"fanduel_odds_{args.tournament_id}.csv"
    fanduel_df.to_csv(fanduel_output_path, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("  ODDS SUMMARY")
    print("=" * 60)

    print(f"\n  Tournament: {df['tournament_name'].iloc[0]}")
    print(f"  Players: {len(df)}")

    # Total implied probability (shows vig)
    total_implied = df["implied_prob"].sum() * 100
    print(f"  Total implied prob: {total_implied:.1f}% (vig = {total_implied - 100:.1f}%)")

    print(f"\n  Top 15 Favorites:")
    print("-" * 60)

    top15 = df.head(15)
    for _, row in top15.iterrows():
        name = row["player_name"][:22].ljust(22)
        odds = row["odds_to_win"]
        prob = row["fair_prob"] * 100 if row["fair_prob"] else 0
        swing = row["odds_swing"]
        swing_icon = "↑" if swing == "UP" else "↓" if swing == "DOWN" else "→"
        print(f"    {name}  {odds:>8}  ({prob:5.2f}%)  {swing_icon}")

    if "edge_win_prob" in df.columns:
        value_count = int((df["edge_win_prob"] > 0).sum())
        with_model_count = int(df["edge_win_prob"].notna().sum())
        print(f"\n  Value edges ready: {value_count}/{with_model_count} players with positive edge")

    print(f"\n  Saved to: {output_path}")
    print(f"  Saved FanDuel view to: {fanduel_output_path}")

    return 0


if __name__ == "__main__":
    exit(main())
