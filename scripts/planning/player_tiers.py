#!/usr/bin/env python3
"""
Player Tier Classification System

Organizes players into tiers for strategic allocation
"""

import pandas as pd

# Updated tier system with more players
PLAYER_TIERS = {
    # Tier 1: Elite - Save for premium events (Signatures/Majors/Playoffs)
    'Tier 1 - Elite': [
        {'player_name': 'Scottie Scheffler', 'player_id': 46046, 'priority': 1},
        {'player_name': 'Xander Schauffele', 'player_id': 48081, 'priority': 2},
        {'player_name': 'Rory McIlroy', 'player_id': 28237, 'priority': 3},
        {'player_name': 'Ludvig Aberg', 'player_id': 58610, 'priority': 4},
        {'player_name': 'Jon Rahm', 'player_id': 46970, 'priority': 5},
    ],
    
    # Tier 2: Strong - Mix of premium and course fit events
    'Tier 2 - Strong': [
        {'player_name': 'Viktor Hovland', 'player_id': 51466, 'priority': 6},
        {'player_name': 'Collin Morikawa', 'player_id': 50525, 'priority': 7},
        {'player_name': 'Patrick Cantlay', 'player_id': 35450, 'priority': 8},
        {'player_name': 'Hideki Matsuyama', 'player_id': 33399, 'priority': 9},
        {'player_name': 'Sahith Theegala', 'player_id': 51634, 'priority': 10},
        {'player_name': 'Wyndham Clark', 'player_id': 48081, 'priority': 11},
        {'player_name': 'Max Homa', 'player_id': 47959, 'priority': 12},
    ],
    
    # Tier 3: Solid - Course fit and field strength dependent
    'Tier 3 - Solid': [
        {'player_name': 'Justin Thomas', 'player_id': 33448, 'priority': 13},
        {'player_name': 'Jordan Spieth', 'player_id': 29478, 'priority': 14},
        {'player_name': 'Tony Finau', 'player_id': 32102, 'priority': 15},
        {'player_name': 'Sam Burns', 'player_id': 51766, 'priority': 16},
        {'player_name': 'Tom Kim', 'player_id': 57879, 'priority': 17},
        {'player_name': 'Sungjae Im', 'player_id': 47025, 'priority': 18},
        {'player_name': 'Russell Henley', 'player_id': 28093, 'priority': 19},
        {'player_name': 'Keegan Bradley', 'player_id': 26329, 'priority': 20},
    ],
    
    # Tier 4: Value - Use freely based on EV
    'Tier 4 - Value': [
        {'player_name': 'Jason Day', 'player_id': 24502, 'priority': 21},
        {'player_name': 'Brian Harman', 'player_id': 27644, 'priority': 22},
        {'player_name': 'Corey Conners', 'player_id': 35532, 'priority': 23},
        {'player_name': 'Akshay Bhatia', 'player_id': 54470, 'priority': 24},
        {'player_name': 'Taylor Pendrith', 'player_id': 49963, 'priority': 25},
        # Add more as needed
    ]
}

def get_player_tier(player_name):
    """
    Get tier classification for a player
    
    Args:
        player_name: Player name (partial match supported)
    
    Returns:
        Dict with tier, priority, and strategy recommendation
    """
    player_name_lower = player_name.lower()
    
    for tier_name, players in PLAYER_TIERS.items():
        for player in players:
            if player_name_lower in player['player_name'].lower():
                return {
                    'tier': tier_name,
                    'priority': player['priority'],
                    'player_id': player['player_id'],
                    'strategy': get_tier_strategy(tier_name)
                }
    
    # Not in any tier - treat as flexible
    return {
        'tier': 'Unranked',
        'priority': 999,
        'player_id': None,
        'strategy': 'Use freely based on EV - not tracked for 3-use optimization'
    }

def get_tier_strategy(tier_name):
    """Get recommended strategy for each tier"""
    strategies = {
        'Tier 1 - Elite': 'Save for Signatures/Majors/Playoffs only (unless dominant course fit)',
        'Tier 2 - Strong': 'Use at Signatures, Majors, or strong course fits',
        'Tier 3 - Solid': 'Use at course fits or weaker field events',
        'Tier 4 - Value': 'Use anytime EV is high - less scarce'
    }
    return strategies.get(tier_name, 'Use based on weekly EV')

def get_all_tracked_players():
    """Get all players that should be tracked (Tiers 1-3)"""
    tracked = []
    for tier_name in ['Tier 1 - Elite', 'Tier 2 - Strong', 'Tier 3 - Solid']:
        tracked.extend(PLAYER_TIERS[tier_name])
    return tracked

def export_tiers_to_csv(output_path='outputs/player_tiers.csv'):
    """Export tier system to CSV"""
    rows = []
    for tier_name, players in PLAYER_TIERS.items():
        for player in players:
            rows.append({
                'tier': tier_name,
                'player_name': player['player_name'],
                'player_id': player['player_id'],
                'priority': player['priority'],
                'strategy': get_tier_strategy(tier_name)
            })
    
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"✅ Exported {len(df)} players to {output_path}")
    return df

if __name__ == '__main__':
    # Test the system
    print("\n" + "="*80)
    print("PLAYER TIER SYSTEM")
    print("="*80 + "\n")
    
    for tier_name, players in PLAYER_TIERS.items():
        print(f"\n{tier_name} ({len(players)} players):")
        print(f"Strategy: {get_tier_strategy(tier_name)}\n")
        for player in players[:3]:  # Show first 3
            print(f"  {player['priority']:2d}. {player['player_name']}")
        if len(players) > 3:
            print(f"  ... and {len(players)-3} more")
    
    # Export
    export_tiers_to_csv()
