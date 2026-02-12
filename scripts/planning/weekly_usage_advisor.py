#!/usr/bin/env python3
"""
Weekly Usage Advisor - Should you use elite players this week?

Reads predictions and provides usage recommendations
"""

import pandas as pd
import argparse
from track_usage import load_tracker, calculate_opportunity_cost

def get_usage_advice(predictions_file, top_n=10):
    """
    Analyze predictions and provide usage recommendations
    Shows tier info and tournament winner boost
    """
    # Load predictions
    predictions_df = pd.read_csv(predictions_file)
    predictions_df = predictions_df.nlargest(top_n, 'expected_value')
    
    # Load tracker
    tracker_df = load_tracker()
    
    # Add tier info to predictions
    from player_tiers import get_player_tier
    predictions_df['tier_info'] = predictions_df['player_name'].apply(
        lambda x: get_player_tier(x)['tier']
    )
    
    print("\n" + "="*80)
    print("WEEKLY USAGE RECOMMENDATIONS")
    print("="*80 + "\n")
    
    # Analyze each top prediction
    for idx, row in predictions_df.iterrows():
        player_name = row['player_name']
        
        # Check winner boost
        winner_boost = ""
        if 'has_won_here' in row and row['has_won_here'] == 1:
            winner_boost = "🏆 PAST WINNER"
        
        # Check if player is tracked
        mask = tracker_df['player_name'] == player_name
        
        if not mask.any():
            status = "✅ USE"
            uses_info = f"{row['tier_info']} - Use freely"
        else:
            player_data = tracker_df[mask].iloc[0]
            uses_remaining = player_data['uses_remaining']
            tier = player_data['tier']
            
            if uses_remaining == 0:
                status = "❌ CANNOT USE"
                uses_info = f"{tier} - 0/3 uses remaining"
            elif uses_remaining == 1:
                status = "⚠️  LAST USE"
                uses_info = f"{tier} - 1/3 remaining - SAVE?"
            elif uses_remaining == 2:
                status = "🟡 2 USES LEFT"
                uses_info = f"{tier} - 2/3 remaining"
            else:
                status = "✅ CAN USE"
                uses_info = f"{tier} - 3/3 remaining"
        
        print(f"{idx+1}. {player_name:<25} {status} {winner_boost}")
        print(f"   EV: ${row['expected_value']:,.0f}  |  Win: {row['win_prob']:.1%}  |  {uses_info}")
        
        # Show course history if available
        if 'hist_times_played' in row and pd.notna(row['hist_times_played']):
            hist_played = int(row['hist_times_played'])
            if hist_played > 0:
                hist_avg = row.get('hist_avg_finish', 0)
                hist_best = row.get('hist_best_finish', 0)
                print(f"   Course: {hist_played} starts, avg {hist_avg:.1f}, best {int(hist_best)}")
        
        print()
    
    print("="*80 + "\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictions', required=True,
                       help='Path to predictions CSV')
    parser.add_argument('--top-n', type=int, default=10,
                       help='Number of top picks to analyze')
    args = parser.parse_args()
    
    get_usage_advice(args.predictions, args.top_n)
