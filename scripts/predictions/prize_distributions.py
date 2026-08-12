#!/usr/bin/env python3
"""
Prize Distribution Models for PGA Tour Tournaments
==================================================

This module provides realistic prize money distributions for different
tournament types based on historical PGA Tour payouts.

Usage:
    from prize_distributions import calculate_expected_value_detailed

    ev = calculate_expected_value_detailed(
        win_prob=0.05,
        top5_prob=0.20,
        top10_prob=0.35,
        top20_prob=0.50,
        purse=20_000_000,
        tournament_type='Signature'
    )
"""

import numpy as np
import pandas as pd

# ============================================================================
# Prize Distribution Percentages (Based on 2024-2026 PGA Tour Structure)
# ============================================================================

# Standard tournaments (e.g., Phoenix Open, Valspar)
STANDARD_DISTRIBUTION = {
    1: 0.180,   # Winner: 18%
    2: 0.109,   # 2nd: 10.9%
    3: 0.069,   # 3rd: 6.9%
    4: 0.049,   # 4th: 4.9%
    5: 0.041,   # 5th: 4.1%
    6: 0.036,   # 6th-10th decline gradually
    7: 0.034,
    8: 0.031,
    9: 0.029,
    10: 0.027,
    11: 0.025,  # 11th-20th
    12: 0.023,
    13: 0.021,
    14: 0.020,
    15: 0.019,
    16: 0.018,
    17: 0.017,
    18: 0.016,
    19: 0.015,
    20: 0.014,
    # 21-70 get smaller amounts (not modeled here for simplicity)
}

# Signature events (e.g., Genesis Invitational, Arnold Palmer)
SIGNATURE_DISTRIBUTION = {
    1: 0.200,   # Winner: 20% (bigger winner's share)
    2: 0.120,
    3: 0.076,
    4: 0.054,
    5: 0.045,
    6: 0.040,
    7: 0.037,
    8: 0.034,
    9: 0.032,
    10: 0.030,
    11: 0.028,
    12: 0.026,
    13: 0.024,
    14: 0.022,
    15: 0.021,
    16: 0.020,
    17: 0.019,
    18: 0.018,
    19: 0.017,
    20: 0.016,
}

# Majors (Masters, PGA, US Open, Open Championship)
MAJOR_DISTRIBUTION = {
    1: 0.200,   # Winner: 20%
    2: 0.120,
    3: 0.076,
    4: 0.054,
    5: 0.045,
    6: 0.040,
    7: 0.037,
    8: 0.034,
    9: 0.032,
    10: 0.030,
    11: 0.028,
    12: 0.026,
    13: 0.024,
    14: 0.022,
    15: 0.021,
    16: 0.020,
    17: 0.019,
    18: 0.018,
    19: 0.017,
    20: 0.016,
}

# Map tournament types to distributions
DISTRIBUTIONS = {
    'Standard': STANDARD_DISTRIBUTION,
    'Signature': SIGNATURE_DISTRIBUTION,
    'Major': MAJOR_DISTRIBUTION,
    # FedEx Cup playoff events: small no-cut elite fields with Signature-scale
    # purses, so the Signature payout curve is the closest fit.
    'Playoff': SIGNATURE_DISTRIBUTION,
}

# ============================================================================
# Expected Value Calculations
# ============================================================================

def get_prize_for_position(position, purse, tournament_type='Standard'):
    """
    Get prize money for a specific finishing position

    Args:
        position: Finishing position (1 = win, 2 = 2nd, etc.)
        purse: Tournament purse
        tournament_type: 'Standard', 'Signature', or 'Major'

    Returns:
        Prize money for that position
    """
    distribution = DISTRIBUTIONS.get(tournament_type, STANDARD_DISTRIBUTION)

    if position in distribution:
        return purse * distribution[position]
    else:
        # For positions beyond 20, use declining percentage
        # Approximate as exponential decay
        return purse * 0.005  # Rough estimate for 21-70th

def calculate_expected_value_simple(win_prob, top5_prob, top10_prob, purse):
    """
    Simple EV calculation (current method in your script)

    This is what you're currently using - fast but less accurate
    """
    ev = (
        win_prob * (purse * 0.18) +
        (top5_prob - win_prob) * (purse * 0.08) +
        (top10_prob - top5_prob) * (purse * 0.04)
    )
    return ev

def calculate_expected_value_detailed(win_prob, top5_prob, top10_prob, top20_prob,
                                     purse, tournament_type='Standard'):
    """
    Detailed EV calculation using actual prize distributions

    This is the IMPROVED version for Challenge 4!

    Args:
        win_prob: P(1st place)
        top5_prob: P(1st-5th)
        top10_prob: P(1st-10th)
        top20_prob: P(1st-20th)
        purse: Tournament purse
        tournament_type: 'Standard', 'Signature', or 'Major'

    Returns:
        Expected value in dollars

    Method:
        Instead of using average percentages for top-5, top-10, etc.,
        we break down the probabilities for each individual position
        and use actual prize percentages.
    """
    distribution = DISTRIBUTIONS.get(tournament_type, STANDARD_DISTRIBUTION)

    # Calculate implied probabilities for each position
    # Assume uniform distribution within each band

    # Position 1 (win)
    p1 = win_prob

    # Positions 2-5 (top5 but not win)
    p_2to5_total = top5_prob - win_prob
    p_2to5_each = p_2to5_total / 4  # Divide equally among 2nd, 3rd, 4th, 5th

    # Positions 6-10 (top10 but not top5)
    p_6to10_total = top10_prob - top5_prob
    p_6to10_each = p_6to10_total / 5

    # Positions 11-20 (top20 but not top10)
    p_11to20_total = top20_prob - top10_prob
    p_11to20_each = p_11to20_total / 10

    # Calculate EV by summing: P(position) × Prize(position)
    ev = 0

    # 1st place
    ev += p1 * (purse * distribution[1])

    # 2nd-5th
    for pos in [2, 3, 4, 5]:
        ev += p_2to5_each * (purse * distribution[pos])

    # 6th-10th
    for pos in [6, 7, 8, 9, 10]:
        ev += p_6to10_each * (purse * distribution[pos])

    # 11th-20th
    for pos in range(11, 21):
        ev += p_11to20_each * (purse * distribution[pos])

    # 21st+ (remaining probability)
    p_21plus = 1.0 - top20_prob
    ev += p_21plus * (purse * 0.005)  # Small prize for making the cut

    return ev

def calculate_expected_value_distribution(position_probs, purse, tournament_type='Standard'):
    """
    Most detailed EV calculation - provide probability for each position

    Args:
        position_probs: Dict mapping position to probability
                       e.g., {1: 0.05, 2: 0.08, 3: 0.10, ...}
        purse: Tournament purse
        tournament_type: 'Standard', 'Signature', or 'Major'

    Returns:
        Expected value in dollars
    """
    distribution = DISTRIBUTIONS.get(tournament_type, STANDARD_DISTRIBUTION)

    ev = 0
    for position, prob in position_probs.items():
        prize = get_prize_for_position(position, purse, tournament_type)
        ev += prob * prize

    return ev

# ============================================================================
# Utility Functions
# ============================================================================

def compare_ev_methods(win_prob, top5_prob, top10_prob, top20_prob, purse):
    """
    Compare simple vs detailed EV calculations

    Useful for seeing how much the improvement matters
    """
    simple_ev = calculate_expected_value_simple(win_prob, top5_prob, top10_prob, purse)

    results = {}
    for t_type in ['Standard', 'Signature', 'Major']:
        detailed_ev = calculate_expected_value_detailed(
            win_prob, top5_prob, top10_prob, top20_prob, purse, t_type
        )
        results[t_type] = {
            'simple': simple_ev,
            'detailed': detailed_ev,
            'difference': detailed_ev - simple_ev,
            'pct_difference': (detailed_ev - simple_ev) / simple_ev * 100 if simple_ev > 0 else 0
        }

    return results

def get_prize_table(purse, tournament_type='Standard'):
    """
    Generate a table showing prize money for each position

    Useful for understanding the payout structure
    """
    distribution = DISTRIBUTIONS.get(tournament_type, STANDARD_DISTRIBUTION)

    prizes = []
    for position in range(1, 21):
        if position in distribution:
            prize = purse * distribution[position]
            pct = distribution[position] * 100
            prizes.append({
                'Position': position,
                'Prize': f'${prize:,.0f}',
                'Percentage': f'{pct:.1f}%'
            })

    return pd.DataFrame(prizes)

# ============================================================================
# Example Usage
# ============================================================================

if __name__ == '__main__':
    # Example: Compare methods for a strong player
    print("=" * 70)
    print("  EV CALCULATION COMPARISON")
    print("=" * 70)
    print()

    # Example player: Scottie Scheffler at a Signature event
    win_prob = 0.08      # 8% chance to win
    top5_prob = 0.25     # 25% chance of top-5
    top10_prob = 0.40    # 40% chance of top-10
    top20_prob = 0.60    # 60% chance of top-20
    purse = 20_000_000   # $20M purse

    print("Player probabilities:")
    print(f"  Win: {win_prob*100:.1f}%")
    print(f"  Top-5: {top5_prob*100:.1f}%")
    print(f"  Top-10: {top10_prob*100:.1f}%")
    print(f"  Top-20: {top20_prob*100:.1f}%")
    print(f"\nPurse: ${purse:,}")
    print()

    results = compare_ev_methods(win_prob, top5_prob, top10_prob, top20_prob, purse)

    print("Expected Values:")
    print("-" * 70)
    print(f"{'Method':<20} {'EV':<15} {'Difference':<15}")
    print("-" * 70)

    simple = results['Standard']['simple']
    print(f"{'Simple (current)':<20} ${simple:>12,.0f}")

    for t_type in ['Standard', 'Signature', 'Major']:
        detailed = results[t_type]['detailed']
        diff = results[t_type]['difference']
        diff_pct = results[t_type]['pct_difference']
        print(f"{'Detailed (' + t_type + ')':<20} ${detailed:>12,.0f}  (+${diff:>8,.0f}, +{diff_pct:>4.1f}%)")

    print()
    print("=" * 70)
    print("  PRIZE DISTRIBUTION TABLE (Signature Event)")
    print("=" * 70)
    print()
    print(get_prize_table(purse, 'Signature').to_string(index=False))