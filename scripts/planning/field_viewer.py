#!/usr/bin/env python3
"""
Field Viewer
============
Shows the field for a tournament with world rankings.

Usage:
    python field_viewer.py                           # Current week's field
    python field_viewer.py --tournament "Farmers"    # Specific tournament
    python field_viewer.py --top 30                  # Top 30 by world rank
"""

import argparse
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
FIELDS_DIR = DATA_DIR / "fields"
RANKINGS_FILE = DATA_DIR / "rankings" / "owgr_2026.csv"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"


def get_current_tournament() -> str:
    """Get current week's tournament name."""
    from datetime import datetime

    if not SCHEDULE_FILE.exists():
        return None

    schedule = pd.read_csv(SCHEDULE_FILE)
    today = datetime.now().strftime('%Y-%m-%d')

    # Find current or next tournament
    upcoming = schedule[schedule['start_date'] >= today]
    if not upcoming.empty:
        return upcoming.iloc[0]['tournament_name']

    return None


def find_field_file(tournament_name: str) -> Path:
    """Find the field file for a tournament."""
    if not FIELDS_DIR.exists():
        return None

    # Normalize tournament name for matching
    t_lower = tournament_name.lower().replace(" ", "_").replace("-", "_")

    # Try exact match first
    for f in FIELDS_DIR.glob("*.csv"):
        if f.name.startswith("."):
            continue
        f_lower = f.stem.lower().replace("-", "_")
        if t_lower in f_lower or f_lower in t_lower:
            return f

    # Try partial match
    for f in FIELDS_DIR.glob("*.csv"):
        if f.name.startswith("."):
            continue
        # Check if any word matches
        t_words = set(t_lower.split("_"))
        f_words = set(f.stem.lower().replace("-", "_").split("_"))
        if len(t_words & f_words) >= 2:
            return f

    # Return most recent file as fallback
    files = sorted(FIELDS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    files = [f for f in files if not f.name.startswith(".")]
    return files[0] if files else None


def load_rankings() -> pd.DataFrame:
    """Load world rankings."""
    if RANKINGS_FILE.exists():
        return pd.read_csv(RANKINGS_FILE)
    return pd.DataFrame()


def load_field(tournament_name: str = None) -> tuple:
    """Load field for a tournament, joined with rankings."""
    if tournament_name is None:
        tournament_name = get_current_tournament()

    if tournament_name is None:
        return pd.DataFrame(), "Unknown"

    field_file = find_field_file(tournament_name)
    if field_file is None:
        return pd.DataFrame(), tournament_name

    # Load field
    field_df = pd.read_csv(field_file)

    # Normalize column names
    field_df.columns = [c.lower().replace(" ", "_") for c in field_df.columns]

    # Ensure player_name column exists
    if 'player_name' not in field_df.columns:
        if 'name' in field_df.columns:
            field_df['player_name'] = field_df['name']
        elif 'player' in field_df.columns:
            field_df['player_name'] = field_df['player']

    # Load and join rankings
    rankings = load_rankings()
    if not rankings.empty:
        # Join on player_id if available, otherwise player_name
        if 'player_id' in field_df.columns and 'player_id' in rankings.columns:
            field_df = field_df.merge(
                rankings[['player_id', 'world_rank']],
                on='player_id',
                how='left'
            )
        else:
            # Try name matching
            rankings['name_lower'] = rankings['player_name'].str.lower()
            field_df['name_lower'] = field_df['player_name'].str.lower()
            field_df = field_df.merge(
                rankings[['name_lower', 'world_rank']],
                on='name_lower',
                how='left'
            )
            if 'name_lower' in field_df.columns:
                field_df.drop('name_lower', axis=1, inplace=True)

    # Fill missing ranks with high number
    if 'world_rank' in field_df.columns:
        field_df['world_rank'] = field_df['world_rank'].fillna(999).astype(int)
    else:
        field_df['world_rank'] = 999

    return field_df, tournament_name


def display_field(tournament_name: str = None, top_n: int = None):
    """Display the field for a tournament."""
    field_df, tourney = load_field(tournament_name)

    if field_df.empty:
        print(f"No field data found for: {tourney}")
        return

    # Sort by world rank
    field_df = field_df.sort_values('world_rank')

    total = len(field_df)
    top_10 = len(field_df[field_df['world_rank'] <= 10])
    top_30 = len(field_df[field_df['world_rank'] <= 30])
    top_50 = len(field_df[field_df['world_rank'] <= 50])

    if top_n:
        field_df = field_df.head(top_n)

    print()
    print("=" * 60)
    print(f"  FIELD: {tourney.upper()}")
    print("=" * 60)
    print(f"  Total Players: {total}")
    print(f"  Top 10: {top_10} | Top 30: {top_30} | Top 50: {top_50}")
    print("=" * 60)
    print()
    print(f"  {'#':<5} {'Player':<35} {'World Rank':<12}")
    print("  " + "-" * 55)

    for i, row in enumerate(field_df.itertuples(), 1):
        rank_display = f"#{row.world_rank}" if row.world_rank < 999 else "NR"

        # Tier indicator
        if row.world_rank <= 10:
            tier = "⭐"
        elif row.world_rank <= 30:
            tier = "★"
        elif row.world_rank <= 50:
            tier = "•"
        else:
            tier = " "

        print(f"  {i:<5} {row.player_name:<35} {tier} {rank_display:<10}")

    print()


def main():
    parser = argparse.ArgumentParser(description="View tournament field")
    parser.add_argument("--tournament", "-t", help="Tournament name")
    parser.add_argument("--top", type=int, help="Show only top N by world rank")

    args = parser.parse_args()
    display_field(args.tournament, args.top)


if __name__ == "__main__":
    main()
