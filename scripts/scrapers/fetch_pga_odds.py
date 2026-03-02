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
import base64
import json
import requests
import zlib
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

# ============================================================================
# Configuration
# ============================================================================

GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
PGA_ODDS_API_URL = "https://data-api.pgatour.com/odds/tournament"

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}

REST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
    "User-Agent": "Mozilla/5.0",
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

# DraftKings outright winner odds via PGA Tour's GraphQL proxy.
# Returns a compressed (gzip+base64) payload with 122 players, each having
# odds, oddsSort, oddsDirection (UP/DOWN/CONSTANT), and optionId.
DK_ODDS_COMPRESSED_QUERY = """
query oddsToWinCompressed($tournamentId: ID!) {
  oddsToWinCompressed(oddsToWinId: $tournamentId) {
    id
    payload
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

def fetch_tournament_odds(tournament_id: str, all_markets_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Fetch betting odds for a tournament.

    Args:
        tournament_id: PGA Tour tournament ID (e.g., "R2026002")

    Returns:
        DataFrame with odds for all players
    """
    print(f"  Fetching odds for tournament {tournament_id}...")

    if all_markets_df is None:
        all_markets_df = fetch_all_market_odds(tournament_id)
    if all_markets_df.empty:
        print("    No odds data found")
        return pd.DataFrame()

    winner_df = all_markets_df[all_markets_df["market_type"].astype(str) == "ODDS_TO_WIN"].copy()
    if winner_df.empty:
        print("    No outright winner market found")
        return pd.DataFrame()

    winner_df = winner_df.sort_values(["odds_sort", "implied_prob"], na_position="last").reset_index(drop=True)
    winner_df["fair_prob"] = remove_vig(winner_df["implied_prob"].tolist())
    winner_df["odds_rank"] = range(1, len(winner_df) + 1)

    legacy_cols = [
        "tournament_id",
        "tournament_name",
        "player_id",
        "player_name",
        "odds_to_win",
        "odds_numeric",
        "implied_prob",
        "fair_prob",
        "odds_swing",
        "odds_direction",
        "odds_sort",
        "odds_rank",
        "fetched_at",
    ]
    for col in legacy_cols:
        if col not in winner_df.columns:
            winner_df[col] = np.nan

    print(f"    Found odds for {len(winner_df)} players")
    return winner_df[legacy_cols]


def fetch_market_catalog(tournament_id: str) -> Dict[str, Any]:
    """Fetch available PGA/FanDuel betting markets for a tournament."""
    url = f"{PGA_ODDS_API_URL}/{tournament_id}"
    resp = requests.get(url, headers=REST_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def fetch_market_payload(tournament_id: str, market_id: Any) -> Dict[str, Any]:
    """Fetch one concrete market payload by market ID."""
    url = f"{PGA_ODDS_API_URL}/{tournament_id}/{market_id}"
    resp = requests.get(url, headers=REST_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _build_selection_label(entity: Dict[str, Any], players: List[Dict[str, Any]]) -> str:
    names = [str(p.get("displayName") or p.get("shortName") or "").strip() for p in players]
    names = [n for n in names if n]
    if names:
        return " / ".join(names)
    for key in ("displayName", "name", "label", "title"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _flatten_market_payload(
    tournament_id: str,
    market_meta: Dict[str, Any],
    market_payload: Dict[str, Any],
    fetched_at: str,
) -> List[Dict[str, Any]]:
    """Flatten PGA market payload into normalized row records."""
    rows: List[Dict[str, Any]] = []
    market_id = market_payload.get("marketId", market_meta.get("id"))
    market_name = market_payload.get("market", market_meta.get("name", ""))
    market_display_name = market_payload.get("marketDisplayName", market_meta.get("displayName", ""))
    market_type = market_payload.get("marketType", market_meta.get("marketType", ""))
    betting_provider = market_payload.get("bettingProvider", market_meta.get("book", ""))
    tournament_name = market_payload.get("tournamentName", tournament_id)

    sub_markets = market_payload.get("subMarkets") or []
    for sub_idx, sub_market in enumerate(sub_markets):
        sub_market_name = str(sub_market.get("subMarketName", "")).strip()
        odds_groups = sub_market.get("oddsDataGroup") or []
        for grp_idx, odds_group in enumerate(odds_groups):
            group_title = str(odds_group.get("title", "")).strip()
            odds_entries = odds_group.get("oddsData") or []
            for entry_idx, odds_entry in enumerate(odds_entries):
                selection_type = odds_entry.get("type", "")
                group_count = odds_entry.get("groupCount", 0)
                group = odds_entry.get("group") or []
                if not isinstance(group, list):
                    continue

                option_ids = [str(g.get("optionId", "")).strip() for g in group if isinstance(g, dict)]
                option_id = next((oid for oid in option_ids if oid), "")

                if int(group_count or 0) > 1:
                    bet_group_id = f"{market_id}|{sub_idx}|{grp_idx}|{entry_idx}"
                else:
                    bet_group_id = f"{market_id}|{sub_idx}|{grp_idx}|{option_id or 'single'}"

                entity_names = []
                for entity in group:
                    if not isinstance(entity, dict):
                        continue
                    entity_players = entity.get("players") or []
                    entity_names.append(_build_selection_label(entity, entity_players))

                for selection_index, entity in enumerate(group):
                    if not isinstance(entity, dict):
                        continue

                    players = entity.get("players") or []
                    selection_label = _build_selection_label(entity, players)
                    player_names = [str(p.get("displayName") or "").strip() for p in players if isinstance(p, dict)]
                    player_short_names = [str(p.get("shortName") or "").strip() for p in players if isinstance(p, dict)]
                    player_ids = [_normalize_player_id(p.get("playerId")) for p in players if isinstance(p, dict)]
                    player_ids = [pid for pid in player_ids if pid]
                    opponent_names = [n for i, n in enumerate(entity_names) if i != selection_index and n]

                    odds_value = entity.get("oddsValue")
                    odds_numeric = parse_american_odds(odds_value)

                    row = {
                        "tournament_id": tournament_id,
                        "tournament_name": tournament_name,
                        "market_id": market_id,
                        "market_name": market_name,
                        "market_display_name": market_display_name,
                        "market_type": market_type,
                        "betting_provider": betting_provider,
                        "submarket_name": sub_market_name,
                        "group_title": group_title,
                        "selection_type": selection_type,
                        "group_count": group_count,
                        "bet_group_id": bet_group_id,
                        "selection_index": selection_index,
                        "option_id": str(entity.get("optionId", "")).strip(),
                        "entity_id": str(entity.get("entityId", "")).strip(),
                        "selection_label": selection_label,
                        "player_ids": "|".join(str(pid) for pid in player_ids),
                        "player_id": player_ids[0] if len(player_ids) == 1 else None,
                        "player_names": " | ".join(n for n in player_names if n),
                        "player_name": player_names[0] if len(player_names) == 1 else selection_label,
                        "player_short_names": " | ".join(n for n in player_short_names if n),
                        "opponent_name": " vs ".join(opponent_names),
                        "odds_value": odds_value,
                        "odds_numeric": odds_numeric,
                        "implied_prob": american_to_implied_prob(odds_numeric),
                        "odd_direction": entity.get("oddDirection", ""),
                        "fetched_at": fetched_at,
                    }
                    rows.append(row)
    return rows


def fetch_all_market_odds(tournament_id: str) -> pd.DataFrame:
    """Fetch and normalize all PGA market odds for a tournament."""
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    try:
        catalog = fetch_market_catalog(tournament_id)
    except requests.RequestException as e:
        print(f"    Market catalog request error: {e}")
        return pd.DataFrame()

    available_markets = catalog.get("availableMarkets") or []
    if not available_markets:
        return pd.DataFrame()

    all_rows: List[Dict[str, Any]] = []
    print(f"    Available markets: {len(available_markets)}")
    for market_meta in available_markets:
        market_id = market_meta.get("id")
        market_name = market_meta.get("name", market_id)
        try:
            market_payload = fetch_market_payload(tournament_id, market_id)
        except requests.RequestException as e:
            print(f"    Skipping market {market_id} ({market_name}): {e}")
            continue

        rows = _flatten_market_payload(tournament_id, market_meta, market_payload, fetched_at)
        if rows:
            all_rows.extend(rows)
            print(f"      {market_id}: {market_name} -> {len(rows)} rows")
        else:
            print(f"      {market_id}: {market_name} -> no rows")

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    # Remove vig within each discrete betting group.
    df["fair_prob"] = df.groupby("bet_group_id")["implied_prob"].transform(
        lambda s: pd.Series(remove_vig(s.tolist()), index=s.index)
    )

    # Preserve legacy naming for outright workflow.
    df["odds_to_win"] = np.where(df["market_type"] == "ODDS_TO_WIN", df["odds_value"], np.nan)
    df["odds_swing"] = df["odd_direction"]
    df["odds_sort"] = np.where(
        df["market_type"] == "ODDS_TO_WIN",
        pd.to_numeric(df["implied_prob"], errors="coerce") * -1.0,
        np.nan,
    )

    winner_mask = df["market_type"] == "ODDS_TO_WIN"
    if winner_mask.any():
        df.loc[winner_mask, "odds_sort"] = (
            df.loc[winner_mask, "odds_numeric"].rank(method="first", ascending=True).astype(float)
        )

    return df


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


def fetch_dk_odds_compressed(tournament_id: str) -> pd.DataFrame:
    """
    Fetch DraftKings outright winner odds via PGA Tour's GraphQL proxy.

    Uses the ``oddsToWinCompressed`` query which returns a gzip+base64 payload
    containing DK odds for all field players, including live movement direction
    (UP / DOWN / CONSTANT).  Player names are NOT included — caller must join
    against a name map (e.g. from fetch_player_names).

    Returns
    -------
    DataFrame with columns:
        player_id, dk_odds, dk_odds_numeric, dk_implied_prob,
        dk_odds_direction, dk_option_id, fetched_at
    or an empty DataFrame on failure.
    """
    payload = {
        "operationName": "oddsToWinCompressed",
        "variables": {"tournamentId": tournament_id},
        "query": DK_ODDS_COMPRESSED_QUERY,
    }

    try:
        resp = requests.post(GRAPHQL_URL, headers=DEFAULT_HEADERS, json=payload, timeout=20)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        if data.get("errors"):
            return pd.DataFrame()

        result = (data.get("data") or {}).get("oddsToWinCompressed") or {}
        b64_payload = result.get("payload", "")
        if not b64_payload:
            return pd.DataFrame()

        # Decompress: gzip-encoded binary → JSON
        raw = base64.b64decode(b64_payload)
        try:
            decompressed = zlib.decompress(raw, 16 + zlib.MAX_WBITS)
        except Exception:
            decompressed = zlib.decompress(raw)
        inner = json.loads(decompressed)

        players = inner.get("players") or []
        if not players:
            return pd.DataFrame()

        fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        records = []
        for p in players:
            pid = _normalize_player_id(p.get("playerId"))
            if not pid:
                continue
            odds_raw = p.get("odds", "")
            odds_num = parse_american_odds(odds_raw)
            if odds_num is None:
                continue
            records.append({
                "player_id":        int(pid),
                "dk_odds":          odds_raw,
                "dk_odds_numeric":  odds_num,
                "dk_implied_prob":  american_to_implied_prob(odds_num),
                "dk_odds_direction": p.get("oddsDirection", ""),
                "dk_option_id":     p.get("optionId", ""),
                "fetched_at":       fetched_at,
            })

        df = pd.DataFrame(records)
        if df.empty:
            return df

        # Remove vig — normalize implied probs so they sum to 1
        df["dk_fair_prob"] = remove_vig(df["dk_implied_prob"].tolist())
        df = df.sort_values("dk_odds_numeric")
        print(f"    DK (compressed): {len(df)} players  "
              f"UP={int((df['dk_odds_direction']=='UP').sum())}  "
              f"DOWN={int((df['dk_odds_direction']=='DOWN').sum())}  "
              f"CONSTANT={int((df['dk_odds_direction']=='CONSTANT').sum())}")
        return df

    except Exception as e:
        print(f"    DK compressed fetch error: {e}")
        return pd.DataFrame()


def fetch_and_merge_odds(tournament_id: str, all_markets_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Fetch odds and merge with player names.

    Args:
        tournament_id: PGA Tour tournament ID

    Returns:
        DataFrame with odds and player names
    """
    # Fetch odds
    odds_df = fetch_tournament_odds(tournament_id, all_markets_df=all_markets_df)

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


def fetch_and_merge_all_markets(tournament_id: str, all_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Fetch all PGA market odds and backfill any missing names from leaderboard."""
    if all_df is None:
        all_df = fetch_all_market_odds(tournament_id)
    if all_df.empty:
        return all_df

    if all_df["player_name"].fillna("").eq("").any() or all_df["player_name"].astype(str).str.startswith("Unknown").any():
        name_map = fetch_player_names(tournament_id)
        if name_map:
            missing_mask = all_df["player_id"].notna() & (
                all_df["player_name"].fillna("").eq("") |
                all_df["player_name"].astype(str).str.startswith("Unknown")
            )
            all_df.loc[missing_mask, "player_name"] = all_df.loc[missing_mask, "player_id"].map(name_map).fillna(
                all_df.loc[missing_mask, "player_name"]
            )
    return all_df


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

    all_markets_raw = fetch_all_market_odds(args.tournament_id)
    all_markets_df = fetch_and_merge_all_markets(args.tournament_id, all_df=all_markets_raw)
    df = fetch_and_merge_odds(args.tournament_id, all_markets_df=all_markets_df)

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

    if not all_markets_df.empty:
        all_markets_output_path = OUTPUT_DIR / f"pga_market_odds_{args.tournament_id}.csv"
        all_markets_df.to_csv(all_markets_output_path, index=False)
        print(f"  Saved all PGA markets to: {all_markets_output_path}")

    # Save dedicated FanDuel odds file for value-bet workflow
    fanduel_df = build_fanduel_odds_view(df)
    fanduel_output_path = OUTPUT_DIR / f"fanduel_odds_{args.tournament_id}.csv"
    fanduel_df.to_csv(fanduel_output_path, index=False)

    # Fetch DK outright odds via PGA Tour compressed endpoint (adds movement direction)
    print("\n  Fetching DK odds (PGA Tour compressed endpoint)...")
    dk_df = fetch_dk_odds_compressed(args.tournament_id)
    if not dk_df.empty:
        # Merge player names from the FanDuel fetch
        name_map = df.set_index("player_id")["player_name"].to_dict() if "player_name" in df.columns else {}
        dk_df["player_name"] = dk_df["player_id"].map(name_map).fillna("")
        dk_output_path = OUTPUT_DIR / f"dk_odds_{args.tournament_id}.csv"
        dk_df.to_csv(dk_output_path, index=False)
        print(f"  Saved DK odds to: {dk_output_path}")

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
