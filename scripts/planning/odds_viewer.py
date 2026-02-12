#!/usr/bin/env python3
"""
Odds Viewer
===========
Shows betting odds for the current tournament.

Usage:
    python odds_viewer.py                    # Top 30 by odds
    python odds_viewer.py --favorites 10    # Top 10 favorites
    python odds_viewer.py --longshots        # Best longshots (50+ odds)
    python odds_viewer.py --value            # Model vs Vegas value
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ODDS_DIR = DATA_DIR / "odds"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"


def get_current_tournament_id() -> str:
    """Get current tournament ID."""
    if not SCHEDULE_FILE.exists():
        return None
    
    schedule = pd.read_csv(SCHEDULE_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    
    upcoming = schedule[schedule['start_date'] >= today]
    if not upcoming.empty and 'tournament_id' in upcoming.columns:
        return upcoming.iloc[0]['tournament_id']
    
    return None


def find_odds_file(tournament_id: str = None) -> Path:
    """Find odds file for tournament."""
    if not ODDS_DIR.exists():
        return None
    
    if tournament_id:
        target = ODDS_DIR / f"pga_odds_{tournament_id}.csv"
        if target.exists():
            return target
    
    # Return most recent
    files = sorted(ODDS_DIR.glob("pga_odds_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_odds() -> pd.DataFrame:
    """Load odds data."""
    tournament_id = get_current_tournament_id()
    odds_file = find_odds_file(tournament_id)
    
    if odds_file is None:
        return pd.DataFrame()
    
    return pd.read_csv(odds_file)


def display_favorites(top_n: int = 30):
    """Display top favorites by odds."""
    df = load_odds()
    
    if df.empty:
        print("No odds data found")
        return
    
    tournament = df['tournament_name'].iloc[0] if 'tournament_name' in df.columns else "Unknown"
    
    # Sort by odds rank or odds numeric
    if 'odds_rank' in df.columns:
        df = df.sort_values('odds_rank')
    elif 'odds_numeric' in df.columns:
        df = df.sort_values('odds_numeric')
    
    df = df.head(top_n)
    
    print()
    print("=" * 70)
    print(f"  BETTING ODDS: {tournament.upper()}")
    print("=" * 70)
    print(f"  Top {len(df)} Favorites")
    print("=" * 70)
    print()
    print(f"  {'#':<4} {'Player':<28} {'Odds':<10} {'Impl %':<10} {'Trend':<8}")
    print("  " + "-" * 65)
    
    for i, row in enumerate(df.itertuples(), 1):
        player = row.player_name if hasattr(row, 'player_name') else "Unknown"
        odds = row.odds_to_win if hasattr(row, 'odds_to_win') else "N/A"
        impl_prob = row.implied_prob if hasattr(row, 'implied_prob') else 0
        swing = row.odds_swing if hasattr(row, 'odds_swing') else ""
        
        # Trend indicator
        if swing == "UP":
            trend = "📈"
        elif swing == "DOWN":
            trend = "📉"
        else:
            trend = "➡️"
        
        impl_pct = f"{impl_prob*100:.1f}%" if impl_prob else "—"
        
        print(f"  {i:<4} {player:<28} {odds:<10} {impl_pct:<10} {trend:<8}")
    
    print()


def display_longshots():
    """Display best longshots (high odds)."""
    df = load_odds()
    
    if df.empty:
        print("No odds data found")
        return
    
    tournament = df['tournament_name'].iloc[0] if 'tournament_name' in df.columns else "Unknown"
    
    # Filter for longshots (odds >= 5000 or +5000)
    if 'odds_numeric' in df.columns:
        longshots = df[df['odds_numeric'] >= 5000].copy()
        longshots = longshots.sort_values('odds_numeric')
    else:
        longshots = df.tail(30)
    
    print()
    print("=" * 70)
    print(f"  LONGSHOTS: {tournament.upper()}")
    print("  (Odds +5000 or longer)")
    print("=" * 70)
    print()
    
    if longshots.empty:
        print("  No longshots found at +5000 or longer")
        return
    
    print(f"  {'#':<4} {'Player':<28} {'Odds':<12} {'Impl %':<10}")
    print("  " + "-" * 55)
    
    for i, row in enumerate(longshots.head(20).itertuples(), 1):
        player = row.player_name if hasattr(row, 'player_name') else "Unknown"
        odds = row.odds_to_win if hasattr(row, 'odds_to_win') else "N/A"
        impl_prob = row.implied_prob if hasattr(row, 'implied_prob') else 0
        
        impl_pct = f"{impl_prob*100:.2f}%" if impl_prob else "—"
        
        print(f"  {i:<4} {player:<28} {odds:<12} {impl_pct:<10}")
    
    print()


def display_value():
    """Display value picks (model vs Vegas)."""
    df = load_odds()
    
    if df.empty:
        print("No odds data found")
        return
    
    tournament = df['tournament_name'].iloc[0] if 'tournament_name' in df.columns else "Unknown"
    
    # Check if we have fair_prob (model probability)
    if 'fair_prob' not in df.columns:
        print("No model probability data available for value comparison")
        return
    
    # Calculate edge: fair_prob - implied_prob
    df['edge'] = df['fair_prob'] - df['implied_prob']
    
    # Get top value picks (positive edge)
    value_picks = df[df['edge'] > 0].sort_values('edge', ascending=False).head(15)
    
    print()
    print("=" * 70)
    print(f"  VALUE PICKS: {tournament.upper()}")
    print("  (Model probability > Vegas implied probability)")
    print("=" * 70)
    print()
    
    if value_picks.empty:
        print("  No positive edge picks found")
        return
    
    print(f"  {'#':<4} {'Player':<25} {'Odds':<10} {'Vegas':<8} {'Model':<8} {'Edge':<8}")
    print("  " + "-" * 65)
    
    for i, row in enumerate(value_picks.itertuples(), 1):
        player = row.player_name if hasattr(row, 'player_name') else "Unknown"
        odds = row.odds_to_win if hasattr(row, 'odds_to_win') else "N/A"
        impl_prob = row.implied_prob if hasattr(row, 'implied_prob') else 0
        fair_prob = row.fair_prob if hasattr(row, 'fair_prob') else 0
        edge = row.edge if hasattr(row, 'edge') else 0
        
        vegas_pct = f"{impl_prob*100:.1f}%"
        model_pct = f"{fair_prob*100:.1f}%"
        edge_pct = f"+{edge*100:.1f}%"
        
        print(f"  {i:<4} {player:<25} {odds:<10} {vegas_pct:<8} {model_pct:<8} {edge_pct:<8}")
    
    print()
    
    # Also show fades (negative edge)
    fades = df[df['edge'] < -0.02].sort_values('edge').head(10)
    
    if not fades.empty:
        print()
        print("  ⚠️  FADES (Overvalued by Vegas)")
        print("  " + "-" * 65)
        
        for i, row in enumerate(fades.itertuples(), 1):
            player = row.player_name if hasattr(row, 'player_name') else "Unknown"
            odds = row.odds_to_win if hasattr(row, 'odds_to_win') else "N/A"
            edge = row.edge if hasattr(row, 'edge') else 0
            
            edge_pct = f"{edge*100:.1f}%"
            
            print(f"  {i:<4} {player:<25} {odds:<10} Edge: {edge_pct}")
        
        print()


def main():
    parser = argparse.ArgumentParser(description="View betting odds")
    parser.add_argument("--favorites", "-f", type=int, nargs="?", const=30, help="Show top N favorites")
    parser.add_argument("--longshots", "-l", action="store_true", help="Show longshots")
    parser.add_argument("--value", "-v", action="store_true", help="Show value picks (model vs Vegas)")
    
    args = parser.parse_args()
    
    if args.longshots:
        display_longshots()
    elif args.value:
        display_value()
    else:
        n = args.favorites if args.favorites else 30
        display_favorites(n)


if __name__ == "__main__":
    main()
