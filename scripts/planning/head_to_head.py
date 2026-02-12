#!/usr/bin/env python3
"""
Head-to-Head Player Comparison
==============================
Compare two players side-by-side.

Usage:
    python head_to_head.py "Scottie Scheffler" "Rory McIlroy"
    python head_to_head.py "Xander Schauffele" "Collin Morikawa"
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
import json

DATA_DIR = Path(__file__).parent.parent.parent / "data"
RANKINGS_FILE = DATA_DIR / "rankings" / "owgr_2026.csv"
USAGE_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
ODDS_DIR = DATA_DIR / "odds"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"


def load_rankings() -> pd.DataFrame:
    """Load world rankings."""
    if RANKINGS_FILE.exists():
        return pd.read_csv(RANKINGS_FILE)
    return pd.DataFrame()


def load_strokes_gained() -> pd.DataFrame:
    """Load strokes gained data."""
    years = [2024, 2025, 2026]
    dfs = []
    for year in years:
        path = DATA_DIR / "historical" / f"tournament_stats_{year}.csv"
        if path.exists():
            dfs.append(pd.read_csv(path))
    
    if not dfs:
        return pd.DataFrame()
    
    df = pd.concat(dfs, ignore_index=True)
    
    # Filter for SG stats with Avg component
    sg_stats = [
        "Strokes Gained: Total",
        "Strokes Gained: Off-the-Tee", 
        "Strokes Gained: Approach",
        "Strokes Gained: Putting"
    ]
    
    df = df[
        (df["stat_name"].isin(sg_stats)) & 
        (df["stat_component"] == "Avg")
    ].copy()
    
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")
    return df


def load_recent_results() -> pd.DataFrame:
    """Load recent tournament results."""
    years = [2025, 2026]
    dfs = []
    for year in years:
        path = DATA_DIR / "historical" / f"leaderboards_{year}.csv"
        if path.exists():
            dfs.append(pd.read_csv(path))
    
    if not dfs:
        return pd.DataFrame()
    
    return pd.concat(dfs, ignore_index=True)


def load_usage() -> dict:
    """Load usage tracker data."""
    if USAGE_FILE.exists():
        with open(USAGE_FILE) as f:
            return json.load(f)
    return {"picks": {}}


def load_odds() -> pd.DataFrame:
    """Load current odds."""
    if not ODDS_DIR.exists():
        return pd.DataFrame()
    
    files = sorted(ODDS_DIR.glob("pga_odds_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    if files:
        return pd.read_csv(files[0])
    return pd.DataFrame()


def find_player(name: str, df: pd.DataFrame, col: str = "player_name") -> pd.DataFrame:
    """Find player by fuzzy name match."""
    if df.empty or col not in df.columns:
        return pd.DataFrame()
    
    # Try exact match first
    exact = df[df[col].str.lower() == name.lower()]
    if not exact.empty:
        return exact
    
    # Try contains
    contains = df[df[col].str.lower().str.contains(name.lower(), na=False)]
    return contains


def get_player_sg(name: str, sg_df: pd.DataFrame) -> dict:
    """Get strokes gained breakdown for a player."""
    player_data = find_player(name, sg_df)
    
    if player_data.empty:
        return {}
    
    sg = {}
    stat_map = {
        "Strokes Gained: Total": "total",
        "Strokes Gained: Off-the-Tee": "ott",
        "Strokes Gained: Approach": "app",
        "Strokes Gained: Putting": "putt"
    }
    
    for stat_name, key in stat_map.items():
        stat_data = player_data[player_data["stat_name"] == stat_name]
        if not stat_data.empty:
            sg[key] = stat_data["stat_value"].mean()
    
    return sg


def get_player_results(name: str, results_df: pd.DataFrame, limit: int = 5) -> list:
    """Get recent results for a player."""
    player_data = find_player(name, results_df)
    
    if player_data.empty:
        return []
    
    player_data = player_data.sort_values(["year", "tournament_id"], ascending=[False, False])
    
    results = []
    for _, row in player_data.head(limit).iterrows():
        results.append({
            "tournament": row.get("tournament_name", "Unknown")[:25],
            "position": row.get("position", "—"),
            "to_par": row.get("to_par", "—")
        })
    
    return results


def get_player_odds(name: str, odds_df: pd.DataFrame) -> dict:
    """Get odds for a player."""
    player_data = find_player(name, odds_df)
    
    if player_data.empty:
        return {}
    
    row = player_data.iloc[0]
    return {
        "odds": row.get("odds_to_win", "N/A"),
        "implied_prob": row.get("implied_prob", 0),
        "rank": row.get("odds_rank", 0)
    }


def get_player_usage(name: str, usage_data: dict) -> dict:
    """Get usage status for a player."""
    picks = usage_data.get("picks", {})
    
    # Try to find player (case insensitive)
    for player, info in picks.items():
        if name.lower() in player.lower() or player.lower() in name.lower():
            return {
                "times_used": info.get("times_used", 0),
                "remaining": info.get("remaining_uses", 3),
                "points": info.get("total_points", 0)
            }
    
    return {"times_used": 0, "remaining": 3, "points": 0}


def format_sg(val: float) -> str:
    """Format strokes gained value."""
    if val is None:
        return "  —  "
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}"


def format_bar(val: float, width: int = 10) -> str:
    """Create visual bar for SG comparison."""
    if val is None:
        return " " * width
    
    # Scale -1 to +1 to 0-width
    normalized = (val + 1) / 2
    normalized = max(0, min(1, normalized))
    filled = int(normalized * width)
    
    return "█" * filled + "░" * (width - filled)


def compare_players(player1: str, player2: str):
    """Compare two players head-to-head."""
    # Load all data
    rankings = load_rankings()
    sg_df = load_strokes_gained()
    results_df = load_recent_results()
    odds_df = load_odds()
    usage_data = load_usage()
    
    # Get player data
    p1_rank = find_player(player1, rankings)
    p2_rank = find_player(player2, rankings)
    
    p1_name = p1_rank.iloc[0]["player_name"] if not p1_rank.empty else player1
    p2_name = p2_rank.iloc[0]["player_name"] if not p2_rank.empty else player2
    
    p1_world_rank = int(p1_rank.iloc[0]["world_rank"]) if not p1_rank.empty else "NR"
    p2_world_rank = int(p2_rank.iloc[0]["world_rank"]) if not p2_rank.empty else "NR"
    
    p1_sg = get_player_sg(player1, sg_df)
    p2_sg = get_player_sg(player2, sg_df)
    
    p1_results = get_player_results(player1, results_df)
    p2_results = get_player_results(player2, results_df)
    
    p1_odds = get_player_odds(player1, odds_df)
    p2_odds = get_player_odds(player2, odds_df)
    
    p1_usage = get_player_usage(player1, usage_data)
    p2_usage = get_player_usage(player2, usage_data)
    
    # Display comparison
    print()
    print("=" * 75)
    print("  HEAD-TO-HEAD COMPARISON")
    print("=" * 75)
    print()
    
    # Header with names
    col_width = 30
    print(f"  {'PLAYER':<15} {p1_name:^{col_width}} {p2_name:^{col_width}}")
    print("  " + "-" * 70)
    
    # World Rank
    p1_wr = f"#{p1_world_rank}" if isinstance(p1_world_rank, int) else p1_world_rank
    p2_wr = f"#{p2_world_rank}" if isinstance(p2_world_rank, int) else p2_world_rank
    winner = "◀" if (isinstance(p1_world_rank, int) and isinstance(p2_world_rank, int) and p1_world_rank < p2_world_rank) else ""
    winner2 = "◀" if (isinstance(p1_world_rank, int) and isinstance(p2_world_rank, int) and p2_world_rank < p1_world_rank) else ""
    print(f"  {'World Rank':<15} {p1_wr:^{col_width}} {p2_wr:^{col_width}}")
    
    # Odds
    p1_odds_str = str(p1_odds.get("odds", "N/A"))
    p2_odds_str = str(p2_odds.get("odds", "N/A"))
    print(f"  {'Odds':<15} {p1_odds_str:^{col_width}} {p2_odds_str:^{col_width}}")
    
    # Usage
    p1_use = f"{p1_usage['remaining']}/3 remaining"
    p2_use = f"{p2_usage['remaining']}/3 remaining"
    print(f"  {'Usage':<15} {p1_use:^{col_width}} {p2_use:^{col_width}}")
    
    print()
    print("  " + "-" * 70)
    print("  STROKES GAINED (per round avg)")
    print("  " + "-" * 70)
    
    # SG Breakdown
    sg_categories = [
        ("SG: Total", "total"),
        ("SG: Off-Tee", "ott"),
        ("SG: Approach", "app"),
        ("SG: Putting", "putt")
    ]
    
    for label, key in sg_categories:
        p1_val = p1_sg.get(key)
        p2_val = p2_sg.get(key)
        
        p1_str = format_sg(p1_val)
        p2_str = format_sg(p2_val)
        
        # Determine winner
        if p1_val is not None and p2_val is not None:
            if p1_val > p2_val + 0.05:
                p1_str = f"✓ {p1_str}"
                p2_str = f"  {p2_str}"
            elif p2_val > p1_val + 0.05:
                p1_str = f"  {p1_str}"
                p2_str = f"✓ {p2_str}"
            else:
                p1_str = f"  {p1_str}"
                p2_str = f"  {p2_str}"
        else:
            p1_str = f"  {p1_str}"
            p2_str = f"  {p2_str}"
        
        print(f"  {label:<15} {p1_str:^{col_width}} {p2_str:^{col_width}}")
    
    # Recent Results
    print()
    print("  " + "-" * 70)
    print("  RECENT RESULTS")
    print("  " + "-" * 70)
    
    max_results = max(len(p1_results), len(p2_results), 1)
    for i in range(min(max_results, 5)):
        p1_res = ""
        p2_res = ""
        
        if i < len(p1_results):
            r = p1_results[i]
            p1_res = f"{r['position']:<5} {r['tournament']}"
        
        if i < len(p2_results):
            r = p2_results[i]
            p2_res = f"{r['position']:<5} {r['tournament']}"
        
        print(f"  {'':<15} {p1_res:<{col_width}} {p2_res:<{col_width}}")
    
    # Summary
    print()
    print("  " + "-" * 70)
    print("  VERDICT")
    print("  " + "-" * 70)
    
    p1_wins = 0
    p2_wins = 0
    
    # Count SG wins
    for _, key in sg_categories:
        p1_val = p1_sg.get(key)
        p2_val = p2_sg.get(key)
        if p1_val is not None and p2_val is not None:
            if p1_val > p2_val + 0.05:
                p1_wins += 1
            elif p2_val > p1_val + 0.05:
                p2_wins += 1
    
    # World rank
    if isinstance(p1_world_rank, int) and isinstance(p2_world_rank, int):
        if p1_world_rank < p2_world_rank:
            p1_wins += 1
        elif p2_world_rank < p1_world_rank:
            p2_wins += 1
    
    if p1_wins > p2_wins:
        print(f"  ➤ {p1_name} has the edge ({p1_wins}-{p2_wins})")
    elif p2_wins > p1_wins:
        print(f"  ➤ {p2_name} has the edge ({p2_wins}-{p1_wins})")
    else:
        print(f"  ➤ Too close to call ({p1_wins}-{p2_wins})")
    
    # Usage recommendation
    if p1_usage['remaining'] == 0:
        print(f"  ⚠️  {p1_name} has no uses remaining!")
    if p2_usage['remaining'] == 0:
        print(f"  ⚠️  {p2_name} has no uses remaining!")
    
    print()


def main():
    parser = argparse.ArgumentParser(description="Compare two players head-to-head")
    parser.add_argument("player1", help="First player name")
    parser.add_argument("player2", help="Second player name")
    
    args = parser.parse_args()
    compare_players(args.player1, args.player2)


if __name__ == "__main__":
    main()
