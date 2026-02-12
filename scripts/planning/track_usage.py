#!/usr/bin/env python3
"""
Player Usage Tracker - Manage 3 uses per player rule

Usage:
    # Initialize tracker with elite players
    python track_usage.py --init
    
    # Record picks for a week
    python track_usage.py --week 2 --tournament "American Express" \
        --players "Scottie Scheffler,Michael Brennan,Ben Griffin"
    
    # Check remaining uses
    python track_usage.py --check "Scottie Scheffler"
    
    # View full status
    python track_usage.py --status
"""

import pandas as pd
import argparse
import os
from datetime import datetime
from player_tiers import get_player_tier, get_all_tracked_players

# Elite players to track by default
# Import from player_tiers module instead of hardcoding
from player_tiers import get_all_tracked_players

def get_elite_players():
    """Get all tracked players from tier system"""
    return get_all_tracked_players()


TRACKER_FILE = 'outputs/player_usage_tracker.csv'

def init_tracker():
    """Initialize usage tracker with tiered players"""
    players_list = get_elite_players()
    
    df = pd.DataFrame(players_list)
    df['tier'] = df['player_name'].apply(lambda x: get_player_tier(x)['tier'])
    df['priority'] = df['player_name'].apply(lambda x: get_player_tier(x)['priority'])
    df['strategy'] = df['player_name'].apply(lambda x: get_player_tier(x)['strategy'])
    df['uses_remaining'] = 3
    df['weeks_used'] = ''
    df['tournaments_used'] = ''
    df['optimal_weeks_remaining'] = ''
    df['last_updated'] = datetime.now().strftime('%Y-%m-%d')
    
    # Sort by priority
    df = df.sort_values('priority')
    
    os.makedirs('outputs', exist_ok=True)
    df.to_csv(TRACKER_FILE, index=False)
    print(f"✅ Initialized tracker with {len(df)} players across tiers")
    print(f"📁 File: {TRACKER_FILE}")
    
    # Show tier breakdown
    tier_counts = df['tier'].value_counts()
    for tier, count in tier_counts.items():
        print(f"   {tier}: {count} players")
    
    return df


def load_tracker():
    """Load usage tracker, create if doesn't exist"""
    if not os.path.exists(TRACKER_FILE):
        print("⚠️  Tracker not found, initializing...")
        return init_tracker()
    
    df = pd.read_csv(TRACKER_FILE)
    return df

def add_player(player_name, player_id=None):
    """Add a new player to tracker"""
    df = load_tracker()
    
    # Check if already exists
    if player_name in df['player_name'].values:
        print(f"ℹ️  {player_name} already in tracker")
        return df
    
    # Add new row
    new_row = {
        'player_name': player_name,
        'player_id': player_id if player_id else '',
        'uses_remaining': 3,
        'weeks_used': '',
        'tournaments_used': '',
        'optimal_weeks_remaining': '',
        'last_updated': datetime.now().strftime('%Y-%m-%d')
    }
    
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(TRACKER_FILE, index=False)
    print(f"✅ Added {player_name} to tracker")
    return df

def record_usage(week_number, tournament_name, player_names):
    """Record that players were used this week"""
    df = load_tracker()
    
    for player_name in player_names:
        # Find player in tracker
        mask = df['player_name'] == player_name
        
        if not mask.any():
            # Player not tracked yet, add them
            print(f"ℹ️  {player_name} not in tracker, adding...")
            df = add_player(player_name)
            mask = df['player_name'] == player_name
        
        # Get current data
        idx = df[mask].index[0]
        current_weeks = df.loc[idx, 'weeks_used']
        current_tournaments = df.loc[idx, 'tournaments_used']
        uses_remaining = df.loc[idx, 'uses_remaining']
        
        # Check if already used this week
        weeks_list = [w for w in str(current_weeks).split(',') if w]
        if str(week_number) in weeks_list:
            print(f"⚠️  {player_name} already marked as used in week {week_number}")
            continue
        
        # Check if out of uses
        if uses_remaining <= 0:
            print(f"❌ WARNING: {player_name} has 0 uses remaining!")
            continue
        
        # Update weeks used
        if pd.isna(current_weeks) or current_weeks == '':
            new_weeks = str(week_number)
        else:
            new_weeks = f"{current_weeks},{week_number}"
        
        # Update tournaments used
        if pd.isna(current_tournaments) or current_tournaments == '':
            new_tournaments = tournament_name
        else:
            new_tournaments = f"{current_tournaments},{tournament_name}"
        
        # Update dataframe
        df.loc[idx, 'weeks_used'] = new_weeks
        df.loc[idx, 'tournaments_used'] = new_tournaments
        df.loc[idx, 'uses_remaining'] = uses_remaining - 1
        df.loc[idx, 'last_updated'] = datetime.now().strftime('%Y-%m-%d')
        
        print(f"✅ {player_name}: {uses_remaining} → {uses_remaining - 1} uses remaining")
    
    # Save
    df.to_csv(TRACKER_FILE, index=False)
    print(f"\n📁 Saved to {TRACKER_FILE}")
    return df

def check_player(player_name):
    """Check usage status for a specific player"""
    df = load_tracker()
    
    mask = df['player_name'].str.contains(player_name, case=False, na=False)
    
    if not mask.any():
        print(f"❌ Player '{player_name}' not found in tracker")
        return None
    
    player_data = df[mask].iloc[0]
    
    print(f"\n📊 {player_data['player_name']}")
    print(f"   Uses remaining: {player_data['uses_remaining']}/3")
    
    weeks = player_data['weeks_used']
    if pd.notna(weeks) and weeks != '':
        print(f"   Weeks used: {weeks}")
    else:
        print(f"   Weeks used: None")
    
    tournaments = player_data['tournaments_used']
    if pd.notna(tournaments) and tournaments != '':
        print(f"   Tournaments: {tournaments}")
    
    return player_data

def show_status():
    """Show full tracker status grouped by tier"""
    df = load_tracker()
    
    print("\n" + "="*80)
    print("PLAYER USAGE TRACKER - 2026 Season (By Tier)")
    print("="*80)
    
    # Group by tier first
    tiers = ['Tier 1 - Elite', 'Tier 2 - Strong', 'Tier 3 - Solid', 'Tier 4 - Value']
    
    for tier_name in tiers:
        tier_players = df[df['tier'] == tier_name]
        if len(tier_players) == 0:
            continue
        
        print(f"\n{'='*80}")
        print(f"{tier_name} ({len(tier_players)} players)")
        print(f"{'='*80}")
        
        # Within each tier, group by uses remaining
        for uses in [0, 1, 2, 3]:
            subset = tier_players[tier_players['uses_remaining'] == uses]
            if len(subset) == 0:
                continue
            
            if uses == 0:
                print(f"\n  ❌ NO USES REMAINING ({len(subset)} players):")
            elif uses == 1:
                print(f"\n  ⚠️  1 USE REMAINING ({len(subset)} players):")
            elif uses == 2:
                print(f"\n  🟡 2 USES REMAINING ({len(subset)} players):")
            else:
                print(f"\n  ✅ 3 USES REMAINING ({len(subset)} players):")
            
            for _, row in subset.iterrows():
                tournaments = row['tournaments_used']
                if pd.notna(tournaments) and tournaments != '':
                    print(f"     {row['priority']:2d}. {row['player_name']:<25} Used: {tournaments}")
                else:
                    print(f"     {row['priority']:2d}. {row['player_name']:<25} Not used yet")
    
    print("\n" + "="*80)
    print(f"Last updated: {df['last_updated'].iloc[0]}")
    print("="*80 + "\n")

def calculate_opportunity_cost(player_name, current_ev, upcoming_tournaments_df):
    """
    Calculate opportunity cost of using player now vs later
    
    Args:
        player_name: Name of player
        current_ev: EV for using player this week
        upcoming_tournaments_df: DataFrame with columns [week, tournament, purse, field_strength]
    
    Returns:
        Dictionary with opportunity cost analysis
    """
    df = load_tracker()
    
    mask = df['player_name'] == player_name
    if not mask.any():
        return None
    
    uses_remaining = df.loc[mask, 'uses_remaining'].iloc[0]
    
    if uses_remaining == 0:
        return {
            'decision': 'CANNOT USE',
            'reason': 'No uses remaining',
            'opportunity_cost': float('inf')
        }
    
    if uses_remaining == 3:
        return {
            'decision': 'CAN USE',
            'reason': 'Plenty of uses remaining',
            'opportunity_cost': 0
        }
    
    # Calculate best remaining EV (simplified - you can enhance this)
    # This would need predictions for future tournaments
    # For now, use a heuristic based on tournament purse
    
    if len(upcoming_tournaments_df) == 0:
        return {
            'decision': 'USE NOW',
            'reason': 'No future tournaments to compare',
            'opportunity_cost': 0
        }
    
    # Find highest purse tournaments
    top_tournaments = upcoming_tournaments_df.nlargest(uses_remaining, 'purse')
    avg_top_purse = top_tournaments['purse'].mean()
    
    # Simple heuristic: If current EV is high relative to average top purse
    relative_value = current_ev / (avg_top_purse * 0.15)  # Assume ~15% top finish rate
    
    if relative_value > 1.2:
        decision = 'USE NOW'
        reason = f'High EV relative to upcoming tournaments ({relative_value:.1f}x)'
    elif relative_value < 0.8:
        decision = 'SAVE'
        reason = f'Better opportunities likely ahead ({relative_value:.1f}x current value)'
    else:
        decision = 'NEUTRAL'
        reason = f'Similar value to upcoming tournaments ({relative_value:.1f}x)'
    
    return {
        'decision': decision,
        'reason': reason,
        'opportunity_cost': avg_top_purse * 0.15 - current_ev,
        'relative_value': relative_value
    }

def main():
    parser = argparse.ArgumentParser(description='Track player usage (3 uses per season)')
    
    parser.add_argument('--init', action='store_true',
                       help='Initialize tracker with elite players')
    parser.add_argument('--week', type=int,
                       help='Week number for recording usage')
    parser.add_argument('--tournament', type=str,
                       help='Tournament name for recording usage')
    parser.add_argument('--players', type=str,
                       help='Comma-separated list of player names')
    parser.add_argument('--add', type=str,
                       help='Add a new player to tracker')
    parser.add_argument('--check', type=str,
                       help='Check usage for specific player')
    parser.add_argument('--status', action='store_true',
                       help='Show full tracker status')
    
    args = parser.parse_args()
    
    if args.init:
        init_tracker()
    
    elif args.week and args.tournament and args.players:
        player_list = [p.strip() for p in args.players.split(',')]
        record_usage(args.week, args.tournament, player_list)
    
    elif args.add:
        add_player(args.add)
    
    elif args.check:
        check_player(args.check)
    
    elif args.status:
        show_status()
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
