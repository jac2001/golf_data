#!/usr/bin/env python3
"""
Expert Picks Viewer
===================
Shows expert picks for the current tournament.

Usage:
    python expert_picks_viewer.py                  # All expert picks
    python expert_picks_viewer.py --consensus      # Only consensus picks (2+ sources)
    python expert_picks_viewer.py --by-source      # Group by source
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent.parent / "data"
EXPERT_PICKS_DIR = DATA_DIR / "expert_picks"


def find_latest_picks() -> Path:
    """Find the most recent expert picks file."""
    if not EXPERT_PICKS_DIR.exists():
        return None
    
    # Try expert_picks_latest.csv first
    latest = EXPERT_PICKS_DIR / "expert_picks_latest.csv"
    if latest.exists():
        return latest
    
    # Otherwise find most recent
    files = sorted(EXPERT_PICKS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    files = [f for f in files if not f.name.startswith(".")]
    return files[0] if files else None


def load_expert_picks() -> pd.DataFrame:
    """Load expert picks data."""
    picks_file = find_latest_picks()
    if picks_file is None:
        return pd.DataFrame()
    
    df = pd.read_csv(picks_file)
    return df


def display_all_picks():
    """Display all expert picks."""
    df = load_expert_picks()
    
    if df.empty:
        print("No expert picks data found")
        return
    
    tournament = df['tournament'].iloc[0] if 'tournament' in df.columns else "Unknown"
    scraped = df['scraped_date'].iloc[0] if 'scraped_date' in df.columns else ""
    
    print()
    print("=" * 70)
    print(f"  EXPERT PICKS: {tournament.upper()}")
    print("=" * 70)
    if scraped:
        try:
            dt = datetime.fromisoformat(scraped)
            print(f"  Last updated: {dt.strftime('%b %d, %Y %H:%M')}")
        except:
            pass
    print("=" * 70)
    print()
    
    # Group by pick type
    pick_types = {
        'favorite': '🏆 FAVORITES',
        'model_pick': '🤖 MODEL PICKS',
        'course_specialist': '🏌️ COURSE SPECIALISTS',
        'value_pick': '💎 VALUE PICKS',
        'sleeper': '😴 SLEEPERS',
        'longshot': '🎯 LONGSHOTS'
    }
    
    for pick_type, header in pick_types.items():
        type_picks = df[df['pick_type'] == pick_type] if 'pick_type' in df.columns else pd.DataFrame()
        
        if not type_picks.empty:
            print(f"  {header}")
            print("  " + "-" * 65)
            
            for _, row in type_picks.iterrows():
                player = row.get('player_name', 'Unknown')
                source = row.get('source', '')
                note = row.get('note', '')
                consensus = row.get('consensus_count', 1)
                
                consensus_str = f"({consensus}x)" if consensus > 1 else ""
                
                print(f"  • {player:<25} {consensus_str:<5} [{source}]")
                if note and pd.notna(note):
                    print(f"    └─ {note[:60]}")
            
            print()
    
    # Show any remaining picks not in categories
    other_picks = df[~df['pick_type'].isin(pick_types.keys())] if 'pick_type' in df.columns else df
    if not other_picks.empty:
        print("  📋 OTHER PICKS")
        print("  " + "-" * 65)
        for _, row in other_picks.iterrows():
            player = row.get('player_name', 'Unknown')
            source = row.get('source', '')
            print(f"  • {player:<25} [{source}]")
        print()


def display_consensus_picks():
    """Display only consensus picks (multiple sources)."""
    df = load_expert_picks()
    
    if df.empty:
        print("No expert picks data found")
        return
    
    tournament = df['tournament'].iloc[0] if 'tournament' in df.columns else "Unknown"
    
    print()
    print("=" * 70)
    print(f"  CONSENSUS PICKS: {tournament.upper()}")
    print("  (Players picked by 2+ sources)")
    print("=" * 70)
    print()
    
    # Count picks per player
    if 'consensus_count' in df.columns:
        consensus = df[df['consensus_count'] >= 2].copy()
    else:
        player_counts = df['player_name'].value_counts()
        consensus_players = player_counts[player_counts >= 2].index.tolist()
        consensus = df[df['player_name'].isin(consensus_players)].copy()
    
    if consensus.empty:
        print("  No consensus picks found (no player picked by 2+ sources)")
        return
    
    # Deduplicate and show
    seen = set()
    print(f"  {'Player':<30} {'Count':<8} {'Sources':<30}")
    print("  " + "-" * 65)
    
    for _, row in consensus.iterrows():
        player = row.get('player_name', 'Unknown')
        if player in seen:
            continue
        seen.add(player)
        
        count = row.get('consensus_count', 1)
        sources = df[df['player_name'] == player]['source'].unique()
        sources_str = ", ".join(sources[:3])
        
        print(f"  ⭐ {player:<28} {count:<8} {sources_str:<30}")
    
    print()


def display_by_source():
    """Display picks grouped by source."""
    df = load_expert_picks()
    
    if df.empty:
        print("No expert picks data found")
        return
    
    tournament = df['tournament'].iloc[0] if 'tournament' in df.columns else "Unknown"
    
    print()
    print("=" * 70)
    print(f"  EXPERT PICKS BY SOURCE: {tournament.upper()}")
    print("=" * 70)
    print()
    
    sources = df['source'].unique() if 'source' in df.columns else []
    
    for source in sources:
        source_picks = df[df['source'] == source]
        
        print(f"  📰 {source.upper()}")
        print("  " + "-" * 65)
        
        for _, row in source_picks.iterrows():
            player = row.get('player_name', 'Unknown')
            pick_type = row.get('pick_type', '')
            note = row.get('note', '')
            
            type_icon = {
                'favorite': '🏆',
                'model_pick': '🤖',
                'course_specialist': '🏌️',
                'value_pick': '💎',
                'sleeper': '😴',
                'longshot': '🎯'
            }.get(pick_type, '•')
            
            print(f"  {type_icon} {player:<30} [{pick_type}]")
            if note and pd.notna(note):
                print(f"      └─ {note[:55]}")
        
        print()


def main():
    parser = argparse.ArgumentParser(description="View expert picks")
    parser.add_argument("--consensus", "-c", action="store_true", help="Show only consensus picks")
    parser.add_argument("--by-source", "-s", action="store_true", help="Group by source")
    
    args = parser.parse_args()
    
    if args.consensus:
        display_consensus_picks()
    elif args.by_source:
        display_by_source()
    else:
        display_all_picks()


if __name__ == "__main__":
    main()
