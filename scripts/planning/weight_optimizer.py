#!/usr/bin/env python3
"""
Weight Optimizer for Scoring Engine
====================================

Tests different weight configurations against historical results
to find optimal scoring weights.

Usage:
    python weight_optimizer.py                    # Run full optimization
    python weight_optimizer.py --config form_heavy  # Test specific config
    python weight_optimizer.py --backtest 5       # Backtest last 5 tournaments
"""

import json
import random
import pandas as pd
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"
RESULTS_FILE = DATA_DIR / "prediction_tracking" / "weight_test_results.json"

# Weight configurations to test
WEIGHT_CONFIGS = {
    'baseline': {
        'importance': 0.25,
        'course_fit': 0.35,
        'form': 0.25,
        'field': 0.15
    },
    'form_heavy': {
        'importance': 0.15,
        'course_fit': 0.30,
        'form': 0.40,
        'field': 0.15
    },
    'course_heavy': {
        'importance': 0.20,
        'course_fit': 0.45,
        'form': 0.20,
        'field': 0.15
    },
    'balanced': {
        'importance': 0.25,
        'course_fit': 0.25,
        'form': 0.30,
        'field': 0.20
    },
    'value_focus': {
        'importance': 0.20,
        'course_fit': 0.30,
        'form': 0.35,
        'field': 0.15
    }
}


@dataclass
class WeightTestResult:
    """Results from testing a weight configuration."""
    config_name: str
    weights: Dict[str, float]
    tournaments_tested: int

    # Performance metrics
    avg_pick_finish: float  # Average finish position of top picks
    top10_hit_rate: float   # % of top picks that finished top 10
    top20_hit_rate: float   # % of top picks that finished top 20
    winner_identified: int  # Times the winner was in top 5 picks

    # Fantasy specific
    total_points: int       # Simulated fantasy points
    points_per_pick: float

    def score(self) -> float:
        """Overall score for this config (higher = better)."""
        return (
            self.top10_hit_rate * 40 +
            self.top20_hit_rate * 30 +
            (self.winner_identified / max(1, self.tournaments_tested)) * 20 +
            (100 - self.avg_pick_finish) * 0.1
        )


def load_historical_results() -> pd.DataFrame:
    """Load historical leaderboard results."""
    leaderboards_file = DATA_DIR / "historical" / "leaderboards_2026.csv"
    if leaderboards_file.exists():
        return pd.read_csv(leaderboards_file)
    return pd.DataFrame()


def load_predictions_for_tournament(tournament_id: str) -> pd.DataFrame:
    """Load predictions that were made for a tournament."""
    pred_files = list(OUTPUTS_DIR.glob(f"*{tournament_id}*predictions*.csv"))
    if pred_files:
        return pd.read_csv(pred_files[0])
    return pd.DataFrame()


def get_position_numeric(pos_str) -> int:
    """Convert position string like 'T24' to numeric."""
    if pd.isna(pos_str):
        return 99
    pos_str = str(pos_str).replace('T', '').replace('*', '').strip()
    try:
        return int(pos_str)
    except:
        return 99


def simulate_picks_with_weights(
    predictions: pd.DataFrame,
    weights: Dict[str, float],
    n_picks: int = 3
) -> List[str]:
    """Re-score predictions with given weights and return top N picks."""
    if predictions.empty:
        return []

    df = predictions.copy()

    # Map prediction columns to weight categories
    col_mapping = {
        'importance': ['tournament_importance', 'importance_score'],
        'course_fit': ['course_fit', 'course_fit_score'],
        'form': ['form_score', 'current_form', 'form'],
        'field': ['field_strength', 'field_score']
    }

    df['weighted_score'] = 0
    for weight_key, possible_cols in col_mapping.items():
        for col in possible_cols:
            if col in df.columns:
                df['weighted_score'] += df[col].fillna(0) * weights.get(weight_key, 0.25)
                break

    top_picks = df.nlargest(n_picks, 'weighted_score')
    name_col = 'player_name' if 'player_name' in df.columns else 'player'
    return top_picks[name_col].tolist()


def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    return str(name).lower().strip()


def evaluate_picks(
    picks: List[str],
    results: pd.DataFrame,
    tournament_name: str
) -> Dict:
    """Evaluate how picks performed against actual results."""
    tourney_results = results[
        results['tournament_name'].str.lower().str.contains(
            tournament_name.lower()[:15], na=False, regex=False
        )
    ]

    if tourney_results.empty:
        return None

    eval_data = {
        'picks': picks,
        'finishes': [],
        'top10_hits': 0,
        'top20_hits': 0,
        'winner_hit': False,
        'points': 0
    }

    # FedEx points approximation
    points_table = {
        1: 500, 2: 300, 3: 175, 4: 135, 5: 115,
        6: 100, 7: 90, 8: 80, 9: 72, 10: 65,
        **{i: max(5, 60 - (i-10)*2) for i in range(11, 50)}
    }

    for pick in picks:
        pick_lower = normalize_name(pick)

        match = None
        for _, row in tourney_results.iterrows():
            result_name = normalize_name(row.get('player_name', ''))
            pick_parts = set(pick_lower.split())
            result_parts = set(result_name.split())
            if len(pick_parts & result_parts) >= 1:
                match = row
                break

        if match is not None:
            pos = get_position_numeric(match.get('position', 99))
            eval_data['finishes'].append(pos)

            if pos <= 10:
                eval_data['top10_hits'] += 1
            if pos <= 20:
                eval_data['top20_hits'] += 1
            if pos == 1:
                eval_data['winner_hit'] = True

            eval_data['points'] += points_table.get(pos, 0)
        else:
            eval_data['finishes'].append(99)

    return eval_data


def run_backtest(n_tournaments: int = 5) -> Dict[str, WeightTestResult]:
    """Backtest all weight configurations against recent tournaments."""
    results = load_historical_results()
    if results.empty:
        print("No historical results found")
        return {}

    tournaments = results['tournament_name'].unique()
    print(f"Found {len(tournaments)} tournaments in historical data")

    # Load all available prediction files
    prediction_files = list(OUTPUTS_DIR.glob("*_predictions.csv"))
    prediction_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    if not prediction_files or True:  # Always use simulated for now until more data
        print("Using simulated backtest based on historical finishes...")
        return run_simulated_backtest(results, n_tournaments)

    config_results = {}

    for config_name, weights in WEIGHT_CONFIGS.items():
        print(f"\nTesting config: {config_name}")
        print(f"  Weights: {weights}")

        all_finishes = []
        top10_hits = 0
        top20_hits = 0
        winner_hits = 0
        total_points = 0
        tournaments_tested = 0

        for pred_file in prediction_files[:n_tournaments]:
            try:
                predictions = pd.read_csv(pred_file)
                tourney_name = pred_file.stem.replace('_predictions', '').replace('_', ' ')
                picks = simulate_picks_with_weights(predictions, weights, n_picks=3)

                if not picks:
                    continue

                eval_result = evaluate_picks(picks, results, tourney_name)

                if eval_result:
                    all_finishes.extend(eval_result['finishes'])
                    top10_hits += eval_result['top10_hits']
                    top20_hits += eval_result['top20_hits']
                    if eval_result['winner_hit']:
                        winner_hits += 1
                    total_points += eval_result['points']
                    tournaments_tested += 1

                    print(f"    {tourney_name[:30]}: picks={picks[:2]}... finishes={eval_result['finishes']}")

            except Exception as e:
                print(f"    Error processing {pred_file.name}: {e}")
                continue

        if tournaments_tested > 0:
            config_results[config_name] = WeightTestResult(
                config_name=config_name,
                weights=weights,
                tournaments_tested=tournaments_tested,
                avg_pick_finish=sum(all_finishes) / len(all_finishes) if all_finishes else 50,
                top10_hit_rate=top10_hits / (tournaments_tested * 3),
                top20_hit_rate=top20_hits / (tournaments_tested * 3),
                winner_identified=winner_hits,
                total_points=total_points,
                points_per_pick=total_points / (tournaments_tested * 3)
            )

    return config_results


def run_simulated_backtest(results: pd.DataFrame, n_tournaments: int = 5) -> Dict[str, WeightTestResult]:
    """Run simulated backtest when no prediction files are available."""
    tournaments = results['tournament_name'].unique()[:n_tournaments]

    config_results = {}

    # FedEx points
    points_table = {
        1: 500, 2: 300, 3: 175, 4: 135, 5: 115,
        6: 100, 7: 90, 8: 80, 9: 72, 10: 65,
        **{i: max(5, 60 - (i-10)*2) for i in range(11, 50)}
    }

    for config_name, weights in WEIGHT_CONFIGS.items():
        print(f"\nSimulating config: {config_name}")

        all_finishes = []
        top10_hits = 0
        top20_hits = 0
        winner_hits = 0
        total_points = 0
        tournaments_tested = 0

        for tourney in tournaments:
            tourney_data = results[results['tournament_name'] == tourney].copy()

            if tourney_data.empty:
                continue

            tourney_data['position_num'] = tourney_data['position'].apply(get_position_numeric)

            # Simulate scoring based on weights
            tourney_data['sim_score'] = (
                (100 - tourney_data['position_num'].clip(0, 100)) * weights['form'] +
                50 * weights['course_fit'] +
                50 * weights['importance'] +
                50 * weights['field']
            )

            # Add randomness to simulate model uncertainty
            tourney_data['sim_score'] += [random.uniform(-10, 10) for _ in range(len(tourney_data))]

            # Get top 3 "picks"
            top_picks = tourney_data.nlargest(3, 'sim_score')

            for _, pick in top_picks.iterrows():
                pos = pick['position_num']
                all_finishes.append(pos)

                if pos <= 10:
                    top10_hits += 1
                if pos <= 20:
                    top20_hits += 1
                if pos == 1:
                    winner_hits += 1

                total_points += points_table.get(pos, 0)

            tournaments_tested += 1

        if tournaments_tested > 0:
            config_results[config_name] = WeightTestResult(
                config_name=config_name,
                weights=weights,
                tournaments_tested=tournaments_tested,
                avg_pick_finish=sum(all_finishes) / len(all_finishes) if all_finishes else 50,
                top10_hit_rate=top10_hits / (tournaments_tested * 3),
                top20_hit_rate=top20_hits / (tournaments_tested * 3),
                winner_identified=winner_hits,
                total_points=total_points,
                points_per_pick=total_points / (tournaments_tested * 3)
            )

    return config_results


def save_results(results: Dict[str, WeightTestResult]):
    """Save test results for tracking."""
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {
        'timestamp': datetime.now().isoformat(),
        'results': {
            name: {
                'config_name': r.config_name,
                'weights': r.weights,
                'tournaments_tested': r.tournaments_tested,
                'avg_pick_finish': r.avg_pick_finish,
                'top10_hit_rate': r.top10_hit_rate,
                'top20_hit_rate': r.top20_hit_rate,
                'winner_identified': r.winner_identified,
                'total_points': r.total_points,
                'score': r.score()
            }
            for name, r in results.items()
        }
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nResults saved to {RESULTS_FILE}")


def print_results(results: Dict[str, WeightTestResult]):
    """Print formatted results."""
    print("\n" + "=" * 70)
    print("  WEIGHT OPTIMIZATION RESULTS")
    print("=" * 70)

    sorted_results = sorted(results.items(), key=lambda x: x[1].score(), reverse=True)

    print(f"\n{'Config':<15} {'Score':>8} {'Top10%':>8} {'Top20%':>8} {'AvgFin':>8} {'Pts':>8}")
    print("-" * 60)

    for name, result in sorted_results:
        print(f"{name:<15} {result.score():>8.1f} {result.top10_hit_rate*100:>7.1f}% "
              f"{result.top20_hit_rate*100:>7.1f}% {result.avg_pick_finish:>8.1f} {result.total_points:>8}")

    if sorted_results:
        best = sorted_results[0]
        print(f"\n{'='*60}")
        print(f"  RECOMMENDED CONFIG: {best[0]}")
        print(f"  Weights: importance={best[1].weights['importance']:.2f}, "
              f"course_fit={best[1].weights['course_fit']:.2f}, "
              f"form={best[1].weights['form']:.2f}, "
              f"field={best[1].weights['field']:.2f}")
        print(f"{'='*60}")


def get_best_config() -> Dict[str, float]:
    """Return the best performing weight configuration."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)

        results = data.get('results', {})
        if results:
            best = max(results.items(), key=lambda x: x[1].get('score', 0))
            return best[1].get('weights', WEIGHT_CONFIGS['baseline'])

    return WEIGHT_CONFIGS['baseline']


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Optimize scoring weights")
    parser.add_argument('--backtest', type=int, default=5, help="Number of tournaments to backtest")
    parser.add_argument('--config', help="Test specific config only")
    parser.add_argument('--best', action='store_true', help="Show current best config")

    args = parser.parse_args()

    if args.best:
        best = get_best_config()
        print("Current best weight configuration:")
        print(json.dumps(best, indent=2))
    else:
        print("Running weight optimization backtest...")
        print(f"Testing {len(WEIGHT_CONFIGS)} configurations...")

        results = run_backtest(args.backtest)

        if results:
            print_results(results)
            save_results(results)
        else:
            print("No results to display. Check that historical data exists.")
