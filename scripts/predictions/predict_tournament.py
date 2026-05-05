import pandas as pd 
import numpy as np 
import argparse
import json
from collections import Counter
import joblib
from pathlib import Path
import sys 
from datetime import datetime
import re
import subprocess
# Ensure project root is on path so `scripts.*` imports work when running directly
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.scrapers.fetch_world_rankings import fetch_world_rankings
from scripts.predictions.prize_distributions import calculate_expected_value_detailed
from scripts.predictions.odds_ensemble import add_odds_to_predictions
from scripts.features.recent_form import get_form_features_for_field, load_form_stats
from scripts.predictions.generate_insights import InsightsGenerator
from scripts.predictions.prediction_tracker import PredictionTracker
from scripts.predictions.usage_optimizer import UsageTracker, UsageOptimizer
from scripts.predictions.calibration import ProbabilityCalibrator
from scripts.predictions.cut_model import add_cut_probability, get_cut_risk_summary


#Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
MODEL_DIR = DATA_DIR / 'models'
PROCESSED_DIR = DATA_DIR / 'processed'
HISTORICAL_DIR = DATA_DIR / 'historical'  # Fixed: should be 'historical' not 'historical_data'


def _latest_year_for(prefix: str, base_dir: Path = HISTORICAL_DIR):
    """Return latest year found for files like '<prefix><year>.csv'."""
    years = []
    for path in base_dir.glob(f"{prefix}*.csv"):
        match = re.search(rf"{re.escape(prefix)}(\d{{4}})", path.stem)
        if match:
            years.append(int(match.group(1)))
    return max(years) if years else None


def write_data_dictionary(predictions_df: pd.DataFrame, output_path: Path):
    """Write a data dictionary for prediction outputs."""
    descriptions = {
        # IDs / names
        "player_id": "PGA Tour player ID (primary key)",
        "player_name": "Player name",
        # Recent SG
        "sg_total": "Recent SG:Total (form window)",
        "sg_ott": "Recent SG:Off-the-Tee",
        "sg_app": "Recent SG:Approach",
        "sg_arg": "Recent SG:Around-the-Green",
        "sg_putt": "Recent SG:Putting",
        "sg_t2g": "Recent SG:Tee-to-Green",
        # Season SG
        "season_sg_total": "Season-to-date SG:Total average",
        "season_sg_ott": "Season SG:Off-the-Tee average",
        "season_sg_app": "Season SG:Approach average",
        "season_sg_arg": "Season SG:Around-the-Green average",
        "season_sg_putt": "Season SG:Putting average",
        "season_sg_t2g": "Season SG:Tee-to-Green average",
        # Course history
        "hist_times_played": "Number of starts at this course",
        "hist_avg_finish": "Average finish at this course",
        "hist_best_finish": "Best finish at this course",
        "hist_wins": "Wins at this course",
        "hist_top5s": "Top-5s at this course",
        "hist_top10s": "Top-10s at this course",
        "hist_cut_rate": "Cut-made rate at this course (0-1)",
        "hist_missed_cuts": "Missed cuts at this course",
        "has_won_here": "1/0 flag: has won at this course",
        "has_course_history": "1/0 flag: has course history",
        "has_made_cut_here": "1/0 flag: has made a cut here",
        # Venue / field
        "venue_avg_finish": "Venue average finish baseline (field-level)",
        "venue_finish_std": "Venue finish standard deviation (volatility)",
        "world_rank": "Current world rank (lower is better)",
        "field_avg_rank": "Average world rank of the field",
        "field_median_rank": "Median world rank of the field",
        # Form features
        "form_trend": "SG:Total trend over recent events (positive = improving)",
        "finish_consistency": "Normalized finish volatility (lower = steadier)",
        "recent_top10s": "Recency-weighted top-10 count over last N events",
        "recent_top5s": "Top-5s over last N events",
        "recent_wins": "Wins over last N events",
        "recent_cuts_made": "Cuts made over last N events",
        "recent_cuts_pct": "Cut-made % over last N events (0-1)",
        "recent_birdie_avg": "Recency-weighted birdies per round",
        "recent_bogey_avg": "Recency-weighted bogeys per round",
        "recent_scoring_avg": "Recency-weighted scoring average",
        "recent_gir_pct": "Recency-weighted GIR%",
        "recent_scrambling": "Recency-weighted scrambling%",
        "recent_bounce_back": "Recency-weighted bounce-back%",
        "recent_final_round": "Recency-weighted final-round scoring",
        "recent_sand_save": "Recency-weighted sand save%",
        # Course fit
        "dg_fit_ott": "Course-fit component: Off-the-Tee",
        "dg_fit_app": "Course-fit component: Approach",
        "dg_fit_arg": "Course-fit component: Around-the-Green",
        "dg_fit_putt": "Course-fit component: Putting",
        "dg_fit_total": "Total course-fit score (sum of components)",
        # Course SG performance
        "course_sg_total_weighted": "Recency-weighted SG:Total at this specific course",
        "course_sg_total_avg": "Historical average SG:Total at this specific course",
        "course_sg_ott_avg": "Historical average SG:Off-the-Tee at this specific course",
        "course_sg_app_avg": "Historical average SG:Approach at this specific course",
        "course_sg_putt_avg": "Historical average SG:Putting at this specific course",
        "course_sg_starts": "Number of prior starts with usable SG history at this course",
        "course_sg_ott_weighted": "Recency-weighted SG:Off-the-Tee at this course",
        "course_sg_app_weighted": "Recency-weighted SG:Approach at this course",
        "course_sg_putt_weighted": "Recency-weighted SG:Putting at this course",
        "course_sg_t2g_weighted": "Recency-weighted SG:Tee-to-Green at this course",
        "course_sg_total_vs_avg": "Course SG edge: how much better/worse at this course vs overall (positive = course specialist)",
        "course_sg_ott_vs_avg": "OTT edge at this course vs overall average",
        "course_sg_app_vs_avg": "Approach edge at this course vs overall average",
        "course_sg_putt_vs_avg": "Putting edge at this course vs overall average",
        "course_sg_t2g_vs_avg": "Tee-to-Green edge at this course vs overall average",
        "overall_sg_total_avg": "Player's career-average SG:Total across all courses",
        "course_sg_trend": "Trend in SG:Total at this course over time (positive = improving year-over-year)",
        "course_sg_recent_vs_early": "Difference between recent and early SG at this course (positive = recent improvement)",
        "course_history_confidence": "Reliability score for course history signal (0-1; higher = more starts/history)",
        "has_course_sg_history": "Boolean flag: player has SG history at this course",
        "course_adjustment": "Post-model probability adjustment from course history/similar-course signals",
        "course_adjustment_confidence": "Confidence applied to course adjustment (0-1)",
        # Model outputs
        "win_prob": "Predicted win probability (0-1)",
        "top5_prob": "Predicted top-5 probability (0-1)",
        "top10_prob": "Predicted top-10 probability (0-1)",
        "projected_score": "Regression model: predicted 4-round to-par total (e.g. -12.5)",
        "score_rank": "Field rank by projected_score (1 = best/lowest projected score)",
        "expected_value": "Expected earnings value based on purse + probabilities (USD)",
        # Cut probability
        "cut_prob": "Probability of making the cut (0-1, higher = safer)",
        "cut_risk": "Cut risk category: LOW (>85%), MEDIUM (65-85%), ELEVATED (45-65%), HIGH (<45%)",
        "miss_cut_prob": "Probability of missing the cut (1 - cut_prob)",
    }

    lines = [
        "# Predictions Data Dictionary",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Column | Description |",
        "|--------|-------------|",
    ]

    for col in predictions_df.columns:
        desc = descriptions.get(col, "No description available")
        lines.append(f"| {col} | {desc} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


def get_current_world_rankings() -> pd.DataFrame:
    """
    Fetch current world rankings from saved file or API.
    Returns DataFrame with player_id and world_rank.
    """
    from pathlib import Path
    from datetime import datetime
    
    # Try to load most recent rankings file
    rankings_dir = Path("data/rankings")
    current_year = datetime.now().year
    
    rankings_file = rankings_dir / f"owgr_{current_year}.csv"
    
    if rankings_file.exists():
        df = pd.read_csv(rankings_file)
        print(f"  Loaded {len(df)} world rankings from {rankings_file}")
        return df[['player_id', 'world_rank']]
    
    # Fallback: try to fetch fresh rankings
    try:
        import sys
        sys.path.insert(0, 'scripts/scrapers')
        
        df = fetch_world_rankings(current_year)
        if len(df) > 0:
            # Save for future use
            rankings_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(rankings_file, index=False)
            return df[['player_id', 'world_rank']]
    except Exception as e:
        print(f"  Warning: Could not fetch rankings: {e}")
    
    return pd.DataFrame(columns=['player_id', 'world_rank'])
   


SCORE_FEATURES = [
    "season_sg_total", "season_sg_ott", "season_sg_app", "season_sg_arg",
    "season_sg_t2g", "season_sg_putt", "season_sg_arg_vs_field",
    "season_sg_total_vs_field", "season_sg_ott_vs_field",
    "season_sg_app_vs_field", "season_sg_putt_vs_field",
    "season_sg_ott_field_pct", "season_sg_app_field_pct", "season_sg_putt_field_pct",
    "recent_sg_weighted", "recent_sg_trend",
    "recent_sg_ott_weighted", "recent_sg_app_weighted", "recent_sg_putt_weighted",
    "hist_times_played", "hist_avg_finish", "hist_best_finish",
    "hist_wins", "hist_top5s", "hist_top10s", "hist_cut_rate", "hist_missed_cuts",
    "has_won_here", "has_course_history", "has_made_cut_here",
    "venue_avg_finish", "venue_finish_std",
    "form_trend", "finish_consistency", "recent_top10s", "recent_top5s",
    "recent_cuts_pct", "recent_birdie_avg", "recent_scoring_avg",
    "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt",
    "dg_fit_total", "predictive_sg_weighted",
    "world_rank",
    "world_rank_log",
    # DG archive features — activated 2026-04 (have historical data 2020-2025 via dg_archive_all.csv)
    # NaN for pre-2020 or non-covered events; tree models handle this gracefully.
    "dg_win",                # DG pre-tournament win probability
    "dg_top10",              # DG pre-tournament top-10 probability
    "dg_make_cut",           # DG pre-tournament make-cut probability
    # DG inference-only features (no historical equivalents — activate after architecture change)
    # "approach_skill_sg",
    # "final_pred",            # DG's full course-adjusted prediction
    # "course_fit_delta",      # final_pred - baseline_pred (course uplift/drag)
    # "driving_accuracy_adjustment",
    # "driving_distance_adjustment",
    # "dg_skill_total",
    # "dg_top20",
]


def load_models():
    """Load trained win/top5/top10 models (+ optional score regression model)"""
    models = {
        'win': joblib.load(MODEL_DIR / 'win_model_final.pkl'),
        'top5': joblib.load(MODEL_DIR / 'top5_model_final.pkl'),
        'top10': joblib.load(MODEL_DIR / 'top10_model_final.pkl')
    }
    _score_path = MODEL_DIR / 'score_model_final.pkl'
    if _score_path.exists():
        models['score'] = joblib.load(_score_path)
        _feats_path = MODEL_DIR / 'score_model_features.txt'
        if _feats_path.exists():
            models['score_features'] = _feats_path.read_text().splitlines()
        # Quantile models: Q10=ceiling (best 10% of weeks), Q90=floor (worst 10%)
        for _q in ('q10', 'q50', 'q90'):
            _qpath = MODEL_DIR / f'score_model_{_q}.pkl'
            if _qpath.exists():
                models[f'score_{_q}'] = joblib.load(_qpath)
    return models

def _load_tournament_stats_from_db(year: int) -> pd.DataFrame:
    """Try loading tournament stats from DuckDB; return empty DataFrame on failure."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "database"))
        from db import get_conn
        with get_conn(read_only=True) as conn:
            df = conn.execute(
                "SELECT * FROM tournament_stats WHERE year = ?", [year]
            ).df()
            if not df.empty:
                return df
    except Exception:
        pass
    return pd.DataFrame()


def load_reference_data():
    """Load historical data for feature engineering"""
    # Master data (for course history lookup and venue stats)
    master_df = pd.read_csv(PROCESSED_DIR / 'master_training_data_2016_2025.csv')

    def _normalize_stats_df(df):
        """Ensure player_id and stat_id are strings for consistent lookup."""
        if df.empty:
            return df
        df = df.copy()
        df['player_id'] = df['player_id'].astype(str).str.strip()
        df['stat_id']   = df['stat_id'].astype(str).str.strip()
        return df

    # Current year SG stats - try DB first, then CSV
    current_year = datetime.now().year
    stats_current = _load_tournament_stats_from_db(current_year)
    if not stats_current.empty:
        print(f"  Loaded current year stats ({current_year}) from DB: {len(stats_current)} rows")
    else:
        stats_current_file = HISTORICAL_DIR / f'tournament_stats_{current_year}.csv'
        if stats_current_file.exists():
            stats_current = _normalize_stats_df(pd.read_csv(stats_current_file))
            print(f"  Loaded current year stats ({current_year}): {len(stats_current)} rows")
        else:
            latest_year = _latest_year_for("tournament_stats_")
            if latest_year:
                stats_current = _normalize_stats_df(pd.read_csv(HISTORICAL_DIR / f'tournament_stats_{latest_year}.csv'))
                print(f"  Current year not found, using {latest_year} stats: {len(stats_current)} rows")
            else:
                stats_current = pd.DataFrame()
                print(f"  Warning: No tournament stats found!")

    # Prior year SG stats (for early-season blending) - try DB first, then CSV
    prior_year = current_year - 1
    stats_prior = _load_tournament_stats_from_db(prior_year)
    if not stats_prior.empty:
        print(f"  Loaded prior year stats ({prior_year}) from DB for early-season blending")
    else:
        prior_stats_file = HISTORICAL_DIR / f'tournament_stats_{prior_year}.csv'
        if prior_stats_file.exists():
            stats_prior = _normalize_stats_df(pd.read_csv(prior_stats_file))
            print(f"  Loaded prior year stats ({prior_year}) for early-season blending")
        else:
            stats_prior = pd.DataFrame()
            print(f"  Prior year stats not found, skipping blend")

    return master_df, stats_current, stats_prior


def enrich_field_names(field_df: pd.DataFrame, master_df: pd.DataFrame, tournament_id: str = None) -> pd.DataFrame:
    """
    Fill missing/placeholder player names in the field using master data and odds files.
    - If player_name is empty or looks like 'Player <id>', try master_df map.
    - If tournament_id is provided, try odds CSV (data/odds/pga_odds_<id>.csv) for names.
    - Fallback to players DB (data/players/pga_players_*.csv) and OWGR files.
    """
    df = field_df.copy()

    # Build master map
    master_map = dict(zip(master_df['player_id'], master_df['player_name']))

    # Player database map (latest first)
    player_map = {}
    players_dir = DATA_DIR / "players"
    if players_dir.exists():
        player_files = sorted(players_dir.glob("pga_players_*.csv"),
                              key=lambda f: f.stat().st_mtime,
                              reverse=True)
        for pf in player_files:
            try:
                pdf = pd.read_csv(pf, usecols=["player_id", "player_name"])
                pdf = pdf.dropna(subset=["player_id"])
                pdf["player_id"] = pdf["player_id"].astype(int)
                player_map.update(dict(zip(pdf["player_id"], pdf["player_name"])))
            except Exception as e:
                print(f"  Could not load player file {pf.name}: {e}")

    # OWGR ranking map as an additional source
    owgr_map = {}
    rankings_dir = DATA_DIR / "rankings"
    if rankings_dir.exists():
        ranking_files = sorted(rankings_dir.glob("owgr_*.csv"),
                               key=lambda f: f.stat().st_mtime,
                               reverse=True)
        for rf in ranking_files:
            try:
                rdf = pd.read_csv(rf, usecols=["player_id", "player_name"])
                rdf = rdf.dropna(subset=["player_id"])
                rdf["player_id"] = rdf["player_id"].astype(int)
                owgr_map.update(dict(zip(rdf["player_id"], rdf["player_name"])))
            except Exception as e:
                print(f"  Could not load rankings file {rf.name}: {e}")

    # Optional odds map
    odds_map = {}
    if tournament_id:
        odds_path = DATA_DIR / "odds" / f"pga_odds_{tournament_id}.csv"
        if odds_path.exists():
            try:
                odds_df = pd.read_csv(odds_path)
                odds_map = dict(zip(odds_df['player_id'], odds_df['player_name']))
                print(f"  Using odds names from {odds_path.name}")
            except Exception as e:
                print(f"  Could not read odds file for names: {e}")

    fixed_names = []
    for _, row in df.iterrows():
        pid = row.get('player_id')
        name = row.get('player_name', '')
        placeholder = str(name).startswith('Player ') or pd.isna(name) or str(name).strip() == ''
        if not placeholder:
            fixed_names.append(name)
            continue

        # Try odds map first, then master, players DB, then OWGR
        mapped = None
        try:
            pid_int = int(pid) if pd.notna(pid) else pid
        except Exception:
            pid_int = pid

        if pd.notna(pid_int):
            mapped = odds_map.get(pid_int) or master_map.get(pid_int) or player_map.get(pid_int) or owgr_map.get(pid_int)

        fixed_names.append(mapped or name)

    df['player_name'] = fixed_names
    return df



def load_prior_year_stats(year: int = None) -> pd.DataFrame:
    """
    Load prior year's tournament stats for baseline SG calculations.
    
    Early in the season, current year data is sparse. Prior year provides
    a stable baseline that gets less weight as the season progresses.
    
    Args:
        year: Prior year to load (defaults to current year - 1)
    
    Returns:
        DataFrame with prior year tournament stats
    """
    if year is None:
        year = datetime.now().year - 1
    # Try DB first
    df = _load_tournament_stats_from_db(year)
    if not df.empty:
        print(f"  Loaded prior year ({year}) stats from DB for baseline SG calculations")
        return df
    prior_stats_file = HISTORICAL_DIR / f'tournament_stats_{year}.csv'
    if prior_stats_file.exists():
        print(f"  Loaded prior year ({year}) stats for baseline SG calculations")
        return pd.read_csv(prior_stats_file)
    else:
        print(f"  No prior year stats found for {year}")
        return pd.DataFrame()
        
        
    
def get_season_blend_weight(current_year_tournaments: int, month: int = None) -> float:
    """
    Calculate how much to weight current vs prior year stats.
    
    Early season (few tournaments): weight prior year more heavily
    Mid/late season (many tournaments): weight current year more heavily
    
    Args:
        current_year_tournaments: Number of tournaments player has in current year
        month: Current month (1-12), defaults to current month
    
    Returns:
        Float 0-1 representing weight for CURRENT year (1 - this = prior year weight)
    
    Examples:
        - January, 0 current tournaments: 0.2 (80% prior year)
        - February, 2 current tournaments: 0.4 (60% prior year)
        - April, 5+ current tournaments: 0.85 (15% prior year)
        - June+, any tournaments: 0.95 (5% prior year, just for stability)
    """
    if month is None:
        month = datetime.now().month
    
    # Base weight from number of current year tournaments
    # More tournaments = more confidence in current year data
    
    if current_year_tournaments == 0:
        tournament_weight = 0.0
    elif current_year_tournaments == 1:
        tournament_weight = 0.3
    elif current_year_tournaments == 2:
        tournament_weight = 0.5
    elif current_year_tournaments == 3:
        tournament_weight = 0.65
    elif current_year_tournaments == 4:
        tournament_weight = 0.75
    elif current_year_tournaments >= 5:
        tournament_weight = 0.85
        
        
    # Seasonal adjustment: later in year = trust current data more
    # PGA season runs Jan-Aug primarily
    if month <= 2:  # Jan-Feb: Early season, prior year very relevant
        seasonal_boost = 0.0
    elif month <= 4:  # Mar-Apr: Getting more data
        seasonal_boost = 0.05
    elif month <= 6:  # May-Jun: Mid-season
        seasonal_boost = 0.10
    else:  # Jul+: Late season, current year dominant
        seasonal_boost = 0.15
    
    # Combine: tournament count is primary driver, season provides small boost
    final_weight = min(0.95, tournament_weight + seasonal_boost)
    
    # Minimum 20% current year weight (never fully ignore current form)
    return max(0.2, final_weight)


def get_prior_year_sg_stats(player_id, prior_stats_df: pd.DataFrame) -> dict:
    """
    Get player's prior year season average SG stats.
    
    Args:
        player_id: Player ID
        prior_stats_df: DataFrame with prior year tournament stats
    
    Returns:
        Dict with prior_sg_* stats (season averages from prior year)
    """

    if prior_stats_df.empty:
        return {
             'prior_sg_total': np.nan,
            'prior_sg_ott': np.nan,
            'prior_sg_app': np.nan,
            'prior_sg_putt': np.nan,
            'prior_sg_t2g': np.nan,
            'prior_sg_arg': np.nan,
        }
    # Normalize player_id type to match stats_df (which stores as str)
    pid_str = str(int(player_id)) if player_id is not None else None

    # Filter to this player's average stats
    player_stats = prior_stats_df[
        (prior_stats_df['player_id'] == pid_str) &
        (prior_stats_df['stat_component'] == 'Avg')
    ].copy()

    if len(player_stats) == 0:
        return {
            'prior_sg_total': np.nan,
            'prior_sg_ott': np.nan,
            'prior_sg_app': np.nan,
            'prior_sg_putt': np.nan,
            'prior_sg_t2g': np.nan,
            'prior_sg_arg': np.nan,
        }

    # Stat ID mapping — use strings to match DB/CSV string stat_ids
    stat_mapping = {
        '2567': 'prior_sg_total',
        '2568': 'prior_sg_ott',
        '2569': 'prior_sg_app',
        '2564': 'prior_sg_putt',
        '2674': 'prior_sg_t2g'
    }
    
    #Pivot to get season averages 
    stats_pivot = player_stats.pivot_table(
        index='player_id', 
        columns='stat_id', 
        values='stat_value',
        aggfunc='mean'
    )
    result = {}
    for stat_id, stat_name in stat_mapping.items():
        if stat_id in stats_pivot.columns:
            result[stat_name] = stats_pivot[stat_id].iloc[0]
        else:
            result[stat_name] = np.nan 
    #Calculate prior_sg_arg from prior_sg_t2g - prior_sg_app
    if not np.isnan(result.get('prior_sg_t2g', np.nan)) and not np.isnan(result.get('prior_sg_app', np.nan)):
        result['prior_sg_arg'] = result['prior_sg_t2g'] - result['prior_sg_app']
    else:
        result['prior_sg_arg'] = np.nan
    
    return result


def blend_sg_stats(
    current_stats: dict,
    prior_stats: dict,
    current_year_tournaments: int,
    month: int = None
) -> dict:
    """
    Blend current and prior year SG stats based on data availability.
    
    Args:
        current_stats: Dict with current year sg_* and season_sg_* stats
        prior_stats: Dict with prior_sg_* stats
        current_year_tournaments: Number of tournaments in current year
        month: Current month for seasonal adjustment
    
    Returns:
        Dict with blended season_sg_* stats (replaces originals)
    """
    current_weight = get_season_blend_weight(current_year_tournaments, month)
    prior_weight = 1.0 - current_weight
    
    # Stats to blend (season averages used by model)
    sg_stats = ['sg_total', 'sg_ott', 'sg_app', 'sg_putt', 'sg_t2g', 'sg_arg']
    
    blended = current_stats.copy()
    
    for stat in sg_stats:
        current_key = f'season_{stat}'
        prior_key = f'prior_{stat}'
        
        current_val = current_stats.get(current_key, np.nan)
        prior_val = prior_stats.get(prior_key, np.nan)
        
        # Handle missing values
        if np.isnan(current_val) and np.isnan(prior_val):
            # Both missing: keep as NaN (will be filled later)
            blended[current_key] = np.nan
        elif np.isnan(current_val):
            # Only prior available: use prior
            blended[current_key] = prior_val
        elif np.isnan(prior_val):
            # Only current available: use current
            blended[current_key] = current_val
        else:
            # Both available: weighted blend
            blended[current_key] = (current_val * current_weight) + (prior_val * prior_weight)
    
    # Store blend info for debugging
    blended['sg_blend_current_weight'] = current_weight
    blended['sg_blend_prior_weight'] = prior_weight
    blended['sg_blend_tournaments'] = current_year_tournaments
    
    return blended


def get_recent_sg_stats(
    player_id,
    stats_df,
    method='last_5',
    weights=None,
    prior_stats_df=None,
    blend_with_prior=True
):
    """
    Get recent SG stats for a player from current year data,
    optionally blended with prior year for early-season stability.

    Args:
        player_id: Player ID
        stats_df: DataFrame with current year tournament stats
        method: 'season_avg', 'last_5', or 'weighted'
        weights: List of weights for weighted average [0.4, 0.3, 0.2, 0.1]
        prior_stats_df: DataFrame with prior year stats (for blending)
        blend_with_prior: Whether to blend with prior year stats

    Returns:
        Dict with sg_total, sg_ott, sg_app, sg_putt, sg_t2g, season_sg_* stats
        (blended with prior year if enabled)
    """
    # Stat ID mapping — use strings to match DB/CSV string stat_ids
    stat_mapping = {
        '2567': 'sg_total',
        '2568': 'sg_ott',
        '2569': 'sg_app',
        '2564': 'sg_putt',
        '2674': 'sg_t2g'
    }

    # Normalize player_id type to match stats_df (which stores as str)
    pid_str = str(int(player_id)) if player_id is not None else None

    # Filter stats for the player
    player_stats = stats_df[
        (stats_df['player_id'] == pid_str) &
        (stats_df['stat_component'] == 'Avg')
    ].copy()

    current_year_tournaments = player_stats['tournament_id'].nunique() if len(player_stats) > 0 else 0

    if len(player_stats) == 0:
        # No current year stats - will rely on prior year if available
        recent_stats = {
            'sg_total': np.nan,
            'sg_ott': np.nan,
            'sg_app': np.nan,
            'sg_arg': np.nan,
            'sg_putt': np.nan,
            'sg_t2g': np.nan,
            'season_sg_total': np.nan,
            'season_sg_ott': np.nan,
            'season_sg_app': np.nan,
            'season_sg_putt': np.nan,
            'season_sg_t2g': np.nan,
            'season_sg_arg': np.nan,
        }
        # Still compute recent form from prior-year data if available
        if prior_stats_df is not None and not prior_stats_df.empty:
            _prior_player = prior_stats_df[
                (prior_stats_df['player_id'] == pid_str) &
                (prior_stats_df['stat_component'] == 'Avg') &
                (prior_stats_df['stat_id'].astype(str) == '2567')
            ].sort_values('tournament_id')
            sg_vals = _prior_player['stat_value'].dropna().values
            if len(sg_vals) > 0:
                _n = min(8, len(sg_vals))
                _window = sg_vals[-_n:][::-1]
                _w = np.array([0.85**i for i in range(_n)], dtype=float)
                _w /= _w.sum()
                recent_stats['recent_sg_weighted'] = float(np.dot(_window, _w))
                if len(sg_vals) >= 4:
                    _last3 = float(np.mean(sg_vals[-3:]))
                    _older = sg_vals[-8:-3] if len(sg_vals) >= 8 else sg_vals[:-3]
                    recent_stats['recent_sg_trend'] = float(_last3 - np.mean(_older)) if len(_older) > 0 else 0.0
                else:
                    recent_stats['recent_sg_trend'] = 0.0
    else:
        # Pivot stats to wide format
        stats_pivot = player_stats.pivot_table(
            index='tournament_id',
            columns='stat_id',
            values='stat_value',
            aggfunc='first'
        )
        stats_pivot = stats_pivot.sort_index()

        # Apply selected method for per-tournament stats
        if method == 'season_avg':
            recent_stats = {}
            for stat_id, stat_name in stat_mapping.items():
                if stat_id in stats_pivot.columns:
                    recent_stats[stat_name] = stats_pivot[stat_id].mean()
                else:
                    recent_stats[stat_name] = np.nan

        elif method == 'last_5':
            recent_tournaments = stats_pivot.tail(5)
            recent_stats = {}
            for stat_id, stat_name in stat_mapping.items():
                if stat_id in recent_tournaments.columns:
                    recent_stats[stat_name] = recent_tournaments[stat_id].mean()
                else:
                    recent_stats[stat_name] = np.nan

        elif method == 'weighted':
            if weights is None:
                weights = [0.4, 0.3, 0.2, 0.1]
            n = len(weights)
            recent_tournaments = stats_pivot.tail(n)
            actual_n = len(recent_tournaments)
            if actual_n < n:
                weights = weights[-actual_n:]
                total_weight = sum(weights)
                weights = [w / total_weight for w in weights]

            recent_stats = {}
            for stat_id, stat_name in stat_mapping.items():
                if stat_id in recent_tournaments.columns:
                    values = recent_tournaments[stat_id].values
                    weighted_avg = np.average(values, weights=weights)
                    recent_stats[stat_name] = weighted_avg
                else:
                    recent_stats[stat_name] = np.nan
        else:
            raise ValueError(f"Unknown method: {method}. Use 'season_avg', 'last_5', or 'weighted'")

        # Compute season averages (full season)
        for stat_id, stat_name in stat_mapping.items():
            season_key = f'season_{stat_name}'
            if stat_id in stats_pivot.columns:
                recent_stats[season_key] = stats_pivot[stat_id].mean()
            else:
                recent_stats[season_key] = np.nan

        # Calculate sg_arg
        sg_t2g = recent_stats.get('sg_t2g', np.nan)
        sg_app = recent_stats.get('sg_app', np.nan)
        if not np.isnan(sg_t2g) and not np.isnan(sg_app):
            recent_stats['sg_arg'] = sg_t2g - sg_app
        else:
            recent_stats['sg_arg'] = np.nan

        # Calculate season_sg_arg
        season_t2g = recent_stats.get('season_sg_t2g', np.nan)
        season_app = recent_stats.get('season_sg_app', np.nan)
        if not np.isnan(season_t2g) and not np.isnan(season_app):
            recent_stats['season_sg_arg'] = season_t2g - season_app
        else:
            recent_stats['season_sg_arg'] = np.nan

        # ── Recent form: exponential decay + trend ─────────────────────────
        # Mirrors the training-data computation in merge_all_historical_data.py.
        # Cross-year: combine prior-year sg_total values (older) with current-year
        # values (newer) so the 8-event window spans year boundaries.
        # This matters early in the season when players have <4 current-year events.
        sg_total_col = '2567'
        # Current-year values (sorted ascending by tournament_id already)
        cur_sg = stats_pivot[sg_total_col].dropna().values if sg_total_col in stats_pivot.columns else np.array([])

        # Prior-year values for this player (sorted ascending by tournament_id)
        prior_sg = np.array([])
        if prior_stats_df is not None and not prior_stats_df.empty:
            _prior_player = prior_stats_df[
                (prior_stats_df['player_id'] == pid_str) &
                (prior_stats_df['stat_component'] == 'Avg') &
                (prior_stats_df['stat_id'].astype(str) == sg_total_col)
            ].sort_values('tournament_id')
            prior_sg = _prior_player['stat_value'].dropna().values

        # Combine: prior events first, then current events (chronological order)
        sg_vals = np.concatenate([prior_sg, cur_sg]) if len(prior_sg) > 0 else cur_sg

        if len(sg_vals) > 0:
            _n = min(8, len(sg_vals))
            _window = sg_vals[-_n:][::-1]          # most recent at index 0
            _w = np.array([0.85**i for i in range(_n)], dtype=float)
            _w /= _w.sum()
            recent_stats['recent_sg_weighted'] = float(np.dot(_window, _w))
            if len(sg_vals) >= 4:
                _last3 = float(np.mean(sg_vals[-3:]))
                _older = sg_vals[-8:-3] if len(sg_vals) >= 8 else sg_vals[:-3]
                recent_stats['recent_sg_trend'] = float(_last3 - np.mean(_older)) if len(_older) > 0 else 0.0
            else:
                recent_stats['recent_sg_trend'] = 0.0
        else:
            recent_stats['recent_sg_weighted'] = np.nan
            recent_stats['recent_sg_trend'] = 0.0

        # Per-category recent form (OTT, APP, PUTT) — same decay window as sg_total
        _SG_CAT = {'2568': 'recent_sg_ott_weighted',
                   '2569': 'recent_sg_app_weighted',
                   '2564': 'recent_sg_putt_weighted'}
        for _cat_id, _cat_col in _SG_CAT.items():
            _cur_cat = stats_pivot[_cat_id].dropna().values if _cat_id in stats_pivot.columns else np.array([])
            _prior_cat = np.array([])
            if prior_stats_df is not None and not prior_stats_df.empty:
                _pc = prior_stats_df[
                    (prior_stats_df['player_id'] == pid_str) &
                    (prior_stats_df['stat_component'] == 'Avg') &
                    (prior_stats_df['stat_id'].astype(str) == _cat_id)
                ].sort_values('tournament_id')
                _prior_cat = _pc['stat_value'].dropna().values
            _cat_vals = np.concatenate([_prior_cat, _cur_cat]) if len(_prior_cat) > 0 else _cur_cat
            if len(_cat_vals) > 0:
                _cn = min(8, len(_cat_vals))
                _cw = np.array([0.85**i for i in range(_cn)], dtype=float)
                _cw /= _cw.sum()
                recent_stats[_cat_col] = float(np.dot(_cat_vals[-_cn:][::-1], _cw))
            else:
                recent_stats[_cat_col] = np.nan

    # Blend with prior year stats if enabled
    if blend_with_prior and prior_stats_df is not None and not prior_stats_df.empty:
        prior_stats = get_prior_year_sg_stats(player_id, prior_stats_df)
        recent_stats = blend_sg_stats(
            recent_stats,
            prior_stats,
            current_year_tournaments
        )

    return recent_stats

    

    
    
def load_course_weights():
    """Load Data Golf course SG importance weights."""
    weights_path = DATA_DIR / "course_sg_weights.csv"
    if weights_path.exists():
        return pd.read_csv(weights_path)
    return pd.DataFrame()


def add_course_fit_features(features_df, tournament_name):
    """
    Add Data Golf course fit features to prediction DataFrame.

    Uses season_sg_* (prior performance) × course importance weights.
    This avoids data leakage by not using same-tournament SG stats.

    Args:
        features_df: DataFrame with player features including season_sg_* columns
        tournament_name: Tournament name to look up course weights

    Returns:
        DataFrame with dg_fit_* columns added
    """
    # Load course weights
    course_weights = load_course_weights()

    # Default weights for tournaments not in mapping
    default_weights = {'ott_sg': 0.020, 'app_sg': 0.020, 'arg_sg': 0.025, 'putt_sg': 0.005}

    # Look up weights for this tournament
    weights = default_weights.copy()
    if not course_weights.empty:
        match = course_weights[course_weights['tournament_name'] == tournament_name]
        if len(match) == 0:
            # Substring fallback (same logic as insights section)
            search_term = tournament_name.lower().replace('the ', '')
            match = course_weights[
                course_weights['tournament_name'].str.lower().str.contains(search_term, na=False)
            ]
            if len(match) > 0:
                print(f"    Fuzzy-matched course weights: '{match.iloc[0]['tournament_name']}'")
        if len(match) > 0:
            row = match.iloc[0]
            weights = {
                'ott_sg': row['ott_sg'],
                'app_sg': row['app_sg'],
                'arg_sg': row['arg_sg'],
                'putt_sg': row['putt_sg']
            }
            if match.iloc[0]['tournament_name'] == tournament_name:
                print(f"    Found course weights for {tournament_name}")
        else:
            print(f"    Using default weights (tournament '{tournament_name}' not in mapping)")

    # Calculate season_sg_arg if not present
    if 'season_sg_arg' not in features_df.columns:
        if 'season_sg_t2g' in features_df.columns and 'season_sg_app' in features_df.columns:
            features_df['season_sg_arg'] = features_df['season_sg_t2g'].fillna(0) - features_df['season_sg_app'].fillna(0)
        else:
            features_df['season_sg_arg'] = 0.0

    # Calculate fit scores (scaled by 10 for interpretability)
    scale = 10.0

    sg_ott = features_df['season_sg_ott'].fillna(0)
    sg_app = features_df['season_sg_app'].fillna(0)
    sg_arg = features_df['season_sg_arg'].fillna(0)
    sg_putt = features_df['season_sg_putt'].fillna(0)

    features_df['dg_fit_ott'] = sg_ott * weights['ott_sg'] * scale
    features_df['dg_fit_app'] = sg_app * weights['app_sg'] * scale
    features_df['dg_fit_arg'] = sg_arg * weights['arg_sg'] * scale
    features_df['dg_fit_putt'] = sg_putt * weights['putt_sg'] * scale

    # DataGolf predictive SG weights: OTT=1.2, APP=1.0, ARG=0.9, PUTT=0.6 (total=3.7)
    _dg_total = 3.7
    features_df['predictive_sg_weighted'] = (
        sg_ott  * (1.2 / _dg_total) +
        sg_app  * (1.0 / _dg_total) +
        sg_arg  * (0.9 / _dg_total) +
        sg_putt * (0.6 / _dg_total)
    )

    # dg_fit_total weighted by DataGolf predictive coefficients
    features_df['dg_fit_total'] = (
        features_df['dg_fit_ott']  * 1.2 +
        features_df['dg_fit_app']  * 1.0 +
        features_df['dg_fit_arg']  * 0.9 +
        features_df['dg_fit_putt'] * 0.6
    ) / _dg_total

    print(f"    Course fit range: {features_df['dg_fit_total'].min():.3f} to {features_df['dg_fit_total'].max():.3f}")

    return features_df


def load_tournament_course_mapping():
    """Load tournament-to-course mapping from JSON."""
    mapping_path = DATA_DIR / "reference" / "tournament_courses.json"
    if not mapping_path.exists():
        return {}
    with open(mapping_path, 'r') as f:
        data = json.load(f)
    return data.get("tournaments", {})


def normalize_course_key(text):
    """Normalize text for course key matching."""
    if not text:
        return ""
    import re
    text = str(text).lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"\(\s*\d{4}\s*\)", "", text)  # Remove year suffixes
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def get_course_for_tournament(tournament_name: str) -> dict:
    """
    Look up the course information for a tournament.

    Returns dict with keys: course_name, course_full_name, course_key, course_type
    """
    mapping = load_tournament_course_mapping()

    # Normalize tournament name for matching
    name_key = normalize_course_key(tournament_name)

    # Try direct match first
    for tourn_name, details in mapping.items():
        if normalize_course_key(tourn_name) == name_key:
            return {
                "course_name": details.get("course", "Unknown"),
                "course_full_name": details.get("course_full", details.get("course", "Unknown")),
                "course_key": normalize_course_key(details.get("course_full", details.get("course", "Unknown"))),
                "course_type": details.get("course_type", "unknown"),
            }
        # Check aliases
        for alias in details.get("aliases", []):
            if normalize_course_key(alias) == name_key:
                return {
                    "course_name": details.get("course", "Unknown"),
                    "course_full_name": details.get("course_full", details.get("course", "Unknown")),
                    "course_key": normalize_course_key(details.get("course_full", details.get("course", "Unknown"))),
                    "course_type": details.get("course_type", "unknown"),
                }

    return {"course_name": "Unknown", "course_full_name": "Unknown", "course_key": "unknown", "course_type": "unknown"}


def add_course_performance_features(features_df: pd.DataFrame, tournament_name: str) -> pd.DataFrame:
    """
    Add player course-specific performance features from form stats consolidation.

    Uses data/processed/player_course_performance.csv which contains:
    - Per-course stats (driving, GIR, scrambling, etc.)
    - Made cut rate, top 10 rate, win rate at this specific course
    - Recency-weighted averages

    Args:
        features_df: DataFrame with player features (must have player_id column)
        tournament_name: Tournament name to look up course

    Returns:
        DataFrame with course performance features added
    """
    course_perf_path = PROCESSED_DIR / "player_course_performance.csv"

    if not course_perf_path.exists():
        print("    Course performance data not found, skipping...")
        return features_df

    # Get course for this tournament
    course_info = get_course_for_tournament(tournament_name)
    course_key = course_info["course_key"]

    if course_key == "unknown":
        print(f"    Course not found for '{tournament_name}', skipping course performance features...")
        return features_df

    print(f"    Course: {course_info['course_full_name']} ({course_info['course_type']})")

    # Load course performance data
    course_perf = pd.read_csv(course_perf_path)

    # Filter to this course
    course_data = course_perf[course_perf["course_key"] == course_key].copy()

    if course_data.empty:
        print(f"    No historical data for course '{course_key}', skipping...")
        return features_df

    print(f"    Found {len(course_data)} players with history at this course")

    # Select features to merge (avoid duplicate columns)
    # These are the most predictive course-specific features
    feature_cols = [
        "player_id",
        "starts",              # Times played at this course
        "made_cut_rate",       # Cut rate at this course
        "top_10_rate",         # Top-10 rate at this course
        "top_20_rate",         # Top-20 rate at this course
        "win_rate",            # Win rate at this course
        "avg_finish",          # Average finish at this course
        "best_finish",         # Best finish at this course
        "avg_to_par",          # Average score to par at this course
        "avg_earnings",        # Average earnings at this course
        "last_season",         # Most recent year played here
    ]

    # Add Strokes Gained course-specific columns (recency-weighted + vs average)
    sg_cols = [
        "course_sg_total_avg",       # Mean SG:Total at this course (historical)
        "course_sg_ott_avg",         # Mean SG:OTT at this course (historical)
        "course_sg_app_avg",         # Mean SG:Approach at this course (historical)
        "course_sg_putt_avg",        # Mean SG:Putting at this course (historical)
        "course_sg_t2g_avg",         # Mean SG:T2G at this course (historical)
        "course_sg_total_weighted",  # Recency-weighted SG:Total at this course
        "course_sg_ott_weighted",    # Recency-weighted SG:OTT at this course
        "course_sg_app_weighted",    # Recency-weighted SG:Approach at this course
        "course_sg_putt_weighted",   # Recency-weighted SG:Putting at this course
        "course_sg_t2g_weighted",    # Recency-weighted SG:Tee-to-Green at this course
        "course_sg_trend",           # Year-over-year trend in SG:Total at this course
        "course_sg_recent_vs_early", # Recent SG vs early SG at this course
        "course_sg_total_vs_avg",    # Course SG vs player's overall average (edge)
        "course_sg_ott_vs_avg",      # OTT edge at this course
        "course_sg_app_vs_avg",      # Approach edge at this course
        "course_sg_putt_vs_avg",     # Putting edge at this course
        "course_sg_t2g_vs_avg",      # T2G edge at this course
        "overall_sg_total_avg",      # Player's overall SG:Total for comparison
    ]
    feature_cols.extend([c for c in sg_cols if c in course_data.columns])

    # Add form stat columns if available (weighted versions for recency)
    stat_cols = [c for c in course_data.columns if c.startswith("stat_") and c.endswith("_weighted")]
    feature_cols.extend(stat_cols[:10])  # Limit to top 10 stat columns

    # Filter to available columns
    available_cols = [c for c in feature_cols if c in course_data.columns]
    course_subset = course_data[available_cols].copy()

    # Rename columns to indicate course-specific (but don't double-prefix columns that already have course_/overall_)
    rename_map = {
        c: f"course_{c}"
        for c in available_cols
        if c != "player_id" and not c.startswith("course_") and not c.startswith("overall_")
    }
    course_subset = course_subset.rename(columns=rename_map)

    # Deduplicate course_subset to one row per player before merging.
    # player_course_performance.csv can have multiple rows per player per course
    # (e.g., separate records for 2023 and 2025 appearances). Merging without
    # deduplication produces cartesian-product duplicates in the output.
    # Sort by last_season descending so keep='first' retains the most recent row.
    if "last_season" in course_subset.columns:
        course_subset = (
            course_subset
            .sort_values("last_season", ascending=False)
            .drop_duplicates(subset=["player_id"], keep="first")
            .reset_index(drop=True)
        )
    else:
        course_subset = course_subset.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)

    # Merge with features
    original_len = len(features_df)
    features_df = features_df.merge(course_subset, on="player_id", how="left")

    # Guard: if merge accidentally multiplied rows, deduplicate and warn
    if len(features_df) != original_len:
        print(f"    WARNING: course merge changed row count {original_len} → {len(features_df)}. Deduplicating.")
        features_df = features_df.drop_duplicates(subset=["player_id"], keep="first").reset_index(drop=True)

    # Fill missing values (players without course history)
    course_cols = [c for c in features_df.columns if c.startswith("course_")]
    overall_cols = [c for c in features_df.columns if c.startswith("overall_")]

    for col in course_cols:
        if col == "course_starts":
            features_df[col] = features_df[col].fillna(0)
        elif col in ["course_made_cut_rate", "course_top_10_rate", "course_top_20_rate", "course_win_rate"]:
            # Use field median for players without course history
            features_df[col] = features_df[col].fillna(features_df[col].median())
        elif col == "course_avg_finish":
            features_df[col] = features_df[col].fillna(40.0)  # Assume middle of pack
        elif col == "course_best_finish":
            features_df[col] = features_df[col].fillna(40.0)
        elif col == "course_avg_to_par":
            features_df[col] = features_df[col].fillna(0.0)  # Even par as default
        elif "_vs_avg" in col:
            # Course edge columns: 0 = no edge (performs same as usual)
            features_df[col] = features_df[col].fillna(0.0)
        elif "_weighted" in col and "sg_" in col:
            # SG weighted columns: use player's overall average if available, else 0
            # e.g., course_sg_total_weighted -> overall_sg_total_avg
            overall_col = col.replace("course_sg_", "overall_sg_").replace("_weighted", "_avg")
            if overall_col in features_df.columns:
                features_df[col] = features_df[col].fillna(features_df[overall_col])
            features_df[col] = features_df[col].fillna(0.0)
        else:
            features_df[col] = features_df[col].fillna(0.0)

    # Fill overall SG avg columns
    for col in overall_cols:
        features_df[col] = features_df[col].fillna(0.0)

    # Ensure similar-course fallback columns always exist for downstream logic
    if "has_similar_course_data" not in features_df.columns:
        features_df["has_similar_course_data"] = False
    if "similar_course_sg_estimate" not in features_df.columns:
        features_df["similar_course_sg_estimate"] = np.nan

    # Compatibility aliases for training/inference feature parity.
    if "course_sg_starts" not in features_df.columns:
        if "course_starts" in features_df.columns:
            features_df["course_sg_starts"] = pd.to_numeric(features_df["course_starts"], errors="coerce").fillna(0)
        else:
            features_df["course_sg_starts"] = 0.0
    if "course_sg_total_vs_avg" not in features_df.columns and "course_sg_vs_avg" in features_df.columns:
        features_df["course_sg_total_vs_avg"] = pd.to_numeric(features_df["course_sg_vs_avg"], errors="coerce")
    if "course_sg_vs_avg" not in features_df.columns and "course_sg_total_vs_avg" in features_df.columns:
        features_df["course_sg_vs_avg"] = pd.to_numeric(features_df["course_sg_total_vs_avg"], errors="coerce")

    # Reliability score for course signal (more starts -> higher confidence)
    starts_num = pd.to_numeric(features_df.get("course_starts", 0), errors="coerce").fillna(0).clip(lower=0)
    features_df["course_history_confidence"] = (np.log1p(starts_num) / np.log(6.0)).clip(0, 1)

    # Add derived features
    features_df["has_course_form_history"] = features_df["course_starts"] > 0
    features_df["has_course_sg_history"] = pd.to_numeric(
        features_df.get("course_sg_starts", 0), errors="coerce"
    ).fillna(0) > 0
    features_df["course_experience_tier"] = pd.cut(
        features_df["course_starts"],
        bins=[-1, 0, 1, 2, 4, float("inf")],
        labels=["none", "rookie", "familiar", "experienced", "veteran"]
    )

    # Calculate course fit boost based on historical performance
    # This combines multiple signals into a single adjustment factor
    # Enhanced with SG course edge data
    base_perf_score = (
        features_df["course_top_10_rate"].fillna(0) * 2.0 +
        features_df["course_made_cut_rate"].fillna(0) * 1.0 +
        features_df["course_win_rate"].fillna(0) * 5.0 -
        (features_df["course_avg_finish"].fillna(40) / 40.0)  # Lower finish = higher score
    )

    # Add SG course edge bonus (how much better player performs at this course)
    sg_edge_bonus = 0.0
    if "course_sg_total_vs_avg" in features_df.columns:
        # SG edge: +0.5 SG vs avg = very strong course fit
        sg_edge_bonus = features_df["course_sg_total_vs_avg"].fillna(0) * 1.0

    features_df["course_perf_score"] = base_perf_score + sg_edge_bonus

    matched = features_df["has_course_form_history"].sum()
    print(f"    Matched {matched}/{original_len} players with course history ({matched/original_len*100:.1f}%)")

    if matched > 0:
        avg_starts = features_df.loc[features_df["has_course_form_history"], "course_starts"].mean()
        print(f"    Average starts at course: {avg_starts:.1f}")

    # Try to fill in similar course performance for players without direct history
    no_history = features_df[~features_df["has_course_form_history"]].copy()
    if len(no_history) > 0:
        features_df = add_similar_course_performance(features_df, course_key, course_perf)

    return features_df


def add_similar_course_performance(features_df: pd.DataFrame, course_key: str, course_perf: pd.DataFrame) -> pd.DataFrame:
    """
    For players without direct course history, estimate performance using similar courses.
    """
    # Load similarity data
    sim_path = PROCESSED_DIR / "course_similarity_matrix.csv"
    if not sim_path.exists():
        return features_df

    try:
        sim_matrix = pd.read_csv(sim_path, index_col=0)
    except Exception:
        return features_df

    # Find similar courses
    if course_key not in sim_matrix.index:
        # Try fuzzy match
        matches = [c for c in sim_matrix.index if course_key in c or c in course_key]
        if matches:
            course_key = matches[0]
        else:
            return features_df

    similarities = sim_matrix[course_key].sort_values(ascending=False)
    similar_courses = [(k, v) for k, v in similarities.items() if k != course_key and v > 0.6][:5]

    if not similar_courses:
        return features_df

    if "has_similar_course_data" not in features_df.columns:
        features_df["has_similar_course_data"] = False
    if "similar_course_sg_estimate" not in features_df.columns:
        features_df["similar_course_sg_estimate"] = np.nan

    # For each player without history, estimate from similar courses
    no_history_mask = ~features_df["has_course_form_history"]
    similar_estimates = 0

    for idx in features_df[no_history_mask].index:
        player_id = features_df.loc[idx, "player_id"]

        # Get player's performance at similar courses
        player_data = course_perf[course_perf["player_id"] == player_id]
        if player_data.empty:
            continue

        weighted_sg = 0.0
        total_weight = 0.0

        for sim_course_key, similarity in similar_courses:
            perf_at_sim = player_data[player_data["course_key"] == sim_course_key]
            if perf_at_sim.empty:
                continue

            row = perf_at_sim.iloc[0]
            sg_total = row.get("course_sg_total_weighted")
            if pd.isna(sg_total):
                continue

            starts = row.get("starts", 1)
            weight = similarity * min(starts, 3) / 3
            weighted_sg += sg_total * weight
            total_weight += weight

        if total_weight > 0:
            estimated_sg = weighted_sg / total_weight
            # Add to features with reduced confidence (50% weight)
            features_df.loc[idx, "similar_course_sg_estimate"] = estimated_sg
            features_df.loc[idx, "has_similar_course_data"] = True
            # Partially update course_perf_score for these players
            features_df.loc[idx, "course_perf_score"] = estimated_sg * 0.5
            similar_estimates += 1

    if similar_estimates > 0:
        print(f"    Added similar course estimates for {similar_estimates} players without direct history")

    return features_df


def normalize_venue_name(tournament_name):
    """
    Normalize tournament name to match training data format

    Must match the normalization used in merge_all_historical_data.py

    Example:
        "The Masters" → "THE MASTERS"
        "American Express" → "THE AMERICAN EXPRESS"
        "AT&T Pebble Beach Pro-Am" → "ATANDT PEBBLE BEACH PROAM"

    Note: Adds "THE" prefix for tournaments commonly known with it
    """
    import re
    # Replace & with AND BEFORE removing special chars (so AT&T -> ATANDT)
    normalized = tournament_name.upper().replace("&", "AND").replace("'", "")
    normalized = re.sub(r'[^\w\s]', '', normalized).strip()

    # Add "THE" prefix for tournaments that have it in historical data
    # Check if venue needs "THE" prefix by looking in master data
    tournaments_with_the = [
        'AMERICAN EXPRESS',
        'MASTERS',
        'PLAYERS CHAMPIONSHIP',
        'MEMORIAL TOURNAMENT',
        'TOUR CHAMPIONSHIP',
        'NORTHERN TRUST',
        'OPEN CHAMPIONSHIP',
        'CJ CUP',
        'RSM CLASSIC',
        'HONDA CLASSIC',
        'GENESIS INVITATIONAL',
        'SENTRY'
    ]

    # Normalize common aliases to match historical data
    alias_map = {
        "WM PHOENIX OPEN": "WASTE MANAGEMENT PHOENIX OPEN",
        "WASTE MANAGEMENT PHOENIX OPEN": "WASTE MANAGEMENT PHOENIX OPEN",
        # Pebble Beach variations (all map to master data format)
        "ATANDT PEBBLE BEACH PROAM": "ATANDT PEBBLE BEACH PROAM",
        "ATANDT PEBBLE BEACH PRO AM": "ATANDT PEBBLE BEACH PROAM",
        "ATT PEBBLE BEACH PROAM": "ATANDT PEBBLE BEACH PROAM",
        "ATT PEBBLE BEACH PRO AM": "ATANDT PEBBLE BEACH PROAM",
        "PEBBLE BEACH PROAM": "ATANDT PEBBLE BEACH PROAM",
        # American Express
        "AMERICAN EXPRESS": "THE AMERICAN EXPRESS",
        "THE AMERICAN EXPRESS": "THE AMERICAN EXPRESS",
        # RSM Classic
        "RSM CLASSIC": "THE RSM CLASSIC",
        "THE RSM CLASSIC": "THE RSM CLASSIC",
        # Genesis
        "GENESIS INVITATIONAL": "THE GENESIS INVITATIONAL",
        "THE GENESIS INVITATIONAL": "THE GENESIS INVITATIONAL",
        # Arnold Palmer (Bay Hill) — sponsor suffix
        "ARNOLD PALMER INVITATIONAL": "ARNOLD PALMER INVITATIONAL PRESENTED BY MASTERCARD",
        "ARNOLD PALMER INVITATIONAL PRESENTED BY MASTERCARD": "ARNOLD PALMER INVITATIONAL PRESENTED BY MASTERCARD",
        # Cognizant Classic / Honda Classic — SAME COURSE (PGA National)
        # Map to THE HONDA CLASSIC which has 8 years of data (2016-2023)
        "HONDA CLASSIC": "THE HONDA CLASSIC",
        "THE HONDA CLASSIC": "THE HONDA CLASSIC",
        "COGNIZANT CLASSIC": "THE HONDA CLASSIC",
        "COGNIZANT CLASSIC IN THE PALM BEACHES": "THE HONDA CLASSIC",
        # Memorial Tournament (Muirfield Village) — same course, different sponsors
        "THE MEMORIAL TOURNAMENT": "THE MEMORIAL TOURNAMENT PRESENTED BY NATIONWIDE",
        "THE MEMORIAL TOURNAMENT PRESENTED BY WORKDAY": "THE MEMORIAL TOURNAMENT PRESENTED BY NATIONWIDE",
        "THE MEMORIAL TOURNAMENT PRESENTED BY NATIONWIDE": "THE MEMORIAL TOURNAMENT PRESENTED BY NATIONWIDE",
        # Truist / Wells Fargo (Quail Hollow) — same course
        "TRUIST CHAMPIONSHIP": "WELLS FARGO CHAMPIONSHIP",
        "WELLS FARGO CHAMPIONSHIP": "WELLS FARGO CHAMPIONSHIP",
        # Colonial CC (Dean & Deluca → Fort Worth → Charles Schwab Challenge)
        "DEAN AND DELUCA INVITATIONAL": "CHARLES SCHWAB CHALLENGE",
        "FORT WORTH INVITATIONAL": "CHARLES SCHWAB CHALLENGE",
        "CHARLES SCHWAB CHALLENGE": "CHARLES SCHWAB CHALLENGE",
        # American Express / PGA West (Desert Classic, CareerBuilder)
        "CAREERBUILDER CHALLENGE": "THE AMERICAN EXPRESS",
        "CAREERBUILDER CHALLENGE IN PARTNERSHIP WITH THE CLINTON FOUNDATION": "THE AMERICAN EXPRESS",
        "DESERT CLASSIC": "THE AMERICAN EXPRESS",
        # Genesis Invitational (Riviera)
        "GENESIS OPEN": "THE GENESIS INVITATIONAL",
        # Sentry / Kapalua — same course
        "THE SENTRY": "SENTRY TOURNAMENT OF CHAMPIONS",
        "HYUNDAI TOURNAMENT OF CHAMPIONS": "SENTRY TOURNAMENT OF CHAMPIONS",
        "SBS TOURNAMENT OF CHAMPIONS": "SENTRY TOURNAMENT OF CHAMPIONS",
        "SENTRY TOURNAMENT OF CHAMPIONS": "SENTRY TOURNAMENT OF CHAMPIONS",
        # Shriners (TPC Summerlin) — keep HOSPITALS as canonical (852 rows vs 552)
        "SHRINERS HOSPITALS FOR CHILDREN OPEN": "SHRINERS HOSPITALS FOR CHILDREN OPEN",
        "SHRINERS CHILDRENS OPEN": "SHRINERS HOSPITALS FOR CHILDREN OPEN",
        # Rocket Mortgage / Rocket Classic (Detroit Golf Club)
        "ROCKET CLASSIC": "ROCKET MORTGAGE CLASSIC",
        "ROCKET MORTGAGE CLASSIC": "ROCKET MORTGAGE CLASSIC",
        # Mexico Open (Vidanta Vallarta)
        "MEXICO OPEN AT VIDANTAWORLD": "MEXICO OPEN AT VIDANTA",
        "MEXICO OPEN AT VIDANTA": "MEXICO OPEN AT VIDANTA",
        # Myrtle Beach Classic
        "ONEFLIGHT MYRTLE BEACH CLASSIC": "MYRTLE BEACH CLASSIC",
        "MYRTLE BEACH CLASSIC": "MYRTLE BEACH CLASSIC",
    }
    if normalized in alias_map:
        normalized = alias_map[normalized]

    # If normalized name is in the list and doesn't start with THE, add it
    if normalized in tournaments_with_the and not normalized.startswith('THE '):
        normalized = 'THE ' + normalized

    return normalized


# Step 4: Look up course history 

def get_course_history(player_id, venue_clean, master_df):
    """
    Get players' historical performance at the venue

    Args:
        player_id: Player ID
        venue_clean: Normalized venue name
        master_df: Master training DataFrame
    Returns:
        Dict with hist_* features
    """
    #Filter to this player at this venue (past years only)

    history = master_df[
                        (master_df['player_id'] == player_id)
                        & (master_df['venue_clean'] == venue_clean)].copy()

    if len(history) == 0:
        # No history - return defaults (must match column names when history exists)
        return {
            'hist_times_played': 0,
            'hist_avg_finish': 40.0,  # Default: middle of field
            'hist_best_finish': 40.0,
            'hist_wins': 0,
            'hist_top5s': 0,
            'hist_top10s': 0,
            'hist_cut_rate': 0.5,  # Default: neutral
            'hist_missed_cuts': 0,
            'has_won_here': 0,
            'has_course_history': 0,
            'has_made_cut_here': 0,
        }

    # Separate made cuts vs missed cuts (999 = missed cut)
    made_cuts = history[history['position_num'] < 100]
    missed_cuts = history[history['position_num'] >= 100]

    # Calculate cut rate
    total_starts = len(history)
    cuts_made = len(made_cuts)
    cut_rate = cuts_made / total_starts if total_starts > 0 else 0
    wins_at_venue = (history['position_num'] == 1).sum()

    # Calculate hist_avg_finish with defaults for MC-only history
    if len(made_cuts) > 0:
        avg_finish = made_cuts['position_num'].mean()
        best_finish = made_cuts['position_num'].min()
    else:
        avg_finish = 70.0  # MC-only history
        best_finish = 70.0

    return {
        'hist_times_played': len(history),
        'hist_avg_finish': avg_finish,
        'hist_best_finish': best_finish,
        'hist_wins': wins_at_venue,
        'hist_top5s': (history['position_num'] <= 5).sum(),
        'hist_top10s': (history['position_num'] <= 10).sum(),
        'hist_cut_rate': cut_rate,
        'hist_missed_cuts': len(missed_cuts),
        'has_won_here': 1 if wins_at_venue > 0 else 0,
        'has_course_history': 1,
        'has_made_cut_here': 1 if cuts_made > 0 else 0,
    }
    
    
    
def get_tournament_winner_boost(player_id, venue_clean, master_df):
    """
    Check if player has won at this venue before
    Returns 1 if they've won, 0 otherwise
    
    This is a powerful predictor - past winners have significantly higher win rates
    
    Args:
        player_id: Player ID
        venue_clean: Normalized venue name
        master_df: Master training DataFrame
    
    Returns:
        Dict with has_won_here feature
    """
    history = master_df[
        (master_df['player_id'] == player_id) & 
        (master_df['venue_clean'] == venue_clean)
    ]
    
    if len(history) == 0:
        return {'has_won_here': 0}
    
    # Check if player has any wins at this venue
    wins = (history['position_num'] == 1).sum()
    
    return {
        'has_won_here': 1 if wins > 0 else 0,
        'wins_at_venue': int(wins)  # Store count for reference
    }


def _parse_pos_num(pos_str) -> float:
    """Convert position string ('T3', 'MC', 'WD', '1') to a numeric value.
    Missed cut / withdrawn / disqualified → 999.
    """
    if pd.isna(pos_str):
        return 999.0
    s = str(pos_str).upper().strip().lstrip("T").lstrip("=")
    if s in ("MC", "CUT", "MDF", "WD", "DQ", "W/D", "DNS", "RTD", "DSQ"):
        return 999.0
    try:
        return float(s)
    except ValueError:
        return 999.0


def add_situational_features(
    features_df: pd.DataFrame,
    tournament_name: str,
    master_df: pd.DataFrame,
    tournament_id: str = None,
) -> pd.DataFrame:
    """
    Add narrative/situational features that capture event-specific context.

    Features added:
      is_defending_champion  — Won this tournament in the most recent prior year
      first_start_of_season  — Player has no starts yet in the current season
      last_start_position    — Numeric finishing position of most recent start (999 = MC/WD)
      post_top5_last_start   — Most recent start was a top-5 finish (binary)
      missed_cut_last_start  — Most recent start was a missed cut (binary)
      consecutive_top10s     — Streak of consecutive top-10 finishes going into this week
      pre_major_flag         — Next tournament on schedule is a Major (same for all players)
    """
    features_df = features_df.copy()

    # ── 1. Current-year leaderboard (for recent-result features) ─────────────
    current_year = datetime.now().year
    lb_path = HISTORICAL_DIR / f"leaderboards_{current_year}.csv"
    if lb_path.exists():
        lb = pd.read_csv(lb_path)
        lb["player_id"] = lb["player_id"].astype(str).str.strip()
        lb["pos_num"] = lb["position"].apply(_parse_pos_num)
        # Exclude the current tournament only (by exact ID match).
        # Do NOT use tournament_id < current_id: PGA R-IDs are not assigned
        # in calendar order (e.g. Cognizant R2026010 played before Arnold Palmer R2026009).
        if tournament_id and "tournament_id" in lb.columns:
            lb = lb[lb["tournament_id"] != tournament_id]
    else:
        lb = pd.DataFrame()

    # ── 2. Defending champion ─────────────────────────────────────────────────
    venue_clean = normalize_venue_name(tournament_name)
    prior_wins = master_df[
        (master_df["venue_clean"] == venue_clean) &
        (master_df["position_num"] == 1)
    ]
    # Fuzzy fallback: "Arnold Palmer Invitational" won't exactly match
    # "Arnold Palmer Invitational presented by Mastercard" in master_df
    if prior_wins.empty:
        search_term = venue_clean.replace("THE ", "").strip()
        prior_wins = master_df[
            master_df["venue_clean"].str.contains(search_term, na=False) &
            (master_df["position_num"] == 1)
        ]
    defending_pid = None
    if not prior_wins.empty:
        last_year_won = prior_wins["year"].max()
        winner_row = prior_wins[prior_wins["year"] == last_year_won].iloc[0]
        defending_pid = str(int(float(winner_row["player_id"])))

    # ── 3. Pre-major flag (same value for all players this week) ─────────────
    # IMPORTANT: PGA R-IDs are NOT in calendar order (e.g. R2026010 plays before
    # R2026009). Use start_date comparison — never tournament_id string comparison.
    pre_major_flag = 0
    schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
    if schedule_path.exists() and tournament_id:
        try:
            sched = pd.read_csv(schedule_path)
            sched["start_date"] = pd.to_datetime(sched["start_date"], errors="coerce")
            cur_row = sched[sched["tournament_id"] == tournament_id]
            if not cur_row.empty:
                cur_date = cur_row.iloc[0]["start_date"]
                future = sched[sched["start_date"] > cur_date].sort_values("start_date")
                if not future.empty:
                    next_type = str(future.iloc[0].get("tournament_type", "")).strip().title()
                    pre_major_flag = 1 if next_type == "Major" else 0
        except Exception:
            pass

    # ── 4. Per-player situational features ───────────────────────────────────
    sit_rows = []
    for _, row in features_df.iterrows():
        try:
            pid = str(int(float(row["player_id"])))
        except Exception:
            pid = str(row["player_id"])

        is_defending = 1 if (defending_pid and pid == defending_pid) else 0

        if not lb.empty and "player_id" in lb.columns:
            player_lb = lb[lb["player_id"] == pid]
            if "tournament_id" in player_lb.columns:
                player_lb = player_lb.sort_values("tournament_id")
            n_starts = len(player_lb)
        else:
            player_lb = pd.DataFrame()
            n_starts = 0

        first_start = 1 if n_starts == 0 else 0

        if n_starts > 0:
            positions = player_lb["pos_num"].tolist()
            last_pos = positions[-1]
            post_top5 = 1 if last_pos <= 5 else 0
            missed_cut = 1 if last_pos >= 100 else 0
            # Count consecutive top-10s from the most recent start backwards
            streak = 0
            for pos in reversed(positions):
                if pos <= 10:
                    streak += 1
                else:
                    break
        else:
            last_pos = 40.0  # neutral default
            post_top5 = 0
            missed_cut = 0
            streak = 0

        sit_rows.append({
            "player_id": row["player_id"],
            "is_defending_champion": is_defending,
            "first_start_of_season": first_start,
            "last_start_position": last_pos,
            "post_top5_last_start": post_top5,
            "missed_cut_last_start": missed_cut,
            "consecutive_top10s": streak,
            "pre_major_flag": pre_major_flag,
        })

    sit_df = pd.DataFrame(sit_rows)
    if not sit_df.empty:
        features_df["player_id"] = features_df["player_id"].astype(str)
        sit_df["player_id"] = sit_df["player_id"].astype(str)
        # Drop any columns from features_df that sit_df would also add (avoids _x/_y split)
        overlap = [c for c in sit_df.columns if c in features_df.columns and c != "player_id"]
        if overlap:
            features_df = features_df.drop(columns=overlap)
        features_df = features_df.merge(sit_df, on="player_id", how="left")

    # Ensure all situational columns exist with safe defaults (guards against merge edge cases)
    _sit_defaults = {
        "is_defending_champion": 0,
        "first_start_of_season": 0,
        "post_top5_last_start": 0,
        "missed_cut_last_start": 0,
        "consecutive_top10s": 0,
        "pre_major_flag": pre_major_flag,
        "last_start_position": 40.0,
    }
    for col, default in _sit_defaults.items():
        if col not in features_df.columns:
            features_df[col] = default
        else:
            features_df[col] = features_df[col].fillna(default)
    for col in ["is_defending_champion", "first_start_of_season", "post_top5_last_start",
                "missed_cut_last_start", "consecutive_top10s", "pre_major_flag"]:
        features_df[col] = features_df[col].astype(int)

    n_defending = int(features_df["is_defending_champion"].sum())
    n_first = int(features_df["first_start_of_season"].sum())
    n_top5 = int(features_df["post_top5_last_start"].sum())
    n_streak = int((features_df["consecutive_top10s"] > 0).sum())
    print(f"    Situational: defending={n_defending}, first_start={n_first}, "
          f"post_top5={n_top5}, hot_streak>0={n_streak}, pre_major={pre_major_flag}")

    return features_df


### Step 5: Get Venue Difficulty Stats


def get_venue_stats(venue_clean, master_df):
    """
    Get venue difficulty statistics

    Args:
        venue_clean: Normalized venue name
        master_df: Master training data

    Returns:
        Dict with venue_avg_finish, venue_finish_std
        
    """
    
    venue_data = master_df[master_df['venue_clean'] == venue_clean]
    
    if len(venue_data) == 0:
        # No venue data - return NaN
        return {
            'venue_avg_finish': np.nan, 
            'venue_finish_std': np.nan
        }
    
    return {
        'venue_avg_finish': venue_data['venue_avg_finish'].iloc[0],  # Fixed typo
        'venue_finish_std': venue_data['venue_finish_std'].iloc[0]   # Fixed typo
    }
    
### Step 6: Build Feature Matrix

def build_feature_matrix(field_df, tournament_name, master_df, stats_current, sg_method='last_5', stats_prior=None, tournament_id=None):
    """
    Build feature matrix for all players in the field

    Args:
        field_df: DataFrame with player_id, player_name
        tournament_name: Tournament name (e.g., "The Masters")
        master_df: Master training data
        stats_current: Current year SG stats
        sg_method: Method for calculating recent SG stats ('season_avg', 'last_5', or 'weighted')
        stats_prior: Prior year SG stats (for early-season blending)

    Returns:
        DataFrame with features per player
    """

    print(f"\n  Building features for {len(field_df)} players...")
    print(f"  Using SG method: {sg_method}")
    
    if tournament_id:
        stats_current = stats_current[stats_current['tournament_id'] < tournament_id].copy()
    
    # Check if we're blending with prior year
    blend_with_prior = stats_prior is not None and not stats_prior.empty
    if blend_with_prior:
        month = datetime.now().month
        print(f"  Blending with prior year stats (month: {month})")

    venue_clean = normalize_venue_name(tournament_name)
    venue_stats = get_venue_stats(venue_clean, master_df)

    print(f"  Venue: {venue_clean}")

    features_list = []

    for idx, player in field_df.iterrows():
        if idx % 20 == 0 and idx > 0:
            print(f"    Progress: {idx}/{len(field_df)}")

        player_id = player['player_id']
        player_name = player['player_name']

        sg_stats = get_recent_sg_stats(
            player_id,
            stats_current,
            method=sg_method,
            prior_stats_df=stats_prior,
            blend_with_prior=blend_with_prior
        )
        course_history = get_course_history(player_id, venue_clean, master_df)
        winner_boost = get_tournament_winner_boost(player_id, venue_clean, master_df)
        # Combine all features
        player_features = {
            'player_id': player_id,
            'player_name': player_name,
            **sg_stats,
            **course_history,
            **venue_stats,
            **winner_boost  # Add winner boost feature
        }

        features_list.append(player_features)

    features_df = pd.DataFrame(features_list)

    # ADD WORLD RANKINGS (before field strength calculation)
    rankings_df = get_current_world_rankings()
    if len(rankings_df) > 0:
        features_df = features_df.merge(rankings_df, on='player_id', how='left')
        features_df['world_rank'] = features_df['world_rank'].fillna(500)
        print(f"  Added world rankings ({features_df['world_rank'].notna().sum()} players)")
    else:
        features_df['world_rank'] = 500

    # SG-ADJUSTED WORLD RANK: rescue LIV/injury players whose OWGR doesn't reflect ability
    # For players where world_rank >> SG-implied rank, use the better of the two.
    # Applied consistently here (inference) and in merge_all_historical_data.py (training).
    if 'predictive_sg_weighted' in features_df.columns:
        sg_vals = features_df['predictive_sg_weighted'].fillna(0)
        # Rank within field by SG (1=best). Scale to world-rank units:
        # field rank 1 → ~30 (top-30 world), field rank N → ~(N * field_size_scale)
        n_players = len(features_df)
        field_size_scale = 4.0   # rank-1-in-field ≈ world rank 4
        sg_implied = sg_vals.rank(ascending=False) * field_size_scale
        # Only adjust when OWGR is likely stale (rank > 150) AND SG suggests better ability
        mask = (features_df['world_rank'] > 150) & (sg_implied < features_df['world_rank'])
        n_adj = mask.sum()
        if n_adj > 0:
            features_df.loc[mask, 'world_rank'] = sg_implied[mask].round(0)
            print(f"  SG-adjusted world_rank for {n_adj} players (LIV/injury/stale OWGR)")

    # Log-transform world rank to match training feature
    features_df['world_rank_log'] = np.log1p(features_df['world_rank'])

    # ADD FIELD STRENGTH (avg/median world rank of tournament field)
    field_avg_rank = features_df['world_rank'].mean()
    field_median_rank = features_df['world_rank'].median()
    features_df['field_avg_rank'] = field_avg_rank
    features_df['field_median_rank'] = field_median_rank
    print(f"  Field strength: avg={field_avg_rank:.1f}, median={field_median_rank:.1f}")

    # ADD FIELD-AVERAGE SG FEATURES (vs-field deltas + percentile ranks)
    sg_field_cols = ['season_sg_ott', 'season_sg_app', 'season_sg_arg',
                     'season_sg_putt', 'season_sg_total', 'predictive_sg_weighted']
    for col in sg_field_cols:
        if col in features_df.columns:
            col_mean = features_df[col].mean()
            features_df[f'{col}_vs_field'] = features_df[col] - col_mean
            features_df[f'field_avg_{col}'] = col_mean
    for col in ['season_sg_ott', 'season_sg_app', 'season_sg_arg', 'season_sg_putt']:
        if col in features_df.columns:
            features_df[f'{col}_field_pct'] = features_df[col].rank(pct=True)
            features_df[f'{col}_field_rank'] = features_df[col].rank(ascending=False, na_option='bottom').fillna(0).astype(int)
    print(f"  SG vs-field features added")

    # ADD NON-SG TOUR STAT FIELD RANKS (driving dist, GIR, scrambling etc.)
    NON_SG_STATS = {
        '101': ('driving_dist',      False),   # False = higher is better
        '102': ('driving_acc',       False),
        '103': ('gir_pct',           False),
        '119': ('one_putt_pct',      False),
        '130': ('scrambling',        False),
        '104': ('putts_per_round',   True),    # True = lower is better
        '111': ('sand_save',         False),
        '352': ('bogey_avoid',       False),
        '156': ('birdie_avg',        False),
        '299': ('par3_scoring',      True),
        '142': ('par4_scoring',      True),
        '143': ('par5_scoring',      True)
    }
    try:
        fs_year = _latest_year_for("form_stats_")
        if fs_year:
            fs_path = HISTORICAL_DIR / f'form_stats_{fs_year}.csv'
            if fs_path.exists():
                fs = pd.read_csv(fs_path)
                fs['player_id'] = fs['player_id'].astype(str)
                fs['stat_id'] = fs['stat_id'].astype(str)
                # Get most recent value per player per stat (last tournament entry)
                fs_latest = (
                    fs.sort_values('tournament_id')
                    .groupby(['player_id', 'stat_id'])
                    .tail(1)
                )
                stat_pivot = fs_latest.pivot_table(
                    index='player_id', columns='stat_id',
                    values='stat_value_numeric', aggfunc='first'
                ).reset_index()
                stat_pivot.columns.name = None
                features_df['player_id'] = features_df['player_id'].astype(str)
                features_df = features_df.merge(stat_pivot, on='player_id', how='left')
                for stat_id, (col_name, lower_is_better) in NON_SG_STATS.items():
                    if stat_id in features_df.columns:
                        features_df = features_df.rename(columns={stat_id: f'{col_name}_val'})
                        val_col = f'{col_name}_val'
                        field_avg = features_df[val_col].mean()
                        features_df[f'{col_name}_field_avg'] = field_avg
                        features_df[f'{col_name}_field_rank'] = features_df[val_col].rank(
                            ascending=lower_is_better, na_option='bottom').fillna(0).astype(int)
                        features_df[f'{col_name}_field_pct'] = features_df[val_col].rank(
                            ascending=not lower_is_better, pct=True)
                # Drop any remaining unmapped stat_id columns from the pivot
                # (numeric string names like '102', '108', etc. that weren't in NON_SG_STATS)
                unmapped = [c for c in features_df.columns if str(c).isdigit()]
                if unmapped:
                    features_df = features_df.drop(columns=unmapped)
                    print(f"  Dropped {len(unmapped)} unmapped stat_id columns: {unmapped}")
                print(f"  Non-SG tour stat field ranks added from form_stats_{fs_year}.csv")
    except Exception as e:
        print(f"  Non-SG stat ranks skipped: {e}")

    # ADD ROUND-SPECIFIC SCORING (R1/R2/R3/R4 averages + closing ability)
    try:
        import glob as _glob
        _lb_files = sorted(_glob.glob(str(HISTORICAL_DIR / 'leaderboards_20*.csv')))[-4:]
        if _lb_files:
            _lb_all = []
            for _f in _lb_files:
                _df = pd.read_csv(_f)
                for _rc in ['r1_to_par', 'r2_to_par', 'r3_to_par', 'r4_to_par']:
                    _df[_rc] = pd.to_numeric(_df[_rc], errors='coerce')
                _lb_all.append(_df[['player_id', 'tournament_id',
                                     'r1_to_par', 'r2_to_par', 'r3_to_par', 'r4_to_par']])
            _lb_df = pd.concat(_lb_all, ignore_index=True)
            _lb_df['player_id'] = _lb_df['player_id'].astype(str)
            if tournament_id:
                _lb_df = _lb_df[_lb_df['tournament_id'] < tournament_id]

            _weekend_rows = []
            for _pid, _grp in _lb_df.groupby('player_id'):
                _grp = _grp.sort_values('tournament_id').tail(20)
                _r1 = _grp['r1_to_par'].dropna()
                _r2 = _grp['r2_to_par'].dropna()
                _r3 = _grp['r3_to_par'].dropna()
                _r4 = _grp['r4_to_par'].dropna()
                _r1a = float(_r1.mean()) if len(_r1) >= 3 else np.nan
                _r2a = float(_r2.mean()) if len(_r2) >= 3 else np.nan
                _r3a = float(_r3.mean()) if len(_r3) >= 3 else np.nan
                _r4a = float(_r4.mean()) if len(_r4) >= 3 else np.nan
                _delta = float((_r3.mean() + _r4.mean()) / 2 - (_r1.mean() + _r2.mean()) / 2) \
                    if all(len(x) >= 3 for x in [_r1, _r2, _r3, _r4]) else np.nan
                _weekend_rows.append({
                    'player_id': _pid,
                    'recent_r1_avg': _r1a, 'recent_r2_avg': _r2a,
                    'recent_r3_avg': _r3a, 'recent_r4_avg': _r4a,
                    'closing_delta': _delta,
                })
            _wdf = pd.DataFrame(_weekend_rows)
            features_df['player_id'] = features_df['player_id'].astype(str)
            features_df = features_df.merge(_wdf, on='player_id', how='left')
            for _col in ['recent_r1_avg', 'recent_r2_avg', 'recent_r3_avg', 'recent_r4_avg', 'closing_delta']:
                if _col in features_df.columns:
                    # lower = better (negative to-par = good), rank descending → lowest gets pct 1.0
                    features_df[f'{_col}_field_pct'] = features_df[_col].rank(ascending=False, pct=True)
                    features_df[f'{_col}_vs_field'] = features_df[_col] - features_df[_col].mean()
            _n = int(_wdf['recent_r3_avg'].notna().sum())
            print(f"  Round scoring features added ({_n} players with R3/R4 history)")
    except Exception as e:
        print(f"  Round scoring features skipped: {e}")

    # ADD FORM FEATURES (recent performance indicators)
    try:
        # Load latest available form stats
        # tournament_stats has SG data (form_trend); form_stats has scoring/birdie/GIR stats
        # We need both: concat them so get_form_features_for_field can find all stat IDs
        form_year = _latest_year_for("tournament_stats_")
        form_stats = stats_current.copy()  # Start with tournament_stats (SG data)
        if form_year:
            print(f"  Using tournament_stats_{form_year}.csv for recent form (has SG data)")
        # Supplement with form_stats (scoring_avg, birdie_avg, GIR, etc.)
        _fs_year = _latest_year_for("form_stats_") or form_year
        if _fs_year:
            _fs_path = HISTORICAL_DIR / f"form_stats_{_fs_year}.csv"
            if _fs_path.exists():
                _fs_extra = pd.read_csv(_fs_path)
                # Apply same tournament_id cutoff as tournament_stats if needed
                if tournament_id and 'tournament_id' in _fs_extra.columns:
                    _fs_extra = _fs_extra[_fs_extra['tournament_id'] < tournament_id].copy()
                form_stats = pd.concat([form_stats, _fs_extra], ignore_index=True)
                print(f"  + form_stats_{_fs_year}.csv merged ({len(_fs_extra)} rows, adds scoring/birdie/GIR stats)")

        # Load latest available leaderboards
        lb_year = _latest_year_for("leaderboards_") or form_year
        leaderboards = pd.DataFrame()
        if lb_year:
            lb_path = HISTORICAL_DIR / f"leaderboards_{lb_year}.csv"
            if lb_path.exists():
                leaderboards = pd.read_csv(lb_path)
                print(f"  Using leaderboards_{lb_year}.csv for recent form ({len(leaderboards)} rows)")

        if leaderboards.empty:
            raise ValueError("No leaderboard data available for recent form")

        if tournament_id and 'tournament_id' in form_stats.columns and 'tournament_id' in leaderboards.columns:
            def _id_to_int(series):
                # keep only valid PGA ids like R2026002 -> 2026002
                s = series.astype(str)
                s = s[s.str.match(r'^R\\d{7}$', na=False)]
                return s.str.replace('R', '', regex=False).astype(int)

            try:
                tid_int = int(str(tournament_id).replace('R', ''))
                form_ids = _id_to_int(form_stats['tournament_id'])
                lb_ids = _id_to_int(leaderboards['tournament_id'])
                future_form = (form_ids >= tid_int).sum()
                future_lb = (lb_ids >= tid_int).sum()
                if future_form or future_lb:
                    print(f"  ⚠️ recent_form leakage check: form_stats >= tournament_id: {future_form}, leaderboards >= tournament_id: {future_lb}")
            except Exception:
                pass


        features_df = get_form_features_for_field(
            features_df, form_stats, leaderboards
        )
    except Exception as e:
        print(f"  Form features not available: {e}")
        # Add placeholder form columns with neutral defaults
        form_defaults = {
            'form_trend': 0.0,
            'finish_consistency': 0.5,
            'recent_top10s': 0.0,
            'recent_top5s': 0,
            'recent_cuts_pct': 0.5,
            'recent_birdie_avg': 4.0,
            'recent_bogey_avg': 3.5,
            'recent_scoring_avg': 71.0,
            'recent_gir_pct': 65.0,
            'recent_scrambling': 58.0,
            'recent_bounce_back': 20.0,
            'recent_final_round': 71.0,
            'recent_sand_save': 50.0,
        }
        for col, default in form_defaults.items():
            features_df[col] = default

    # ADD DPWT FORM DATA FOR PLAYERS WITHOUT PGA TOUR FORM
    # Players like Rory McIlroy, Tommy Fleetwood who started season in Europe
    try:
        dpwt_form_path = HISTORICAL_DIR / "dpwt_form_2026.csv"
        if dpwt_form_path.exists():
            dpwt_form = pd.read_csv(dpwt_form_path)
            dpwt_form['player_id'] = pd.to_numeric(dpwt_form['pga_player_id'], errors='coerce').astype('Int64')

            # Map DPWT columns to prediction form columns
            dpwt_mapping = {
                'dpwt_form_score': 'form_trend',  # Use form_score as trend proxy (scaled)
                'dpwt_recent_top10s': 'recent_top10s',
                'dpwt_recent_top5s': 'recent_top5s',
                'dpwt_cuts_pct': 'recent_cuts_pct',
                'dpwt_estimated_sg_total': 'dpwt_sg_total',  # Add as new feature
            }

            # For players with missing/zero form data, fill from DPWT
            filled_count = 0
            for idx, row in features_df.iterrows():
                pid = row['player_id']
                # Check if player has weak form data (trend near 0 or missing top10s)
                has_weak_form = (
                    pd.isna(row.get('form_trend')) or
                    abs(row.get('form_trend', 0)) < 0.01 or
                    (row.get('recent_top10s', 0) == 0 and row.get('recent_cuts_pct', 0) < 0.1)
                )

                if has_weak_form and pid in dpwt_form['player_id'].values:
                    dpwt_player = dpwt_form[dpwt_form['player_id'] == pid].iloc[0]

                    # Scale DPWT form_score (0-100) to form_trend scale (-1 to 1)
                    form_score = dpwt_player.get('dpwt_form_score', 50)
                    features_df.at[idx, 'form_trend'] = (form_score - 50) / 50  # 80 -> 0.6, 50 -> 0, 30 -> -0.4

                    # Fill other form columns
                    features_df.at[idx, 'recent_top10s'] = dpwt_player.get('dpwt_recent_top10s', 0)
                    features_df.at[idx, 'recent_top5s'] = dpwt_player.get('dpwt_recent_top5s', 0)
                    features_df.at[idx, 'recent_cuts_pct'] = dpwt_player.get('dpwt_cuts_pct', 0.5)

                    # NOTE: Do NOT set sg_total from estimated_sg here
                    # Actual DPWT SG stats are handled in the next section
                    # This prevents estimated values from blocking actual stats

                    filled_count += 1

            if filled_count > 0:
                print(f"  ✓ Added DPWT form data for {filled_count} players (European Tour results)")
    except Exception as e:
        print(f"  DPWT form data not available: {e}")

    # ADD DPWT STROKES GAINED STATS (more accurate than estimated SG)
    # For players with actual DPWT SG stats, use those instead of estimates
    try:
        dpwt_sg_path = HISTORICAL_DIR / "dpwt_stats_2026_strokes-gained-total.csv"
        if dpwt_sg_path.exists():
            dpwt_sg = pd.read_csv(dpwt_sg_path)

            # DPWT uses different player IDs - need to map via name matching
            # Create name lookup (DPWT uses "Rory MCILROY" format)
            dpwt_sg['name_lower'] = dpwt_sg['player_name'].str.lower().str.replace(' ', '')

            sg_filled = 0
            for idx, row in features_df.iterrows():
                # Skip if player already has good SG data
                if pd.notna(row.get('sg_total')) and abs(row.get('sg_total', 0)) > 0.1:
                    continue

                # Try to match by name
                player_name = str(row.get('player_name', '')).lower().replace(',', '').replace(' ', '')
                # Handle "LastName, FirstName" -> "firstnamelastname"
                if ',' in str(row.get('player_name', '')):
                    parts = str(row.get('player_name', '')).split(',')
                    player_name = (parts[1].strip() + parts[0].strip()).lower().replace(' ', '')

                # Find in DPWT stats
                match = dpwt_sg[dpwt_sg['name_lower'].str.contains(player_name[:6], case=False, na=False)]
                if len(match) > 0:
                    dpwt_sg_val = match.iloc[0]['average']
                    features_df.at[idx, 'sg_total'] = dpwt_sg_val
                    sg_filled += 1

            if sg_filled > 0:
                print(f"  ✓ Added DPWT SG:Total for {sg_filled} players (actual European Tour stats)")

            # Also load component SG stats if available
            sg_components = {
                'sg_ott': 'strokes-gained-off-the-tee',
                'sg_app': 'strokes-gained-approach-the-green',
                'sg_arg': 'strokes-gained-around-the-green',
                'sg_putt': 'strokes-gained-putting',
            }
            for col, filename in sg_components.items():
                comp_path = HISTORICAL_DIR / f"dpwt_stats_2026_{filename}.csv"
                if comp_path.exists() and col in features_df.columns:
                    comp_df = pd.read_csv(comp_path)
                    comp_df['name_lower'] = comp_df['player_name'].str.lower().str.replace(' ', '')
                    for idx, row in features_df.iterrows():
                        if pd.notna(row.get(col)) and abs(row.get(col, 0)) > 0.1:
                            continue
                        player_name = str(row.get('player_name', '')).lower().replace(',', '').replace(' ', '')
                        if ',' in str(row.get('player_name', '')):
                            parts = str(row.get('player_name', '')).split(',')
                            player_name = (parts[1].strip() + parts[0].strip()).lower().replace(' ', '')
                        match = comp_df[comp_df['name_lower'].str.contains(player_name[:6], case=False, na=False)]
                        if len(match) > 0:
                            features_df.at[idx, col] = match.iloc[0]['average']
    except Exception as e:
        print(f"  DPWT SG stats not available: {e}")

    # FALLBACK 1: PGA 2025 STATS (primary fallback for players with no 2026 data)
    # Players who only missed cuts in 2026 have no SG stats - use their 2025 PGA season stats
    # This runs BEFORE DPWT fallback because PGA stats are preferred
    try:
        stats_2025_path = HISTORICAL_DIR / "tournament_stats_2025.csv"
        if stats_2025_path.exists():
            stats_2025 = pd.read_csv(stats_2025_path)
            stats_2025_avg = stats_2025[stats_2025['stat_component'] == 'Avg'].copy()

            # Pivot to get player season averages
            if len(stats_2025_avg) > 0:
                # Group by player and stat to get season average
                season_avg = stats_2025_avg.groupby(['player_id', 'stat_id'])['stat_value'].mean().reset_index()

                # Map stat IDs to column names
                stat_id_map = {
                    2567: 'sg_total',
                    2568: 'sg_ott',
                    2569: 'sg_app',
                    2564: 'sg_putt',
                    2674: 'sg_t2g'
                }

                fallback_count = 0
                for idx, row in features_df.iterrows():
                    pid = row['player_id']

                    # Check if player has weak/missing SG data (same threshold as DPWT)
                    has_weak_sg = (
                        pd.isna(row.get('sg_total')) or
                        abs(row.get('sg_total', 0)) < 0.1
                    )

                    if has_weak_sg:
                        player_2025 = season_avg[season_avg['player_id'] == pid]
                        if len(player_2025) > 0:
                            filled_any = False
                            for stat_id, col_name in stat_id_map.items():
                                if col_name in features_df.columns:
                                    stat_row = player_2025[player_2025['stat_id'] == stat_id]
                                    if len(stat_row) > 0:
                                        current_val = features_df.at[idx, col_name]
                                        if pd.isna(current_val) or abs(current_val) < 0.1:
                                            features_df.at[idx, col_name] = stat_row.iloc[0]['stat_value']
                                            filled_any = True
                            if filled_any:
                                fallback_count += 1

                if fallback_count > 0:
                    print(f"  ✓ Used 2025 PGA stats for {fallback_count} players (primary fallback)")
    except Exception as e:
        print(f"  2025 PGA fallback stats not available: {e}")

    # FALLBACK 2: DPWT 2025 STATS (secondary fallback - only if no PGA data available)
    # For players still missing SG data after PGA fallback, try 2025 DPWT season stats
    try:
        dpwt_2025_path = HISTORICAL_DIR / "dpwt_stats_2025_strokes-gained-total.csv"
        if dpwt_2025_path.exists():
            dpwt_2025 = pd.read_csv(dpwt_2025_path)
            dpwt_2025['name_lower'] = dpwt_2025['player_name'].str.lower().str.replace(' ', '')

            dpwt_2025_filled = 0
            for idx, row in features_df.iterrows():
                # Skip if player already has good SG data (from PGA 2026, PGA 2025, or DPWT 2026)
                if pd.notna(row.get('sg_total')) and abs(row.get('sg_total', 0)) > 0.1:
                    continue

                # Try to match by name
                player_name = str(row.get('player_name', '')).lower().replace(',', '').replace(' ', '')
                if ',' in str(row.get('player_name', '')):
                    parts = str(row.get('player_name', '')).split(',')
                    player_name = (parts[1].strip() + parts[0].strip()).lower().replace(' ', '')

                match = dpwt_2025[dpwt_2025['name_lower'].str.contains(player_name[:6], case=False, na=False)]
                if len(match) > 0:
                    features_df.at[idx, 'sg_total'] = match.iloc[0]['average']
                    dpwt_2025_filled += 1

            if dpwt_2025_filled > 0:
                print(f"  ✓ Added 2025 DPWT SG:Total for {dpwt_2025_filled} players (secondary fallback)")

            # Also load 2025 DPWT component stats
            sg_components = {
                'sg_ott': 'strokes-gained-off-the-tee',
                'sg_app': 'strokes-gained-approach-the-green',
                'sg_arg': 'strokes-gained-around-the-green',
                'sg_putt': 'strokes-gained-putting',
            }
            for col, filename in sg_components.items():
                comp_path = HISTORICAL_DIR / f"dpwt_stats_2025_{filename}.csv"
                if comp_path.exists() and col in features_df.columns:
                    comp_df = pd.read_csv(comp_path)
                    comp_df['name_lower'] = comp_df['player_name'].str.lower().str.replace(' ', '')
                    for idx, row in features_df.iterrows():
                        if pd.notna(row.get(col)) and abs(row.get(col, 0)) > 0.1:
                            continue
                        player_name = str(row.get('player_name', '')).lower().replace(',', '').replace(' ', '')
                        if ',' in str(row.get('player_name', '')):
                            parts = str(row.get('player_name', '')).split(',')
                            player_name = (parts[1].strip() + parts[0].strip()).lower().replace(' ', '')
                        match = comp_df[comp_df['name_lower'].str.contains(player_name[:6], case=False, na=False)]
                        if len(match) > 0:
                            features_df.at[idx, col] = match.iloc[0]['average']
    except Exception as e:
        print(f"  2025 DPWT stats not available: {e}")

    # BLEND CURRENT SG WITH PGA 2025 BASELINE FOR ALL PLAYERS
    # This gives a more complete picture by incorporating proven PGA Tour track record
    # Especially important for dual-tour players (Rory, Fleetwood, etc.) whose
    # current DPWT form should be weighted with their PGA Tour baseline
    try:
        stats_2025_path = HISTORICAL_DIR / "tournament_stats_2025.csv"
        if stats_2025_path.exists():
            stats_2025 = pd.read_csv(stats_2025_path)
            stats_2025_avg = stats_2025[stats_2025['stat_component'] == 'Avg'].copy()

            if len(stats_2025_avg) > 0:
                # Get PGA 2025 season averages per player
                pga_2025_avg = stats_2025_avg.groupby(['player_id', 'stat_id'])['stat_value'].mean().reset_index()

                # Map stat IDs to both form columns (sg_*) and season columns (season_sg_*)
                # The model uses season_sg_* for predictions, so we need to blend both
                stat_id_map = {
                    2567: ('sg_total', 'season_sg_total'),
                    2568: ('sg_ott', 'season_sg_ott'),
                    2569: ('sg_app', 'season_sg_app'),
                    2564: ('sg_putt', 'season_sg_putt'),
                    2674: ('sg_t2g', 'season_sg_t2g')
                }

                # Blend weights: 65% current form, 35% PGA 2025 baseline
                # This balances recent form with proven track record
                current_weight = 0.65
                baseline_weight = 0.35

                blended_count = 0
                for idx, row in features_df.iterrows():
                    pid = row['player_id']
                    player_2025 = pga_2025_avg[pga_2025_avg['player_id'] == pid]

                    if len(player_2025) == 0:
                        continue  # No PGA 2025 data for this player

                    blended_any = False
                    for stat_id, (form_col, season_col) in stat_id_map.items():
                        stat_row = player_2025[player_2025['stat_id'] == stat_id]
                        if len(stat_row) == 0:
                            continue  # No 2025 data for this stat

                        baseline_val = stat_row.iloc[0]['stat_value']

                        # Blend both form column (sg_*) and season column (season_sg_*)
                        for col_name in [form_col, season_col]:
                            if col_name not in features_df.columns:
                                continue

                            current_val = features_df.at[idx, col_name]

                            # Only blend if we have valid current data
                            if pd.notna(current_val) and abs(current_val) > 0.01:
                                # Blend current form with PGA 2025 baseline
                                blended_val = (current_val * current_weight) + (baseline_val * baseline_weight)
                                features_df.at[idx, col_name] = blended_val
                                blended_any = True
                            elif pd.isna(current_val) or abs(current_val) < 0.01:
                                # No current data - use PGA 2025 baseline directly
                                features_df.at[idx, col_name] = baseline_val
                                blended_any = True

                    if blended_any:
                        blended_count += 1

                if blended_count > 0:
                    print(f"  ✓ Blended SG with PGA 2025 baseline for {blended_count} players (65% current / 35% baseline)")
    except Exception as e:
        print(f"  PGA 2025 baseline blending not available: {e}")

    # REFRESH SG FIELD-CONTEXT FEATURES AFTER SG FALLBACK/BLENDING
    # SG columns can be modified above (PGA/DPWT fallback + baseline blend), so
    # recompute field_avg_* and *_vs_field from final values.
    sg_field_cols = ['season_sg_ott', 'season_sg_app', 'season_sg_arg',
                     'season_sg_putt', 'season_sg_total', 'predictive_sg_weighted']
    for col in sg_field_cols:
        if col in features_df.columns:
            col_mean = features_df[col].mean()
            features_df[f'{col}_vs_field'] = features_df[col] - col_mean
            features_df[f'field_avg_{col}'] = col_mean
    for col in ['season_sg_ott', 'season_sg_app', 'season_sg_arg', 'season_sg_putt']:
        if col in features_df.columns:
            features_df[f'{col}_field_pct'] = features_df[col].rank(pct=True)
            features_df[f'{col}_field_rank'] = features_df[col].rank(
                ascending=False, na_option='bottom'
            ).fillna(0).astype(int)
    print("  SG vs-field features refreshed after SG blending")

    # ADD DATA GOLF COURSE FIT FEATURES
    # Uses season_sg_* (prior performance) × course importance weights
    print("  Adding Data Golf course fit features...")
    features_df = add_course_fit_features(features_df, tournament_name)

    # Refresh predictive_sg_weighted vs-field after course fit (which sets the column)
    if 'predictive_sg_weighted' in features_df.columns:
        _psw_mean = features_df['predictive_sg_weighted'].mean()
        features_df['field_avg_predictive_sg_weighted'] = _psw_mean
        features_df['predictive_sg_weighted_vs_field'] = features_df['predictive_sg_weighted'] - _psw_mean

    # ADD COURSE-SPECIFIC PLAYER PERFORMANCE FEATURES
    # Uses historical form stats to get per-player course performance
    print("  Adding player course performance features...")
    features_df = add_course_performance_features(features_df, tournament_name)

    # ADD SITUATIONAL / NARRATIVE FEATURES
    # Defending champion, first start of season, momentum, pre-major flag
    print("  Adding situational features...")
    features_df = add_situational_features(
        features_df, tournament_name, master_df, tournament_id=tournament_id
    )

    # LIV players: active on LIV Tour, only appear in PGA Tour data via majors.
    # Their form_stats event count (0-2 PGA Tour starts) vastly understates their
    # actual competitive activity. Bypass the SG regression penalty for them.
    # Update this list as players return to PGA Tour (e.g. Koepka returned in 2026).
    _LIV_PLAYER_NAMES = {
        "DeChambeau, Bryson", "Johnson, Dustin", "Rahm, Jon",
        "Garcia, Sergio", "Reed, Patrick", "Westwood, Lee",
        "Gooch, Talor", "Niemann, Joaquin", "Hatton, Tyrrell",
        "Smith, Cameron", "Wolff, Matthew", "Ancer, Abraham",
        "Scott, Adam", "Na, Kevin",
    }

    # SG EVENT COUNT PENALTY: Regression-to-mean for players with < 10 events
    # Prevents hot-but-shallow SG stats from over-ranking low-sample players
    try:
        _ec_year = _latest_year_for("form_stats_")
        if _ec_year:
            _ec_path = HISTORICAL_DIR / f"form_stats_{_ec_year}.csv"
            if _ec_path.exists():
                _ec_fs = pd.read_csv(_ec_path, usecols=['player_id', 'tournament_id'])
                _ec_fs['player_id'] = _ec_fs['player_id'].astype(str)
                if tournament_id:
                    _ec_fs = _ec_fs[_ec_fs['tournament_id'] < tournament_id]
                _event_counts = (
                    _ec_fs.groupby('player_id')['tournament_id']
                    .nunique()
                    .reset_index()
                    .rename(columns={'tournament_id': 'sg_event_count'})
                )
                features_df = features_df.merge(_event_counts, on='player_id', how='left')
                # Players with no form_stats entry default to half the field median
                # (better than 5, which was too aggressive early in the season)
                _field_median_events = features_df['sg_event_count'].median()
                features_df['sg_event_count'] = features_df['sg_event_count'].fillna(
                    max(1, _field_median_events * 0.5)
                )

                # Dynamic threshold: target is 1.5x the field median
                # Rationale: players significantly below the typical active player this
                # week get penalized; players at or above the median do not.
                # This adapts automatically to early-season (median=4 → threshold=6)
                # vs mid-season (median=12 → threshold=18) without needing re-tuning.
                _MIN_EVENTS = max(5, _field_median_events * 1.5)

                # Confidence floor of 0.30: even players with very few events retain
                # 30% weight on their actual stats (the model already has career context
                # from training; we don't want to fully erase this week's stats).
                _CONF_FLOOR = 0.30
                _conf = (_CONF_FLOOR + (1 - _CONF_FLOOR) * (features_df['sg_event_count'] / _MIN_EVENTS)).clip(_CONF_FLOOR, 1)

                # LIV players get confidence=1.0 — their 0-2 PGA Tour starts this
                # season don't reflect their true form (they're competing on LIV
                # full-time; we only see them in majors). Don't regress their stats.
                _liv_mask = features_df['player_name'].isin(_LIV_PLAYER_NAMES)
                _conf = _conf.where(~_liv_mask, 1.0)
                _n_liv_exempted = int(_liv_mask.sum())

                _adjusted = []
                for _sg_col in ['season_sg_total', 'season_sg_arg', 'predictive_sg_weighted']:
                    if _sg_col in features_df.columns:
                        _field_avg = features_df[_sg_col].mean()
                        features_df[_sg_col] = _field_avg + _conf * (features_df[_sg_col] - _field_avg)
                        _adjusted.append(_sg_col)
                _low_sample = int((features_df['sg_event_count'] < _MIN_EVENTS).sum())
                print(f"  SG event count penalty: {_low_sample} low-sample players adjusted "
                      f"(threshold={_MIN_EVENTS:.1f}, floor={_CONF_FLOOR:.0%}, field median={_field_median_events:.1f} events)")
                if _n_liv_exempted:
                    print(f"    LIV exemptions: {_n_liv_exempted} players bypassed penalty (major-only PGA Tour data)")
    except Exception as _ec_e:
        print(f"  SG event count penalty skipped: {_ec_e}")

    # ADD DG APPROACH SKILL (shot-count-weighted SG/shot across distance×lie segments)
    # Loaded from data/datagolf/dg_approach_skill_latest.csv, joined by normalized name.
    # Carries forward as informational columns in predictions (not yet a trained model feature;
    # will be included in next retrain).
    try:
        _as_path = DATA_DIR / "datagolf" / "dg_approach_skill_latest.csv"
        if _as_path.exists():
            import re as _re
            _as_df = pd.read_csv(_as_path, usecols=["player_name", "approach_skill_sg", "approach_skill_proximity", "approach_skill_shot_total"])

            def _as_norm(n):
                import unicodedata as _ud
                s = str(n).strip().lower()
                # manual replacements for chars NFKD doesn't transliterate (ø, æ)
                for _from, _to in [("ø","o"),("Ø","o"),("æ","ae"),("Æ","ae")]:
                    s = s.replace(_from.lower(), _to)
                # transliterate composed chars (Å→a, ü→u, é→e, etc.)
                s = _ud.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
                if "," in s:
                    parts = s.split(",", 1)
                    s = f"{parts[1].strip()} {parts[0].strip()}"
                s = _re.sub(r"[^a-z0-9\s]", " ", s)
                return " ".join(s.split())

            _as_df["_nk"] = _as_df["player_name"].apply(_as_norm)
            _as_lookup = _as_df.set_index("_nk")[["approach_skill_sg", "approach_skill_proximity", "approach_skill_shot_total"]]

            features_df["_nk"] = features_df["player_name"].apply(_as_norm)
            features_df = features_df.merge(_as_lookup, on="_nk", how="left")
            features_df.drop(columns=["_nk"], inplace=True, errors="ignore")

            # vs-field delta (useful for display + eventually for training)
            _as_field_mean = features_df["approach_skill_sg"].mean()
            features_df["approach_skill_sg_vs_field"] = features_df["approach_skill_sg"] - _as_field_mean

            _matched = features_df["approach_skill_sg"].notna().sum()
            print(f"  DG approach skill merged: {_matched}/{len(features_df)} players matched")
        else:
            print(f"  DG approach skill: {_as_path.name} not found — run fetch_dg_approach_skill.py")
    except Exception as _as_e:
        print(f"  DG approach skill merge skipped: {_as_e}")

    print(f"  ✓ Built feature matrix: {features_df.shape}")
    
    
    # ADD DG SKILL RATINGS
    try:
        _sr_path = DATA_DIR / "datagolf" / "dg_skill_ratings_latest.csv"
        if _sr_path.exists():
            _sr_df = pd.read_csv(_sr_path, usecols=[
              "player_name","dg_skill_total","dg_skill_ott",
              "dg_skill_app","dg_skill_arg","dg_skill_putt",
              "dg_skill_dist","dg_skill_acc",
          ])
            
            _sr_df['_nk'] = _sr_df['player_name'].apply(_as_norm)
            _sr_lookup = _sr_df.set_index("_nk").drop(columns=['player_name'])
            features_df['_nk'] = features_df['player_name'].apply(_as_norm)
            features_df = features_df.merge(_sr_lookup, on="_nk", how="left")
            features_df.drop(columns=["_nk"], inplace=True, errors="ignore")
            for _sc in ["dg_skill_total","dg_skill_app","dg_skill_ott","dg_skill_putt"]:
                if _sc in features_df.columns:
                    features_df[f"{_sc}_vs_field"] = features_df[_sc] - features_df[_sc].mean()
            _m = features_df["dg_skill_total"].notna().sum()
            print(f"  DG skill ratings merged: {_m}/{len(features_df)} players matched")
    except Exception as _sr_e:
        print(f"  DG skill ratings merge skipped: {_sr_e}")

    # ADD DG PLAYER DECOMPOSITIONS (event-specific — updates each week)
    # final_pred = DG's full course-adjusted SG prediction for this event
    # course_fit_delta = final_pred - baseline_pred (how course helps/hurts this player)
    # Saves as pass-through columns; activate in SCORE_FEATURES after retrain.
    try:
        _dc_path = DATA_DIR / "datagolf" / "dg_decompositions_latest.csv"
        if _dc_path.exists():
            _dc_df = pd.read_csv(_dc_path, usecols=[
                "player_name", "baseline_pred", "final_pred", "course_fit_delta",
                "driving_accuracy_adjustment", "driving_distance_adjustment",
                "timing_adjustment", "course_history_adjustment",
                "total_course_history_adjustment", "std_deviation", "sample_size",
            ])
            _dc_df["_nk"] = _dc_df["player_name"].apply(_as_norm)
            _dc_lookup = _dc_df.set_index("_nk").drop(columns=["player_name"])
            features_df["_nk"] = features_df["player_name"].apply(_as_norm)
            features_df = features_df.merge(_dc_lookup, on="_nk", how="left")
            features_df.drop(columns=["_nk"], inplace=True, errors="ignore")
            # vs-field delta for final_pred (useful as a ranked signal)
            _dc_field_mean = features_df["final_pred"].mean()
            features_df["dg_final_pred_vs_field"] = features_df["final_pred"] - _dc_field_mean
            _m = features_df["final_pred"].notna().sum()
            print(f"  DG decompositions merged: {_m}/{len(features_df)} players matched")
        else:
            print(f"  DG decompositions: dg_decompositions_latest.csv not found — run fetch_dg_decompositions.py")
    except Exception as _dc_e:
        print(f"  DG decompositions merge skipped: {_dc_e}")

    # ADD DG PRE-TOURNAMENT PROBABILITIES (dg_win, dg_top10, dg_make_cut for this week)
    # These match trained SCORE_FEATURES — populated here at inference so model sees real values not NaN.
    try:
        _pt_path = DATA_DIR / "datagolf" / "dg_pre_tournament_latest.csv"
        if _pt_path.exists():
            _pt_df = pd.read_csv(_pt_path)
            _pt_df = _pt_df[_pt_df["model"] == "baseline_history_fit"].copy()
            _pt_df = _pt_df[["player_name", "win", "top_10", "make_cut"]].rename(columns={
                "win":       "dg_win",
                "top_10":    "dg_top10",
                "make_cut":  "dg_make_cut",
            })
            _pt_df["_nk"] = _pt_df["player_name"].apply(_as_norm)
            _pt_lookup = _pt_df.set_index("_nk").drop(columns=["player_name"])
            features_df["_nk"] = features_df["player_name"].apply(_as_norm)
            features_df = features_df.merge(_pt_lookup, on="_nk", how="left")
            features_df.drop(columns=["_nk"], inplace=True, errors="ignore")
            _m = features_df["dg_win"].notna().sum()
            print(f"  DG pre-tournament merged: {_m}/{len(features_df)} players (dg_win/top10/make_cut)")
        else:
            print("  DG pre-tournament: not found — run fetch_dg_pre_tournament.py")
    except Exception as _pt_e:
        print(f"  DG pre-tournament merge skipped: {_pt_e}")


    
    try:
        _fit_path = DATA_DIR / "datagolf" / "dg_course_fit_latest.csv"
        if _fit_path.exists():
            _fit_df = pd.read_csv(_fit_path)[["player_name", "course_fit_delta", "course_fit_delta_pct"]]
            _fit_df = _fit_df.rename(columns={
                "course_fit_delta":     "dg_course_fit_delta",
                "course_fit_delta_pct": "dg_course_fit_delta_pct",
            })
            _fit_df["_nk"] = _fit_df["player_name"].apply(_as_norm)
            _fit_lookup = _fit_df.set_index("_nk")[["dg_course_fit_delta", "dg_course_fit_delta_pct"]]
            features_df["_nk"] = features_df["player_name"].apply(_as_norm)
            features_df = features_df.merge(_fit_lookup, on="_nk", how="left")
            features_df.drop(columns=["_nk"], inplace=True, errors="ignore")
            _m_fit = features_df["dg_course_fit_delta"].notna().sum()
            print(f"  DG course fit merged: {_m_fit}/{len(features_df)} players (dg_course_fit_delta)")                  
        else:                                             
            print("  DG course fit: not found — run fetch_dg_pre_tournament.py")                                      
    except Exception as _fit_e:                                                                                       
        print(f"  DG course fit merge skipped: {_fit_e}")











    return features_df  






### Step 7: Handle Missing Values (CHALLENGE 3 IMPLEMENTED)

def fill_missing_values(features_df, stats_2025, master_df):
    """
    Fill NaN values with intelligent defaults

    CRITICAL: Model was trained only on complete data,
    so we must fill NaN for predictions

    CHALLENGE 3 ✅: Calculate median SG stats from 2025 data instead of using 0
    """
    print("\n  Filling missing values...")

    # CHALLENGE 3: Calculate median SG stats from actual 2025 data
    stats_avg = stats_2025[stats_2025['stat_component'] == 'Avg'].copy()

    sg_defaults = {
        'sg_total': 0.0,
        'sg_ott': 0.0,
        'sg_app': 0.0,
        'sg_arg': 0.0,
        'sg_putt': 0.0,
        'sg_t2g': 0.0
    }

    if len(stats_avg) > 0:
        # Pivot and calculate median
        stats_pivot = stats_avg.pivot_table(
            index=['player_id', 'tournament_id'],
            columns='stat_id',
            values='stat_value',
            aggfunc='first'
        )

        stat_mapping = {
            2567: 'sg_total',
            2568: 'sg_ott',
            2569: 'sg_app',
            2564: 'sg_putt',
            2674: 'sg_t2g'
        }

        print("    Calculated SG defaults (median from 2025 data):")
        for stat_id, stat_name in stat_mapping.items():
            if stat_id in stats_pivot.columns:
                sg_defaults[stat_name] = stats_pivot[stat_id].median()
                print(f"      {stat_name}: {sg_defaults[stat_name]:.3f}")

        # sg_arg is calculated from sg_t2g - sg_app, default to 0
        print(f"      sg_arg: 0.000 (calculated field)")

    # Fill SG stats with calculated medians (both per-tournament and season)
    for stat_name, default_val in sg_defaults.items():
        # Fill per-tournament SG
        if stat_name in features_df.columns:
            n_missing = features_df[stat_name].isna().sum()
            if n_missing > 0:
                features_df[stat_name] = features_df[stat_name].fillna(default_val)
                print(f"      Filled {n_missing} missing {stat_name} values")

        # Fill season SG with same defaults
        season_stat = f'season_{stat_name}'
        if season_stat in features_df.columns:
            n_missing = features_df[season_stat].isna().sum()
            if n_missing > 0:
                features_df[season_stat] = features_df[season_stat].fillna(default_val)
                print(f"      Filled {n_missing} missing {season_stat} values")

    # Course history: Fill avg_finish with venue avg + penalty for rookies
    # Rationale: Players without course history tend to perform slightly worse than venue avg
    if features_df['hist_avg_finish'].isna().any():
        venue_avg = features_df['venue_avg_finish'].iloc[0]
        rookie_penalty = 5  # Assume rookies finish 5 spots worse than average

        n_missing = features_df['hist_avg_finish'].isna().sum()
        features_df['hist_avg_finish'] = features_df['hist_avg_finish'].fillna(venue_avg + rookie_penalty)
        features_df['hist_best_finish'] = features_df['hist_best_finish'].fillna(venue_avg + rookie_penalty)
        print(f"      Filled {n_missing} missing course history (venue_avg + {rookie_penalty} penalty)")

    # Fill cut rate for players with no history (assume tour average ~85% cut rate)
    if features_df['hist_cut_rate'].isna().any():
        n_missing = features_df['hist_cut_rate'].isna().sum()
        features_df['hist_cut_rate'] = features_df['hist_cut_rate'].fillna(0.85)
        print(f"      Filled {n_missing} missing hist_cut_rate with 0.85 (tour avg)")

    # Venue stats: Fill with median across all venues (if new venue)
    if features_df['venue_avg_finish'].isna().any():
        venue_median = master_df['venue_avg_finish'].median()
        venue_std_median = master_df['venue_finish_std'].median()
        features_df['venue_avg_finish'] = features_df['venue_avg_finish'].fillna(venue_median)
        features_df['venue_finish_std'] = features_df['venue_finish_std'].fillna(venue_std_median)
        print(f"      Filled venue stats with medians ({venue_median:.1f}, {venue_std_median:.1f})")


    if 'world_rank' in features_df.columns and features_df['world_rank'].isna().any():
        n_missing = features_df['world_rank'].isna().sum()
        features_df['world_rank'] = features_df['world_rank'].fillna(300)
        print(f"      Filled {n_missing} missing world_rank with 300 (default)")
   
        
    # Fill form features with neutral defaults
    form_defaults = {
        'form_trend': 0.0,           # No trend = neutral
        'finish_consistency': 0.5,   # Middle of range
        'recent_top10s': 0,          # No recent top 10s
        'recent_top5s': 0,           # No recent top 5s
        'recent_cuts_pct': 0.5,      # 50% cut rate default
        # Scoring efficiency features (use tour averages as defaults)
        'recent_birdie_avg': 4.0,    # ~4 birdies per round is average
        'recent_bogey_avg': 3.5,     # ~3.5 bogeys per round is average
        'recent_scoring_avg': 71.0,  # Par is ~71 average
        'recent_gir_pct': 65.0,      # ~65% GIR is average
        'recent_scrambling': 58.0,   # ~58% scrambling is average
        # Clutch indicators
        'recent_bounce_back': 20.0,  # ~20% bounce back is average
        'recent_final_round': 71.0,  # Similar to scoring avg
        'recent_sand_save': 50.0,    # ~50% sand save is average
    }
    for col, default in form_defaults.items():
        if col in features_df.columns and features_df[col].isna().any():
            n_missing = features_df[col].isna().sum()
            features_df[col] = features_df[col].fillna(default)
            print(f"      Filled {n_missing} missing {col} with {default}")

    # Fill Data Golf course fit features with 0 (neutral fit)
    dg_fit_cols = ['dg_fit_ott', 'dg_fit_app', 'dg_fit_arg', 'dg_fit_putt', 'dg_fit_total']
    for col in dg_fit_cols:
        if col in features_df.columns and features_df[col].isna().any():
            n_missing = features_df[col].isna().sum()
            features_df[col] = features_df[col].fillna(0.0)
            print(f"      Filled {n_missing} missing {col} with 0.0")

    print(f"    ✓ All missing values filled")

    return features_df

# Step 8: Make Predictions

def _apply_score_model(features_df: pd.DataFrame, models: dict) -> pd.DataFrame:
    """Apply score regression + quantile models to add projected score columns.

    Mean model  → projected_score_vs_field  (best for RANKING players)
    Q10 model   → proj_ceiling  (best 10% of weeks — upside scenario)
    Q50 model   → proj_median   (typical week)
    Q90 model   → proj_floor    (worst 10% of weeks — downside scenario)

    All values are vs-field (negative = better than average).
    """
    if 'score' not in models:
        return features_df
    sf: list = models.get('score_features') or SCORE_FEATURES
    sf = [f for f in sf if f in features_df.columns]
    Xs = features_df[sf].apply(pd.to_numeric, errors='coerce').fillna(0).values

    # Mean model — predicts conditional mean, best for ranking
    relative = models['score'].predict(Xs)
    if 'recent_scoring_avg' in features_df.columns:
        field_scoring = pd.to_numeric(features_df['recent_scoring_avg'], errors='coerce')
        field_offset = float(field_scoring.median() - 72)
    else:
        field_offset = 0.0
    features_df['projected_score'] = (relative + field_offset).round(1)
    features_df['projected_score_vs_field'] = relative.round(2)
    features_df['score_rank'] = features_df['projected_score_vs_field'].rank(method='min').astype(int)

    # Quantile models — ceiling/median/floor range
    # These are trained with pinball loss to target specific percentiles,
    # so they give a realistic spread rather than compressed means.
    for _q, _col in (('q10', 'proj_ceiling'), ('q50', 'proj_median'), ('q90', 'proj_floor')):
        if f'score_{_q}' in models:
            features_df[_col] = models[f'score_{_q}'].predict(Xs).round(1)

    return features_df


def make_predictions(features_df: pd.DataFrame, models: dict) -> pd.DataFrame:
    """
    Generate win/top5/top10 probabilities

    Args:
        features_df: DataFrame with features
        models: Dict with trained models

    Returns:
        DataFrame with predictions added
    """
    # Fallback feature set for legacy models that don't expose feature_names_in_
    fallback_feature_cols = [
        'season_sg_putt', 'season_sg_total', 'season_sg_ott', 'season_sg_app', 'season_sg_t2g', 'season_sg_arg',
        'hist_times_played', 'hist_avg_finish', 'hist_best_finish',
        'hist_wins', 'hist_top5s', 'hist_top10s',
        'hist_cut_rate', 'hist_missed_cuts',
        'has_won_here', 'has_course_history', 'has_made_cut_here',
        'venue_avg_finish', 'venue_finish_std',
        'field_avg_rank', 'field_median_rank',
        'world_rank',
        'form_trend', 'finish_consistency', 'recent_top10s', 'recent_top5s', 'recent_cuts_pct',
        'recent_birdie_avg', 'recent_bogey_avg', 'recent_scoring_avg', 'recent_gir_pct', 'recent_scrambling',
        'recent_bounce_back', 'recent_final_round', 'recent_sand_save',
        'dg_fit_ott', 'dg_fit_app', 'dg_fit_arg', 'dg_fit_putt', 'dg_fit_total',
        'course_sg_total_vs_avg', 'course_sg_trend',
    ]

    def _resolve_model_feature_cols(model_obj, fallback_cols):
        if hasattr(model_obj, "feature_names_in_"):
            cols = list(getattr(model_obj, "feature_names_in_"))
            if cols:
                return cols
        if hasattr(model_obj, "calibrated_classifiers_"):
            calibrated = getattr(model_obj, "calibrated_classifiers_", None) or []
            if calibrated:
                est = getattr(calibrated[0], "estimator", None)
                if est is not None and hasattr(est, "feature_names_in_"):
                    cols = list(getattr(est, "feature_names_in_"))
                    if cols:
                        return cols
        return fallback_cols

    def _prepare_matrix(df, cols):
        # Backward/forward compatibility for SG edge column naming.
        if "course_sg_total_vs_avg" in cols and "course_sg_total_vs_avg" not in df.columns and "course_sg_vs_avg" in df.columns:
            df["course_sg_total_vs_avg"] = pd.to_numeric(df["course_sg_vs_avg"], errors="coerce")
        if "course_sg_vs_avg" in cols and "course_sg_vs_avg" not in df.columns and "course_sg_total_vs_avg" in df.columns:
            df["course_sg_vs_avg"] = pd.to_numeric(df["course_sg_total_vs_avg"], errors="coerce")

        missing_cols = [c for c in cols if c not in df.columns]
        for c in missing_cols:
            df[c] = 0.0

        if missing_cols:
            preview = ", ".join(missing_cols[:8])
            suffix = "..." if len(missing_cols) > 8 else ""
            print(f"  Added {len(missing_cols)} missing model features with 0 defaults: {preview}{suffix}")

        x = df[cols].copy()
        x = x.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        return x

    # Predict probabilities
    for model_key, out_col in (("win", "win_prob"), ("top5", "top5_prob"), ("top10", "top10_prob")):
        model_cols = _resolve_model_feature_cols(models[model_key], fallback_feature_cols)
        X = _prepare_matrix(features_df, model_cols)
        features_df[out_col] = models[model_key].predict_proba(X)[:, 1]

    # Score regression model — delegated to top-level helper to avoid Pylance scope issues
    features_df = _apply_score_model(features_df, models)

    return features_df


def _robust_zscore(values: pd.Series) -> pd.Series:
    """Robust z-score with MAD fallback to std."""
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() <= 1:
        return pd.Series(np.zeros(len(numeric)), index=numeric.index, dtype=float)

    median = numeric.median()
    mad = (numeric - median).abs().median()
    std = numeric.std(ddof=0)

    scale = float(mad * 1.4826) if pd.notna(mad) and mad > 1e-8 else float(std)
    if not np.isfinite(scale) or scale < 1e-8:
        scale = 1.0

    return (numeric - median) / scale


def _experience_confidence(starts: pd.Series) -> pd.Series:
    """Map starts count to [0,1] confidence with diminishing returns."""
    starts_num = pd.to_numeric(starts, errors="coerce").fillna(0).clip(lower=0)
    return (np.log1p(starts_num) / np.log(6.0)).clip(0, 1)


def apply_kft_adjustment(
    predictions_df: pd.DataFrame,
    kft_profiles_path: Path = None,
    max_pga_seasons: int = 3,
    max_abs_adjust: float = 0.08,
) -> pd.DataFrame:
    """
    Boost predictions for players whose KFT history suggests higher skill
    than their limited PGA Tour record indicates.

    Logic:
    - Load kft_player_profiles.csv (scoring avg, top10s, kft_sg_proxy)
    - Identify players with < max_pga_seasons PGA Tour seasons in training data
    - For those players, apply a modest upward adjustment proportional to
      kft_sg_proxy, scaled by (1 - pga_experience_factor)
    - Players with strong KFT records get more credit when they have less tour data

    Adjustment is applied to win/top5/top10/top20 probs then renormalized.
    """
    if kft_profiles_path is None:
        kft_profiles_path = DATA_DIR / "historical" / "kft_player_profiles.csv"

    if not Path(kft_profiles_path).exists():
        print("    ⚠  KFT profiles not found — skipping KFT adjustment")
        return predictions_df

    df = predictions_df.copy()

    # Load KFT profiles
    kft = pd.read_csv(kft_profiles_path)
    kft["kft_sg_proxy"] = pd.to_numeric(kft["kft_sg_proxy"], errors="coerce")
    kft["top10s"] = pd.to_numeric(kft["top10s"], errors="coerce").fillna(0)
    kft["kft_year"] = pd.to_numeric(kft["kft_year"], errors="coerce")

    # Normalize KFT names to "first last" lowercase for matching
    def _norm(n):
        parts = str(n).split(",")
        if len(parts) == 2:
            return f"{parts[1].strip()} {parts[0].strip()}".lower()
        return str(n).strip().lower()

    df["_norm"] = df["player_name"].apply(_norm)
    kft["_norm"] = kft["player_name"].apply(lambda n: str(n).strip().lower())

    # Merge KFT data onto predictions
    df = df.merge(
        kft[["_norm", "kft_sg_proxy", "top10s", "kft_year"]].rename(
            columns={"top10s": "kft_top10s"}
        ),
        on="_norm", how="left"
    )
    df = df.drop(columns=["_norm"])

    # Determine PGA Tour experience for each player
    # Use number of times the player appeared in master training data (a proxy for seasons)
    master_path = DATA_DIR / "processed" / "master_training_data_2016_2025.csv"
    pga_seasons = {}
    if master_path.exists():
        master = pd.read_csv(master_path, usecols=["player_name", "year"])
        # Count only FULL member seasons: years where a player played ≥ 10 events.
        # Players on KFT with sponsor exemptions on PGA Tour may appear in 1-3 events
        # per year — those shouldn't count as full PGA Tour seasons.
        events_per_year = master.groupby(["player_name", "year"]).size().reset_index(name="events")
        full_seasons = events_per_year[events_per_year["events"] >= 10]
        for name, count in full_seasons.groupby("player_name").size().items():
            pga_seasons[_norm(name)] = int(count)

    df["pga_seasons"] = df["player_name"].apply(
        lambda n: pga_seasons.get(_norm(n), 0) if pga_seasons else 0
    )

    # Only apply to players with KFT data AND limited PGA Tour experience
    has_kft = df["kft_sg_proxy"].notna() & (df["kft_sg_proxy"] > 0)
    limited_exp = df["pga_seasons"] <= max_pga_seasons
    eligible = has_kft & limited_exp

    n_eligible = int(eligible.sum())
    if n_eligible == 0:
        print("    ✓  KFT adjustment: no eligible players (all have sufficient PGA Tour history)")
        df = df.drop(columns=["kft_sg_proxy", "kft_top10s", "kft_year", "pga_seasons"], errors="ignore")
        return df

    # Scale: players with fewer PGA Tour seasons get more credit for KFT history
    exp_factor = (df.loc[eligible, "pga_seasons"] / max_pga_seasons).clip(0, 1)
    novelty = 1.0 - exp_factor   # 1.0 = brand new, 0.0 = fully experienced

    # KFT quality signal: z-score of kft_sg_proxy among eligible players
    sg_proxy = df.loc[eligible, "kft_sg_proxy"]
    if sg_proxy.std() > 0:
        sg_signal = ((sg_proxy - sg_proxy.mean()) / sg_proxy.std()).clip(-2, 2)
    else:
        sg_signal = pd.Series(0.0, index=sg_proxy.index)

    # Recency penalty: older KFT seasons are less relevant
    current_year = pd.Timestamp.now().year
    kft_age = (current_year - df.loc[eligible, "kft_year"]).clip(0, 4)
    recency = (1.0 - kft_age / 5.0).clip(0.2, 1.0)

    raw_adjust = sg_signal * novelty * recency * max_abs_adjust
    kft_adjust = raw_adjust.clip(-max_abs_adjust, max_abs_adjust)

    df["kft_adjustment"] = 0.0
    df.loc[eligible, "kft_adjustment"] = kft_adjust

    # Apply adjustment to probabilities
    market_scale = {
        "win_prob":   1.00,
        "top5_prob":  0.75,
        "top10_prob": 0.60,
        "top20_prob": 0.40,
    }
    for col, scale in market_scale.items():
        if col in df.columns:
            df[col] = (df[col] * (1 + df["kft_adjustment"] * scale)).clip(0.001, 0.999)

    # Renormalize win probs
    if "win_prob" in df.columns:
        total = float(df["win_prob"].sum())
        if total > 0:
            df["win_prob"] = (df["win_prob"] / total).clip(0, 1)

    boosted = int((kft_adjust > 0.005).sum())
    penalized = int((kft_adjust < -0.005).sum())
    print(f"    ✓  KFT adjustment applied: {n_eligible} eligible players, "
          f"{boosted} boosted, {penalized} penalized")
    if boosted:
        top_boosted = df.loc[eligible & (kft_adjust > 0.005), ["player_name", "kft_adjustment", "kft_sg_proxy", "pga_seasons"]]
        top_boosted = top_boosted.nlargest(5, "kft_adjustment")
        for _, row in top_boosted.iterrows():
            print(f"      ↑ {row['player_name']} (KFT proxy={row['kft_sg_proxy']:.2f}, "
                  f"PGA seasons={int(row['pga_seasons'])}, adj={row['kft_adjustment']:+.3f})")

    df = df.drop(columns=["kft_sg_proxy", "kft_top10s", "kft_year", "pga_seasons"], errors="ignore")
    return df


def apply_course_performance_adjustment(
    predictions_df: pd.DataFrame,
    boost_strength: float = 0.10,
    min_starts: int = 2,
    max_abs_adjust: float = 0.08,
    min_players_with_history: int = 8,
    allow_similar_fallback: bool = True,
) -> pd.DataFrame:
    """
    Apply a conservative post-model course adjustment with confidence shrinkage.

    Adjustment signal:
    - Primary: robust z-score of `course_perf_score` among players with history.
    - Secondary: SG edge (`course_sg_total_vs_avg`) blended when available.

    Guardrails:
    - Requires enough players with history.
    - Shrinks by starts-based confidence.
    - Hard-clips max absolute adjustment.
    - Uses smaller multipliers for top-5/top-10/top-20 than win%.
    """
    df = predictions_df.copy()

    if "course_perf_score" not in df.columns or "course_starts" not in df.columns:
        return df

    df["course_adjustment"] = 0.0
    df["course_adjustment_confidence"] = 0.0

    starts_num = pd.to_numeric(df["course_starts"], errors="coerce").fillna(0)
    history_mask = starts_num >= max(0, int(min_starts))
    eligible = history_mask & pd.to_numeric(df["course_perf_score"], errors="coerce").notna()
    n_history = int(eligible.sum())

    if n_history < max(3, int(min_players_with_history)):
        print(
            "    Skipping course history adjustment "
            f"(need >= {min_players_with_history} players with history, found {n_history})"
        )
        return df

    signal = _robust_zscore(df.loc[eligible, "course_perf_score"]).clip(-2.0, 2.0)
    signal_source = "history_only"

    if "course_sg_total_vs_avg" in df.columns:
        sg_edge = pd.to_numeric(df.loc[eligible, "course_sg_total_vs_avg"], errors="coerce")
        if int(sg_edge.notna().sum()) >= max(5, min_players_with_history // 2):
            sg_signal = _robust_zscore(sg_edge).clip(-2.0, 2.0).fillna(0.0)
            signal = 0.65 * signal + 0.35 * sg_signal
            signal_source = "history_plus_sg_edge"

    confidence = _experience_confidence(starts_num)
    if "course_history_confidence" in df.columns:
        confidence = np.minimum(
            confidence,
            pd.to_numeric(df["course_history_confidence"], errors="coerce").fillna(confidence),
        )
    confidence = pd.Series(confidence, index=df.index).clip(0, 1)

    hist_adjust = (signal * float(boost_strength) * confidence.loc[eligible]).clip(
        -abs(float(max_abs_adjust)),
        abs(float(max_abs_adjust)),
    )
    df.loc[eligible, "course_adjustment"] = hist_adjust
    df.loc[eligible, "course_adjustment_confidence"] = confidence.loc[eligible]

    similar_adjusted = 0
    if (
        allow_similar_fallback
        and "has_similar_course_data" in df.columns
        and "similar_course_sg_estimate" in df.columns
    ):
        similar_mask = (~history_mask) & df["has_similar_course_data"].fillna(False).astype(bool)
        valid_sim = similar_mask & pd.to_numeric(df["similar_course_sg_estimate"], errors="coerce").notna()
        if int(valid_sim.sum()) >= 3:
            sim_signal = _robust_zscore(df.loc[valid_sim, "similar_course_sg_estimate"]).clip(-1.5, 1.5)
            sim_adjust = (sim_signal * float(boost_strength) * 0.25).clip(-0.025, 0.025)
            df.loc[valid_sim, "course_adjustment"] = sim_adjust
            df.loc[valid_sim, "course_adjustment_confidence"] = 0.25
            similar_adjusted = int(valid_sim.sum())

    # Apply adjustment to probabilities (decreasing impact for broader finish markets)
    market_scale = {
        "win_prob": 1.00,
        "top5_prob": 0.75,
        "top10_prob": 0.60,
        "top20_prob": 0.45,
    }
    for col, scale in market_scale.items():
        if col in df.columns:
            df[f"{col}_pre_course_adj"] = df[col]
            df[col] = df[col] * (1 + df["course_adjustment"] * scale)
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(0.001, 0.999).fillna(0.001)

    # Renormalize win probability back to 1.0 field sum
    if "win_prob" in df.columns:
        total_win = float(df["win_prob"].sum())
        if total_win > 0:
            df["win_prob"] = (df["win_prob"] / total_win).clip(0, 1)

    adjusted_mask = df["course_adjustment"].abs() >= 0.005
    boosted = int((df["course_adjustment"] > 0.005).sum())
    penalized = int((df["course_adjustment"] < -0.005).sum())
    max_boost = float(df["course_adjustment"].max()) if len(df) else 0.0
    max_penalty = float(df["course_adjustment"].min()) if len(df) else 0.0
    avg_conf = float(df.loc[adjusted_mask, "course_adjustment_confidence"].mean()) if adjusted_mask.any() else 0.0

    print(
        f"    Course adjustment ({signal_source}): "
        f"{boosted} boosted, {penalized} penalized, {similar_adjusted} similar-course fallback"
    )
    print(
        "    Adjustment range: "
        f"{max_penalty:.1%} to +{max_boost:.1%} | "
        f"avg confidence {avg_conf:.2f}"
    )

    return df


def apply_course_win_boost(
    df: pd.DataFrame,
    boost_per_win: float = 0.012,
    max_boost: float = 0.04,
) -> pd.DataFrame:
    """
    Post-calibration multiplicative boost to win_prob for players with wins at this venue.

    The model's hist_wins feature has ~0.0001 importance because across all PGA Tour
    events, course wins are rare and not consistently predictive. But for unique,
    specialist venues (TPC Sawgrass, Augusta, Pebble Beach) past wins carry real signal
    that the model discards. This adds it back directly.

    boost_per_win: fractional boost per venue win (0.012 = 1.2% additive per win)
    max_boost: hard cap on total boost regardless of win count
    """
    if "wins_at_venue" not in df.columns:
        return df
    df = df.copy()
    wins = pd.to_numeric(df["wins_at_venue"], errors="coerce").fillna(0)
    boost = (wins * boost_per_win).clip(0, max_boost)
    df["win_prob"] = df["win_prob"] * (1 + boost)
    total = df["win_prob"].sum()
    if total > 0:
        df["win_prob"] = (df["win_prob"] / total).clip(0, 1)
    n_boosted = int((boost > 0).sum())
    print(f"    Course win boost: {n_boosted} players boosted (max boost {boost.max():.1%})")
    return df


def apply_course_history_upside_boost(
    df: pd.DataFrame,
    wr_min: int = 50,
    wr_max: int = 200,
    min_starts: int = 3,
    t10_rate_threshold: float = 0.33,
    perf_score_threshold: float = 1.0,
    max_boost: float = 0.08,
) -> pd.DataFrame:
    """
    Post-calibration boost for mid-ranked players (WR 50-200) with strong course history.

    The problem this solves:
    The model's world_rank_log feature penalizes players ranked 50-200 significantly.
    But world rank is a lagging indicator — a player who's missed time to injury or
    has been playing LIV/minor tours can be ranked 120 yet have exceptional course history
    at specific venues. The course_top_10_rate and course_perf_score columns capture this
    pattern, but the world rank penalty in the model overshadows them.

    This function adds it back as a post-processing multiplicative boost, similar to
    how apply_course_win_boost() re-adds venue win signal the model discards.

    Who qualifies:
    - World rank 50-200 (top players already handled by elite market blend; WR > 200
      probably not a true contender even with course history)
    - course_starts >= min_starts (need enough data to trust the pattern — 3+ starts)
    - course_top_10_rate >= t10_rate_threshold (33% = meaningfully above random)
    - course_perf_score >= perf_score_threshold (composite score above baseline)

    Boost formula:
    The boost scales with BOTH signals — a player with 50% T10 rate and perf score 2.0
    gets a larger boost than 33% T10 / perf 1.0. This rewards strong, consistent histories
    rather than fluky single results.

        boost_strength = (t10_rate - threshold) / (1 - threshold)  # 0-1 scale
        perf_scale = min(perf_score / 2.0, 1.0)                    # 0-1 scale (2.0 is very strong)
        boost = boost_strength * perf_scale * max_boost

    Max boost is 8% — conservative. A player with 50% T10 rate and perf score 2.0
    gets the full 8%. A player barely qualifying (33% / 1.0) gets ~0%.

    max_boost: float = 0.08,
        Hard cap on the multiplicative boost. 8% means win_prob * 1.08 before renorm.
    """
    required = {"world_rank", "course_top_10_rate", "course_perf_score", "course_starts"}
    missing = required - set(df.columns)
    if missing:
        print(f"    Course history upside boost skipped (missing columns: {missing})")
        return df

    df = df.copy()
    wr = pd.to_numeric(df["world_rank"], errors="coerce")
    t10_rate = pd.to_numeric(df["course_top_10_rate"], errors="coerce").fillna(0)
    perf_score = pd.to_numeric(df["course_perf_score"], errors="coerce").fillna(0)
    starts = pd.to_numeric(df["course_starts"], errors="coerce").fillna(0)

    # Who qualifies?
    mask = (
        wr.between(wr_min, wr_max)
        & (starts >= min_starts)
        & (t10_rate >= t10_rate_threshold)
        & (perf_score >= perf_score_threshold)
    )

    if not mask.any():
        print(f"    Course history upside boost: no eligible players (WR {wr_min}-{wr_max}, "
              f"T10 rate ≥{t10_rate_threshold:.0%}, perf ≥{perf_score_threshold})")
        return df

    # Scale both signals to 0-1, multiply together, scale by max_boost
    boost_strength = ((t10_rate - t10_rate_threshold) / (1.0 - t10_rate_threshold)).clip(0, 1)
    perf_scale = (perf_score / 2.0).clip(0, 1)
    boost = (boost_strength * perf_scale * max_boost)

    # Only apply to qualifying players
    boost = boost.where(mask, 0.0)

    df["win_prob"] = df["win_prob"] * (1 + boost)
    total = df["win_prob"].sum()
    if total > 0:
        df["win_prob"] = (df["win_prob"] / total).clip(0, 1)

    n_boosted = int((boost > 0).sum())
    if n_boosted > 0:
        boosted_df = df[mask].copy()
        boosted_df["_boost"] = boost[mask]
        boosted_df = boosted_df.sort_values("_boost", ascending=False)
        print(f"    Course history upside boost: {n_boosted} players boosted")
        for _, row in boosted_df.head(5).iterrows():
            name = str(row.get("player_name", "?"))
            if ", " in name:
                last, first = name.split(", ", 1)
                name = f"{first} {last}"
            print(f"      {name}: WR={int(row['world_rank'])}, "
                  f"T10={row['course_top_10_rate']:.0%}, "
                  f"perf={row['course_perf_score']:.2f}, "
                  f"boost=+{row['_boost']:.1%}")
    return df


def apply_finish_variance_adjustment(
    df: pd.DataFrame,
    win_boost_max: float = 0.06,
    placement_shift_max: float = 0.04,
) -> pd.DataFrame:
    """
    Adjust win_prob and top-N probabilities based on each player's historical
    finish variance profile (boom-bust score and consistency flag).

    The core insight:
    Two players with identical SG stats and world rank can have very different
    finish distributions. One wins occasionally but also misses cuts (boom-bust).
    The other never wins but reliably finishes T15-T30 (consistent grinder).
    The model treats them identically. This function separates them.

    What we adjust and why:

    Boom-or-bust players (high boom_bust_score):
      - Boost win_prob: their actual win rate is higher than their SG predicts
        because they can "get hot" in ways the model doesn't capture
      - Reduce top10/top20 prob: they're less reliable for placement bets
        (higher chance of going CUT instead of a safe T15)

    Consistent / low-variance players (low_variance = 1):
      - Reduce win_prob: they rarely win even when they're playing well
        (the model overestimates their win probability)
      - Boost top10/top20: they're more reliable for placement bets
        (they almost never miss cuts and regularly finish 10-25)

    Boost formula:
      We normalize boom_bust_score to a 0-1 scale relative to the field,
      so the adjustment is always relative — not an absolute threshold.
      This means the biggest boom-bust player in the field gets the full boost,
      not some hardcoded cutoff.

    win_boost_max: max fractional boost to win_prob for extreme boom-bust players
    placement_shift_max: max fractional shift to top10/top20 for consistency adjustments
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from features.finish_variance import compute_finish_variance
        variance_df = compute_finish_variance(min_year=2019, min_starts=15)
    except Exception as e:
        print(f"    Finish variance adjustment skipped: {e}")
        return df

    df = df.copy()

    # Normalize player names: predictions use 'Last, First', leaderboards use 'First Last'
    def _to_first_last(name: str) -> str:
        s = str(name).strip()
        if ", " in s:
            last, first = s.split(", ", 1)
            return f"{first} {last}"
        return s

    df["_name_fl"] = df["player_name"].apply(_to_first_last)

    # Merge variance stats by name
    df = df.merge(
        variance_df[["boom_bust_score", "finish_std", "low_variance", "cut_miss_rate"]].reset_index(),
        left_on="_name_fl",
        right_on="player_name",
        how="left",
        suffixes=("", "_var"),
    )

    matched = df["boom_bust_score"].notna().sum()
    print(f"    Finish variance: matched {matched}/{len(df)} players with variance data")

    # Fill unmatched players with field median (neutral — no adjustment)
    for col in ("boom_bust_score", "finish_std", "low_variance", "cut_miss_rate"):
        median_val = df[col].median()
        df[col] = df[col].fillna(median_val)

    # ── Boom-bust adjustment ────────────────────────────────────────────────
    # Normalize boom_bust_score to 0-1 relative to this field
    bb_min = df["boom_bust_score"].min()
    bb_max = df["boom_bust_score"].max()
    if bb_max > bb_min:
        bb_norm = (df["boom_bust_score"] - bb_min) / (bb_max - bb_min)
    else:
        bb_norm = pd.Series(0.0, index=df.index)

    # Boost win_prob for boom-bust players; reduce for consistent ones
    win_adj = bb_norm * win_boost_max - (df["low_variance"] * win_boost_max * 0.5)
    df["win_prob"] = (df["win_prob"] * (1 + win_adj)).clip(0, 1)

    # ── Placement adjustment (top5/top10/top20) ────────────────────────────
    # Consistent players are more reliable for placement bets
    # Boom-bust players are less reliable (miss cut instead of safe finish)
    if "top10_prob" in df.columns:
        placement_adj = (df["low_variance"] * placement_shift_max) - (bb_norm * placement_shift_max * 0.5)
        for col in ("top5_prob", "top10_prob", "top20_prob"):
            if col in df.columns:
                df[col] = (df[col] * (1 + placement_adj)).clip(0, 1)

    # Renormalize win_prob so field sums to ~1
    total = df["win_prob"].sum()
    if total > 0:
        df["win_prob"] = (df["win_prob"] / total).clip(0, 1)

    # Report top adjustments
    df["_win_adj"] = win_adj
    top_boosted = df.nlargest(3, "_win_adj")[["_name_fl", "boom_bust_score", "finish_std", "_win_adj"]]
    top_reduced = df.nsmallest(3, "_win_adj")[["_name_fl", "boom_bust_score", "finish_std", "_win_adj"]]
    print("      Win boosted (boom-bust):  " + " | ".join(
        f"{r['_name_fl']} +{r['_win_adj']:.1%}" for _, r in top_boosted.iterrows()
    ))
    print("      Win reduced (consistent): " + " | ".join(
        f"{r['_name_fl']} {r['_win_adj']:+.1%}" for _, r in top_reduced.iterrows()
    ))

    # Clean up temp columns
    df = df.drop(columns=["_name_fl", "_win_adj", "player_name_var"], errors="ignore")

    return df


def apply_elite_market_blend(
    df: pd.DataFrame,
    top_n: int = 15,
    max_market_weight: float = 0.25,
) -> pd.DataFrame:
    """
    For top world-ranked players, blend model win_prob toward market-implied probability.

    The model systematically underprices elite players — Scheffler at +480 gets 8.5%
    model vs 17.2% market. The market is very efficient at the top of the field where
    sharp money and media attention are highest. We blend toward market for rank 1-15.

    Weight schedule (linear decay):
      rank 1 → max_market_weight (e.g. 25% market)
      rank 8 → ~13% market
      rank 15 → 1.7% market
      rank 16+ → unchanged

    Requires vegas_prob from add_odds_to_predictions() — call this after odds integration.
    """
    if "vegas_prob" not in df.columns:
        print("    Elite market blend skipped (no vegas_prob — run with --tournament-id or --odds)")
        return df
    df = df.copy()
    rank = pd.to_numeric(df["world_rank"], errors="coerce")
    vegas = pd.to_numeric(df["vegas_prob"], errors="coerce")
    model_p = pd.to_numeric(df["win_prob"], errors="coerce")
    mask = rank.notna() & (rank <= top_n) & vegas.notna() & (vegas > 0) & model_p.notna()
    if not mask.any():
        print("    Elite market blend: no eligible top-ranked players found")
        return df
    mw = ((top_n - rank + 1) / top_n * max_market_weight).clip(0, max_market_weight)
    df.loc[mask, "win_prob"] = (1 - mw[mask]) * model_p[mask] + mw[mask] * vegas[mask]
    total = df["win_prob"].sum()
    if total > 0:
        df["win_prob"] = (df["win_prob"] / total).clip(0, 1)
    n_blended = int(mask.sum())
    print(f"    Elite market blend: {n_blended} players adjusted (top {top_n} world rank, max weight {max_market_weight:.0%})")
    return df


def apply_market_cut_blend(
    df: pd.DataFrame,
    tid: str,
    blend_weight: float = 0.20,
) -> pd.DataFrame:
    """
    Blend model cut_prob toward sportsbook-implied make_cut probability.

    The sportsbook (FanDuel) sets individual player make_cut lines based on
    sharp money, injury info, and course-specific data our model may not fully
    capture.  A 20% blend means:
        blended_cut_prob = 0.80 × model_cut_prob + 0.20 × market_implied_cut_prob

    This is Bayesian shrinkage toward a well-calibrated external prior.
    Unlike win_prob where the whole field sums to 1, cut_prob is independent
    per player (each one is a binary yes/no), so we apply the blend directly
    without renormalizing.

    Only adjusts players where we have a market line.  Players without a line
    keep their model cut_prob unchanged.

    Source file: data/odds/pga_market_odds_{tid}.csv
    Market: PLAYER_PROPS / "To Make The Cut"
    """
    odds_path = Path("data/odds") / f"pga_market_odds_{tid}.csv"
    if not odds_path.exists():
        print(f"    Market cut blend skipped (no file: pga_market_odds_{tid}.csv)")
        return df

    try:
        mkt = pd.read_csv(odds_path)
    except Exception as e:
        print(f"    Market cut blend skipped (read error: {e})")
        return df

    # Filter to make_cut rows only
    cut_rows = mkt[
        mkt["submarket_name"].str.lower().str.contains("make the cut", na=False)
    ].copy()
    if cut_rows.empty:
        print("    Market cut blend skipped (no 'To Make The Cut' rows in market odds)")
        return df

    # Vig removal: apply flat 5% factor (binary two-way market, not a pool)
    cut_rows["market_cut_prob"] = pd.to_numeric(
        cut_rows["implied_prob"], errors="coerce"
    ) / 1.05
    cut_rows = cut_rows[cut_rows["market_cut_prob"].notna()].copy()

    # Build name lookup — odds file uses "First Last", predictions use "Last, First"
    # Sorting tokens handles both: "Keith Mitchell" and "Mitchell, Keith"
    # both become the sorted key "keith mitchell".
    def _norm(name: str) -> str:
        """Lowercase, remove punctuation, sort tokens so name order doesn't matter."""
        tokens = str(name or "").lower().replace(",", " ").replace(".", "").split()
        tokens = [t for t in tokens if t not in {"jr", "sr", "ii", "iii", "iv"}]
        return " ".join(sorted(tokens))

    cut_lookup = {_norm(r["player_name"]): float(r["market_cut_prob"])
                  for _, r in cut_rows.iterrows()}

    if not cut_lookup:
        print("    Market cut blend skipped (empty lookup after normalization)")
        return df

    df = df.copy()
    if "cut_prob" not in df.columns:
        print("    Market cut blend skipped (no cut_prob column)")
        return df

    n_blended = 0
    for idx, row in df.iterrows():
        name_key = _norm(row.get("player_name", ""))
        market_p = cut_lookup.get(name_key)
        if market_p is None:
            continue
        model_p = pd.to_numeric(row.get("cut_prob"), errors="coerce")
        if pd.isna(model_p):
            continue
        blended = (1 - blend_weight) * model_p + blend_weight * market_p
        df.loc[idx, "cut_prob"] = float(np.clip(blended, 0.0, 1.0))
        if "miss_cut_prob" in df.columns:
            df.loc[idx, "miss_cut_prob"] = float(np.clip(1.0 - blended, 0.0, 1.0))
        n_blended += 1

    print(f"    Market cut blend: {n_blended}/{len(cut_rows)} players adjusted "
          f"(weight={blend_weight:.0%}, source={odds_path.name})")
    return df


def apply_augusta_fit_blend(
    df: pd.DataFrame,
    tid: str,
    top10_weight: float = 0.10,
    win_weight: float = 0.05,
    elimination_penalty: float = 0.80,
) -> pd.DataFrame:
    """
    Blend top10_prob / win_prob toward an Augusta-specific composite distribution.

    Only applied when masters_qualifiers_{tid}.csv exists (Masters week only).

    Composite scores each player by:
      Augusta avg to_par (30%) + SG T2G last 4 starts (25%) + cut rate (20%)
      + driving distance rank (15%) + model top10_prob (10%)

    Effect:
      - Players with high Augusta composite get a top10_prob / win_prob boost.
      - Players with qualifier_score <= 1 (first-timers, eliminated) get an
        additional elimination_penalty multiplier on top10_prob and win_prob.
        Rationale: model edges on these players are false positives from general
        SG stats — Augusta history is the better predictor.
    """
    qual_path = DATA_DIR / "qualitative" / f"masters_qualifiers_{tid}.csv"
    if not qual_path.exists():
        print(f"    Augusta fit blend skipped (no file: masters_qualifiers_{tid}.csv)")
        return df

    try:
        qdf = pd.read_csv(qual_path)
    except Exception as e:
        print(f"    Augusta fit blend skipped (read error: {e})")
        return df

    def _nk(n: str) -> str:
        s = str(n).strip().lower()
        if ", " in s:
            p = s.split(", ", 1)
            return f"{p[1]} {p[0]}"
        return s

    def _minmax(s: pd.Series) -> pd.Series:
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series([0.5] * len(s), index=s.index)
        return (s - mn) / (mx - mn)

    # Compute composite on qualifier df
    for col in ["augusta_avg_to_par", "sg_t2g_last4_total", "augusta_starts",
                "augusta_cuts_made", "driving_dist_field_rank"]:
        qdf[col] = pd.to_numeric(qdf[col], errors="coerce")
    qdf["augusta_starts"]          = qdf["augusta_starts"].fillna(1).clip(lower=1)
    qdf["augusta_cuts_made"]       = qdf["augusta_cuts_made"].fillna(0)
    qdf["driving_dist_field_rank"] = qdf["driving_dist_field_rank"].fillna(88)

    # Blend in model top10_prob from df for the 10% component
    df_keys = df.copy()
    df_keys["_key"] = df_keys["player_name"].apply(_nk)
    if "top10_prob" in df_keys.columns:
        prob_map = dict(zip(df_keys["_key"], pd.to_numeric(df_keys["top10_prob"], errors="coerce")))
        qdf["_key"] = qdf["player_name"].apply(_nk)
        qdf["_model_prob"] = qdf["_key"].map(prob_map).fillna(0)
    else:
        qdf["_model_prob"] = 0.0

    qdf["_s_aug"]     = _minmax(-qdf["augusta_avg_to_par"].fillna(0))
    qdf["_s_form"]    = _minmax(qdf["sg_t2g_last4_total"].fillna(0))
    qdf["_s_consist"] = _minmax(qdf["augusta_cuts_made"] / qdf["augusta_starts"])
    qdf["_s_dist"]    = _minmax(-qdf["driving_dist_field_rank"])
    qdf["_s_prob"]    = _minmax(qdf["_model_prob"])

    qdf["aug_composite"] = (
        0.30 * qdf["_s_aug"] +
        0.25 * qdf["_s_form"] +
        0.20 * qdf["_s_consist"] +
        0.15 * qdf["_s_dist"] +
        0.10 * qdf["_s_prob"]
    )
    qdf["aug_rank"] = qdf["aug_composite"].rank(ascending=False, method="min").astype(int)

    # Build lookup maps by normalized key
    comp_map  = dict(zip(qdf["_key"], qdf["aug_composite"]))
    qscore_map = dict(zip(qdf["_key"], qdf["qualifier_score"].astype(int)))
    rank_map  = dict(zip(qdf["_key"], qdf["aug_rank"].astype(int)))

    df = df.copy()
    df["_key"] = df["player_name"].apply(_nk)
    df["aug_composite"]       = df["_key"].map(comp_map)
    df["aug_qualifier_score"] = df["_key"].map(qscore_map).fillna(0).astype(int)
    df["aug_rank"]            = df["_key"].map(rank_map)
    df.drop(columns=["_key"], inplace=True)

    # --- Part B: blend top10_prob toward Augusta composite distribution ---
    # Only blend for players in the qualifier file (Masters field)
    has_comp = df["aug_composite"].notna()
    n_in_qual = int(has_comp.sum())
    if n_in_qual == 0:
        print("    Augusta fit blend: no players matched qualifier file")
        return df

    # Normalize composite to a probability distribution over the field
    comp_series = df.loc[has_comp, "aug_composite"].clip(lower=0)
    comp_total  = comp_series.sum()
    if comp_total <= 0:
        return df
    aug_dist = comp_series / comp_total  # sums to 1.0 over matched players

    # Blend top10_prob
    if "top10_prob" in df.columns:
        t10_sub = df.loc[has_comp, "top10_prob"].fillna(0)
        t10_total = t10_sub.sum()
        if t10_total > 0:
            t10_norm = t10_sub / t10_sub.sum()
            blended = (1 - top10_weight) * t10_norm + top10_weight * aug_dist
            df.loc[has_comp, "top10_prob"] = (blended * t10_total).clip(0, 1)

    # Blend win_prob (lighter weight)
    if "win_prob" in df.columns:
        wp_sub = df.loc[has_comp, "win_prob"].fillna(0)
        wp_total = wp_sub.sum()
        if wp_total > 0:
            wp_norm = wp_sub / wp_sub.sum()
            blended_w = (1 - win_weight) * wp_norm + win_weight * aug_dist
            df.loc[has_comp, "win_prob"] = (blended_w * wp_total).clip(0, 1)

    # --- Elimination penalty: first-timers and heavily eliminated players ---
    elim_mask = has_comp & (df["aug_qualifier_score"] <= 1)
    n_elim = int(elim_mask.sum())
    if n_elim > 0:
        for col in ["top10_prob", "top5_prob", "win_prob"]:
            if col in df.columns:
                df.loc[elim_mask, col] = (
                    df.loc[elim_mask, col] * elimination_penalty
                ).clip(0, 1)

    print(
        f"    Augusta fit blend: {n_in_qual} players, top10 weight={top10_weight:.0%}, "
        f"win weight={win_weight:.0%}, {n_elim} elimination-penalized"
    )
    return df


def apply_expert_consensus_blend(
    df: pd.DataFrame,
    tid: str,
    blend_weight: float = 0.12,
) -> pd.DataFrame:
    """
    Blend model win_prob 12% toward expert consensus distribution.

    Reads expert_picks_{tid}.csv, counts each player's appearances across all
    lineup_player_names arrays, normalizes to a probability distribution, then
    softly blends toward that distribution.

    Effect: Players selected by many experts get a probability boost; players
    selected by no experts get a slight reduction.
    """
    ep_path = DATA_DIR / "expert_picks" / f"expert_picks_{tid}.csv"
    if not ep_path.exists():
        print(f"    Expert consensus blend skipped (no file: expert_picks_{tid}.csv)")
        return df
    ep = pd.read_csv(ep_path)
    if len(ep) < 3:
        print(f"    Expert consensus blend skipped (only {len(ep)} experts, need >= 3)")
        return df
    counts: Counter = Counter()
    for names_json in ep['lineup_player_names'].dropna():
        try:
            for name in json.loads(names_json):
                counts[name] += 1
        except (json.JSONDecodeError, TypeError):
            pass
    if not counts:
        print("    Expert consensus blend skipped (no valid player names parsed)")
        return df
    total_experts = len(ep)
    df = df.copy()

    # Expert picks use "First Last" but predictions use "Last, First" — build a lookup
    # that handles both formats. Convert "First Last" → "Last, First" for matching.
    def _to_last_first(name: str) -> str:
        """Convert 'Collin Morikawa' → 'Morikawa, Collin'. Multi-part last names handled naively."""
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[-1]}, {' '.join(parts[:-1])}"
        return name

    normalized_counts: Counter = Counter()
    for name, cnt in counts.items():
        # Try "Last, First" format
        normalized_counts[_to_last_first(name)] += cnt
        # Also keep original in case predictions use "First Last"
        normalized_counts[name] += cnt

    def _lookup_expert_pct(pred_name: str) -> float:
        return normalized_counts.get(pred_name, 0) / total_experts

    df['expert_pct'] = df['player_name'].map(_lookup_expert_pct).fillna(0)
    expert_total = df['expert_pct'].sum()
    if expert_total == 0:
        print("    Expert consensus blend skipped (no expert picks matched field)")
        return df
    expert_dist = df['expert_pct'] / expert_total
    df['win_prob'] = (1 - blend_weight) * df['win_prob'] + blend_weight * expert_dist
    total = df['win_prob'].sum()
    if total > 0:
        df['win_prob'] = (df['win_prob'] / total).clip(0, 1)
    n_in = int((df['expert_pct'] > 0).sum())
    print(f"    Expert consensus blend: {n_in} players in expert lineups ({total_experts} experts, weight {blend_weight:.0%})")
    return df


def apply_probability_constraints(
    predictions_df: pd.DataFrame,
    normalize_topk: bool = True,
    favorite_bias_strength: float = 0.15,
    favorite_bias_half_life: float = 8.0,
    top5_cap: float = 0.65,
    top10_cap: float = 0.75,
    top20_cap: float = 0.85,
    max_top10_win_ratio: float = 20.0,
) -> pd.DataFrame:
    """
    Post-process probabilities for consistency:
    - Clip all probs to [0, 1]
    - Normalize win probs to sum to ~1.0 across field
    - Enforce monotonicity: top20 >= top10 >= top5 >= win
    - Cap top10/win ratio to avoid wild disconnects for weak-field players
    - Optionally normalize top-k totals toward expected field totals
    """
    df = predictions_df.copy()

    prob_cols = [
        "win_prob",
        "top5_prob",
        "top10_prob",
        "top20_prob",
        "win_prob_raw",
        "top5_prob_raw",
        "top10_prob_raw",
        "top20_prob_raw",
        "win_prob_calibrated",
        "top5_prob_calibrated",
        "top10_prob_calibrated",
        "top20_prob_calibrated",
    ]
    for c in prob_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").clip(0, 1).fillna(0.0)

    if "win_prob" in df.columns:
        total_win = float(df["win_prob"].sum())
        if total_win > 0:
            df["win_prob"] = (df["win_prob"] / total_win).clip(0, 1)

        # Favorite-bias correction: boost top-ranked win probs slightly, then renormalize.
        # This helps avoid over-dispersed fields where favorites are too compressed.
        if favorite_bias_strength > 0:
            rank = df["win_prob"].rank(ascending=False, method="first")
            decay = np.exp(-(rank - 1.0) / max(1e-6, float(favorite_bias_half_life)))
            weights = 1.0 + float(favorite_bias_strength) * decay
            df["win_prob"] = (df["win_prob"] * weights).clip(0, 1)
            total_win2 = float(df["win_prob"].sum())
            if total_win2 > 0:
                df["win_prob"] = (df["win_prob"] / total_win2).clip(0, 1)

    def _enforce_monotonic(work: pd.DataFrame) -> None:
        chain = ["win_prob", "top5_prob", "top10_prob", "top20_prob"]
        for i in range(1, len(chain)):
            prev_c = chain[i - 1]
            cur_c = chain[i]
            if prev_c in work.columns and cur_c in work.columns:
                work[cur_c] = np.maximum(work[cur_c], work[prev_c])

    def _project_with_bounds(
        current: pd.Series,
        lower: pd.Series,
        target_sum: float,
        upper_cap: float = 1.0,
        max_iter: int = 30,
    ) -> pd.Series:
        """Project probabilities to satisfy lower<=p<=cap and sum≈target."""
        p = pd.to_numeric(current, errors="coerce").fillna(0.0).to_numpy(dtype=float)
        lo = pd.to_numeric(lower, errors="coerce").fillna(0.0).to_numpy(dtype=float)
        cap = float(np.clip(upper_cap, 0.0, 1.0))

        lo = np.clip(lo, 0.0, cap)
        p = np.clip(np.maximum(p, lo), lo, cap)

        for _ in range(max_iter):
            total = float(p.sum())
            diff = float(target_sum - total)
            if abs(diff) <= 1e-9:
                break

            if diff > 0:
                headroom = np.clip(cap - p, 0.0, None)
                room = float(headroom.sum())
                if room <= 1e-12:
                    break
                p = p + (diff * headroom / room)
            else:
                reducible = np.clip(p - lo, 0.0, None)
                room = float(reducible.sum())
                if room <= 1e-12:
                    break
                p = p - ((-diff) * reducible / room)

            p = np.clip(p, lo, cap)

        return pd.Series(p, index=current.index)

    _enforce_monotonic(df)

    # Ratio cap: prevent top10_prob from being unreasonably large vs win_prob.
    # A 20x ratio means a 0.1% win-prob player is capped at 2% top10, which is
    # still realistic for a weak player in a soft field while avoiding 70x absurdities.
    # Apply before _project_with_bounds so the normalization redistributes cleanly.
    if max_top10_win_ratio > 0 and {"win_prob", "top10_prob"}.issubset(df.columns):
        ceiling = df["win_prob"] * max_top10_win_ratio
        df["top10_prob"] = np.minimum(df["top10_prob"], ceiling)
    if max_top10_win_ratio > 0 and {"win_prob", "top5_prob"}.issubset(df.columns):
        ceiling5 = df["win_prob"] * (max_top10_win_ratio * 0.6)
        df["top5_prob"] = np.minimum(df["top5_prob"], ceiling5)
    # Re-enforce monotonicity after capping
    _enforce_monotonic(df)

    if normalize_topk:
        if {"top5_prob", "win_prob"}.issubset(df.columns):
            df["top5_prob"] = _project_with_bounds(
                current=df["top5_prob"],
                lower=df["win_prob"],
                target_sum=5.0,
                upper_cap=top5_cap,
            )
        if {"top10_prob", "top5_prob"}.issubset(df.columns):
            df["top10_prob"] = _project_with_bounds(
                current=df["top10_prob"],
                lower=df["top5_prob"],
                target_sum=10.0,
                upper_cap=top10_cap,
            )
        if {"top20_prob", "top10_prob"}.issubset(df.columns):
            df["top20_prob"] = _project_with_bounds(
                current=df["top20_prob"],
                lower=df["top10_prob"],
                target_sum=20.0,
                upper_cap=top20_cap,
            )
        _enforce_monotonic(df)

    for c in ["win_prob", "top5_prob", "top10_prob", "top20_prob"]:
        if c in df.columns:
            df[c] = df[c].clip(0, 1)

    return df



def apply_dg_pretournament_blend(df: pd.DataFrame, blend_weight: float=0.35) -> pd.DataFrame:
    """ 
    Blend our calibrated probabilities with DG pre-tournament predictions.
    
    For each player, where DG data exists, replaces calibrated probs with: 
     (1 - blend_weight) * ours  +  blend_weight * DG     
      blend_weight=0.35 means 65% our model / 35% DG.                                                                   
      Players without DG data are unchanged.                                                                            
                                                                                                                        
      DG columns expected: dg_win, dg_top5, dg_top10, dg_top20, dg_make_cut                                             
      (values are 0–1 fractions, same scale as our calibrated probs)
      """
      
    pairs = [
        ('win_prob_calibrated', "dg_win"),
        ("top5_prob_calibrated",  "dg_top5"),
        ("top10_prob_calibrated", "dg_top10"),
        ("top20_prob_calibrated", "dg_top20"),
        ("cut_prob", 'dg_make_cut')
    ]
    
    has_dg = False
    for our_col, dg_col in pairs:
        if dg_col not in df.columns or our_col not in df.columns:
            continue 
        mask = df[dg_col].notna() & (df[dg_col] > 0)
        
        if not mask.any():
            continue
        has_dg = True
        df.loc[mask, our_col] = (
            (1 - blend_weight) * df.loc[mask, our_col] +
            blend_weight * df.loc[mask, dg_col]
        )

    if not has_dg:
        print(" No DG pre-tournament data available -- skipping blend.")
        return df
    
    n = df[df['dg_win'].notna() & (df['dg_win'] > 0)].shape[0] if "dg_win" in df.columns else 0
    print(f" DG Blend applied to {n} players (weight={blend_weight:.0%} DG / {1-blend_weight:.0%} ours)")
    
    
    for _, row in df.iterrows():
        pass # Constraints already applied by apply_probability_constraints - called before us 
    
    if "win_prob_calibrated" in df.columns:
        total = df["win_prob_calibrated"].sum()
        if total > 0:
            df["win_prob_calibrated"] = (df["win_prob_calibrated"] / total).clip(0, 1)
    return df


def apply_dg_skill_nudge(df: pd.DataFrame, scale: float=0.08) -> pd.DataFrame:
    """ 
    Light ranking nudge based on DG skill ratings, applied only to players
    where dg_win is unavailable (prob blend already covers the rest).
    
    dg_skill_total is SG vs tour average: + 1.0 = 1 stroke better than average.
    Multiplier = 1 + scale * (player_skill - field_mean_skill)
    Clambed to [0.85, 1.15] max +- 15% adjustment for extreme players.
    
    Applies to win/top5/top10/top20 probs, then renormalize win prob
    """
    
    #Only nudge players without DG pre-tournament coverage 
    if "dg_skill_total" not in df.columns:
        return df 
    
    no_dg_mask = df['dg_win'].isna() | (df['dg_win'] <= 0) if "dg_win" in df.columns else pd.Series(True, index=df.index)
    
    skill_col = df['dg_skill_total']
    has_skill = skill_col.notna() & (skill_col != 0)
    target = no_dg_mask & has_skill
    
    
    if not target.any():
        print(" DG skill nudge: no eligible players (all have DG prob coverage or no skill data)")
        return df 
    
    field_mean = skill_col[has_skill].mean()
    multiplier = (1 + scale * (skill_col - field_mean)).clip(0.85, 1.15)
    
    prob_cols = [c for c in ['win_prob_calibrated', 'top5_prob_calibrated', 'top10_prob_calibrated', 'top20_prob_calibrated'] if c in df.columns]
    
    for col in prob_cols:
        df.loc[target, col] = (df.loc[target, col] * multiplier[target]).clip(lower=0)
       
       
    delta_col = "dg_course_fit_delta_pct"
    if delta_col in df.columns:
        delta_mask = df[delta_col].notna() & (df[delta_col] != 0)
        if delta_mask.any():
            #course_fit_delta_pct: positive = dg likes this player more at this course 
            # Scaled: +10% -> ~5% boost, Clamped to [0.90, 1.10]
            delta_mult = (1 + 0.05 * df[delta_col].clip(-2, 2)).clip(0.90, 1.10)
            for col in prob_cols:
                df.loc[target & delta_mask, col] = (df.loc[target & delta_mask, col] * delta_mult[target & delta_mask]).clip(lower=0)
            n_delta = int(delta_mask.sum())
            print(f" DG skill nudge: applied course fit adjustment to {n_delta} players with course_fit_delta_pct data (mean delta {df.loc[delta_mask, delta_col].mean():.2f}%)")
    # Renormalize win_prob across full field
    if "win_prob_calibrated" in df.columns:
        total = df["win_prob_calibrated"].sum()
        if total > 0:
            df["win_prob_calibrated"] /= total 
            
    
    n = int(target.sum())
    print(f" DG Skill nudge applied to {n} players (scale={scale}, field mean = {field_mean:.3f})")
    return df 


        
        
### Step 9: Calculate Expected Value


def calculate_expected_value(predictions_df, purse, tournament_type='Standard'):
    """
    Calculate EV for each player using detailed prize distributions

    CHALLENGE 4 ✅: Uses actual PGA Tour prize money structure

    Args:
        predictions_df: DataFrame with win/top5/top10 probabilities
        purse: Tournament purse (e.g., 20000000)
        tournament_type: 'Standard', 'Signature', or 'Major'

    Returns:
        DataFrame with EV column added
    """
    
    print(f"\n  Calculating Expected Value...")
    print(f"    Purse: ${purse:,}")
    print(f"    Type: {tournament_type}")
    
    if "top20_prob" not in predictions_df.columns:
        predictions_df["top20_prob"] = (
            predictions_df["top10_prob"] + (predictions_df["top10_prob"] - predictions_df["top5_prob"]) * 1.2
        ).clip(0, 0.95)

    # For each player, calculate detailed EV
    evs = []
    for idx, row in predictions_df.iterrows():
        # Estimate top20 probability (simple heuristic since we don't have a model)
        # Assumes positions 11-20 have slightly lower prob than 6-10
        top20_prob_est = row['top20_prob'] 
        # Calculate detailed EV using actual prize distributions
        ev = calculate_expected_value_detailed(
            win_prob=row['win_prob'],
            top5_prob=row['top5_prob'],
            top10_prob=row['top10_prob'],
            top20_prob=top20_prob_est,
            purse=purse,
            tournament_type=tournament_type
        )
        evs.append(ev)

    predictions_df['expected_value'] = evs

    print(f"    ✓ Avg EV: ${predictions_df['expected_value'].mean():,.0f}")
    print(f"    ✓ Max EV: ${predictions_df['expected_value'].max():,.0f}")

    
    return predictions_df 



# Step 10: Rank and output 


def generate_recommendations(predictions_df, top_n=10):
    """
    Rank players by EV and format output

    Args:
        predictions_df: DataFrame with predictions and EV
        top_n: Number of top recommendations to show

    Returns:
        DataFrame sorted by EV
    """
    recommendations = predictions_df.sort_values('expected_value', ascending=False)
    # Format for display
    output_cols = [
        'player_id',
        'player_name',
        'expected_value',
        'win_prob',
        'top5_prob',
        'top10_prob',
        'hist_times_played',
        'hist_avg_finish',
        'sg_total'
    ]

    # Add cut probability if available
    if 'cut_prob' in predictions_df.columns:
        output_cols.extend(['cut_prob', 'cut_risk'])

    # Add course_fit_score if available
    if 'course_fit_score' in predictions_df.columns:
        output_cols.append('course_fit_score')
    if 'course_fit_raw' in predictions_df.columns:
        output_cols.append('course_fit_raw')

    # Add odds-related columns if available
    if 'ensemble_win_prob' in predictions_df.columns:
        output_cols.extend(['ensemble_win_prob', 'vegas_prob', 'model_vs_vegas_edge'])
        if 'odds_drift_flag' in predictions_df.columns:
            output_cols.extend(['odds_drift_flag', 'odds_drift_level'])

    # Add form features if available
    if 'form_trend' in predictions_df.columns:
        output_cols.extend(['form_trend', 'recent_top10s', 'recent_cuts_pct'])

    # Add usage strategy annotations if available
    if 'usage_recommendation' in predictions_df.columns:
        output_cols.extend(['usage_recommendation', 'usage_score', 'uses_remaining'])

    return recommendations[output_cols].head(top_n)


def _print_strategy_lineups(lineup_bundle: dict):
    """Pretty-print Safe/Balanced/Upside fantasy lineups."""
    profiles = lineup_bundle.get("profiles", {}) if isinstance(lineup_bundle, dict) else {}
    if not profiles:
        print("  No strategy lineups generated.")
        return

    print("\n" + "=" * 70)
    print("  FANTASY STRATEGY LINEUPS")
    print("=" * 70)

    for key in ["safe", "balanced", "upside"]:
        info = profiles.get(key, {})
        players = info.get("players", [])
        summary = info.get("summary", {})
        if not players:
            continue
        print(f"\n  {info.get('profile', key.title())} Lineup")
        print(f"    Players: {', '.join(players)}")
        print(
            "    Avg probs: "
            f"win={summary.get('avg_win_prob', 0.0)*100:.2f}% | "
            f"top10={summary.get('avg_top10_prob', 0.0)*100:.2f}% | "
            f"cut={summary.get('avg_cut_prob', 0.0)*100:.2f}%"
        )
        print(
            "    Avg strategy: "
            f"usage_score={summary.get('avg_usage_score', 0.0):.1f} | "
            f"leverage={summary.get('avg_leverage_raw', 0.0):+.3f}"
        )


def _save_strategy_lineups(lineup_bundle: dict, tournament: str, outputs_dir: Path):
    """Persist strategy lineup recommendations (JSON + flat CSV)."""
    if not isinstance(lineup_bundle, dict) or not lineup_bundle.get("profiles"):
        return

    safe_tournament = re.sub(r"[^a-z0-9]+", "_", tournament.lower()).strip("_")
    json_latest = outputs_dir / "lineup_strategies_latest.json"
    json_scoped = outputs_dir / f"{safe_tournament}_lineup_strategies.json"

    with open(json_latest, "w") as f:
        json.dump(lineup_bundle, f, indent=2, default=str)
    with open(json_scoped, "w") as f:
        json.dump(lineup_bundle, f, indent=2, default=str)

    rows = []
    for profile_key, info in lineup_bundle.get("profiles", {}).items():
        details = info.get("details", [])
        for idx, row in enumerate(details, start=1):
            flat = {
                "profile": profile_key,
                "profile_label": info.get("profile", profile_key.title()),
                "lineup_rank": idx,
                "player_name": row.get("player_name", ""),
                "uses_remaining": row.get("uses_remaining", ""),
                "usage_recommendation": row.get("usage_recommendation", ""),
                "usage_score": row.get("usage_score", np.nan),
                "win_prob": row.get("win_prob", np.nan),
                "top5_prob": row.get("top5_prob", np.nan),
                "top10_prob": row.get("top10_prob", np.nan),
                "top20_prob": row.get("top20_prob", np.nan),
                "cut_prob": row.get("cut_prob", np.nan),
                "model_gap_raw": row.get("model_gap_raw", np.nan),
                "leverage_raw": row.get("leverage_raw", np.nan),
                "leverage_score": row.get("leverage_score", np.nan),
                "course_fit_norm": row.get("course_fit_norm", np.nan),
                "sg_total_norm": row.get("sg_total_norm", np.nan),
                "sg_app_norm": row.get("sg_app_norm", np.nan),
                "hot_hand_norm": row.get("hot_hand_norm", np.nan),
                "engine_total_score": row.get("engine_total_score", np.nan),
                "engine_course_fit": row.get("engine_course_fit", np.nan),
                "scarcity_penalty": row.get("scarcity_penalty", np.nan),
            }
            for score_col in ["safe_score", "balanced_score", "upside_score"]:
                if score_col in row:
                    flat[score_col] = row.get(score_col, np.nan)
            rows.append(flat)

    if rows:
        df = pd.DataFrame(rows)
        csv_latest = outputs_dir / "lineup_strategies_latest.csv"
        csv_scoped = outputs_dir / f"{safe_tournament}_lineup_strategies.csv"
        df.to_csv(csv_latest, index=False)
        df.to_csv(csv_scoped, index=False)
        print(f"✓ Strategy lineups saved: {json_latest.name}, {csv_latest.name}")
    else:
        print(f"✓ Strategy lineups saved: {json_latest.name}")




#Step 11: Main function to tie it all together
def main():
    parser = argparse.ArgumentParser(
        description='Generate tournament predictions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with last 5 tournaments method (recommended)
  python scripts/predictions/predict_tournament.py \\
      --tournament "The Masters" \\
      --purse 18000000 \\
      --field data/fields/masters_2026.csv

  # Using weighted method (more weight to recent form)
  python scripts/predictions/predict_tournament.py \\
      --tournament "AT&T Pebble Beach Pro-Am" \\
      --purse 20000000 \\
      --field data/fields/pebble_beach_2026.csv \\
      --sg-method weighted \\
      --output outputs/pebble_predictions.csv
        """
    )

    parser.add_argument('--tournament', required=True, help='Tournament name')
    parser.add_argument('--tournament-id', default=None,
                       help='PGA Tour tournament ID for course fit (e.g., R2025002)')
    parser.add_argument('--purse', type=int, required=True, help='Tournament purse')
    parser.add_argument('--field', required=True, help='Path to field CSV')
    parser.add_argument('--output', default=None, help='Output file (optional)')
    parser.add_argument('--tournament-type', default='Standard',
                   choices=['Standard', 'Signature', 'Major'],
                   help='Tournament type (default: Standard)')
    parser.add_argument('--sg-method', default='last_5',
                       choices=['season_avg', 'last_5', 'weighted'],
                       help='Method for calculating recent SG stats (default: last_5)')
    parser.add_argument('--top-n', type=int, default=10,
                       help='Number of recommendations to show (default: 10)')
    parser.add_argument('--odds', default=None,
                       help='Path to odds CSV (or auto-finds from tournament-id)')
    parser.add_argument('--model-weight', type=float, default=0.6,
                       help='Weight for model in ensemble (0-1, default: 0.6)')
    parser.add_argument('--ensemble-method', default='log_odds',
                       choices=['weighted_avg', 'geometric', 'log_odds'],
                       help='Method for combining model + odds (default: log_odds)')
    parser.add_argument('--insights', action='store_true',
                       help='Generate narrative insights for predictions (rule-based)')
    parser.add_argument('--auto-insights', action='store_true',
                        help='Convenience flag to auto-run local insights without extra args')
    parser.add_argument('--insights-ollama', action='store_true',
                       help='Use Ollama (free, local) for LLM insights (requires: ollama serve)')
    parser.add_argument('--ollama-model', default='llama3.2',
                       help='Ollama model to use (default: llama3.2)')
    parser.add_argument('--insights-llm', action='store_true',
                       help='Use Claude API for deeper insights (requires ANTHROPIC_API_KEY)')
    parser.add_argument('--save-tracking', action='store_true',
                        help='Save predictions into data/prediction_tracking via PredictionTracker')
    parser.add_argument('--tournament-date', type=str, default=None,
                        help='Override date (YYYY-MM-DD) for tracking files')
    parser.add_argument('--record-lineup', type=str, default=None,
                        help='Comma-separated player names to record as used in UsageTracker')
    parser.add_argument('--no-calibrate', action='store_true',
                        help='Disable probability calibration (calibration is ON by default to fix overconfidence)')
    parser.add_argument('--calibrate', action='store_true',
                        help='[DEPRECATED] Calibration is now on by default. Use --no-calibrate to disable.')
    parser.add_argument('--usage-strategy', action='store_true',
                        help='Annotate recommendations with usage strategy (no usage is recorded)')
    parser.add_argument('--skip-bet-recs', action='store_true',
                        help='Skip tracked bet recommendation generation at end of prediction run')
    parser.add_argument('--no-prob-postprocess', action='store_true',
                        help='Disable probability post-processing (normalization + monotonic constraints)')
    parser.add_argument('--favorite-bias-strength', type=float, default=0.15,
                        help='Boost top-ranked win probabilities before normalization (default: 0.15)')
    parser.add_argument('--favorite-bias-half-life', type=float, default=8.0,
                        help='Decay speed for favorite-bias boost by rank (default: 8)')
    parser.add_argument('--top5-cap', type=float, default=0.65,
                        help='Upper cap for per-player top5 probability (default: 0.65)')
    parser.add_argument('--top10-cap', type=float, default=0.75,
                        help='Upper cap for per-player top10 probability (default: 0.75)')
    parser.add_argument('--top20-cap', type=float, default=0.85,
                        help='Upper cap for per-player top20 probability (default: 0.85)')
    parser.add_argument('--course-adjust-strength', type=float, default=0.12,
                        help='Base strength for course-history probability adjustment (default: 0.12)')
    parser.add_argument('--course-adjust-max', type=float, default=0.08,
                        help='Hard cap for absolute course-history adjustment (default: 0.08)')
    parser.add_argument('--course-adjust-min-starts', type=int, default=2,
                        help='Minimum starts at course for direct history adjustment (default: 2)')
    parser.add_argument('--course-adjust-min-players', type=int, default=5,
                        help='Minimum players with history needed to apply adjustment (default: 5)')
    parser.add_argument('--no-similar-course-adjust', action='store_true',
                        help='Disable similar-course fallback adjustments for players without direct history')
    parser.add_argument('--lineup-strategies', action='store_true',
                        help='Generate Safe/Balanced/Upside fantasy lineup strategy sets')
    parser.add_argument('--lineup-size', type=int, default=3,
                        help='Players per strategy lineup (default: 3)')
    parser.add_argument('--lineup-candidate-pool', type=int, default=45,
                        help='Candidate player pool size for lineup strategy optimizer (default: 45)')
    parser.add_argument('--lineup-max-overlap', type=int, default=1,
                        help='Max shared players allowed between strategy lineups (default: 1)')
    parser.add_argument('--skip-calibration-report', action='store_true',
                        help='Skip regeneration of outputs/calibration_data.json after predictions')

    args = parser.parse_args()

    print("=" * 70)
    print(f"  TOURNAMENT PREDICTION: {args.tournament}")
    print("=" * 70)

    # FIELD FILE VALIDATION: Ensure field file matches tournament ID
    # This prevents using wrong field files (e.g., using Genesis field for Pebble Beach)
    if args.tournament_id:
        expected_field_file = DATA_DIR / "fields" / f"field_{args.tournament_id}.csv"
        provided_field_path = Path(args.field)

        # Check if the expected field file exists
        if expected_field_file.exists():
            # Check if user provided a different file
            if provided_field_path.name != f"field_{args.tournament_id}.csv":
                print(f"\n  ⚠️  FIELD FILE MISMATCH WARNING!")
                print(f"      Provided:  {provided_field_path.name}")
                print(f"      Expected:  field_{args.tournament_id}.csv")
                print(f"      → Auto-switching to correct field file: {expected_field_file}")
                args.field = str(expected_field_file)
        else:
            # Expected file doesn't exist - warn user but continue
            if not provided_field_path.name.startswith(f"field_{args.tournament_id}"):
                print(f"\n  ⚠️  WARNING: Field file may not match tournament ID {args.tournament_id}")
                print(f"      Using: {provided_field_path.name}")
                print(f"      Recommended naming: field_{args.tournament_id}.csv")

    print('\n  Loading models and reference data...')
    models = load_models()
    master_df, stats_current, stats_prior = load_reference_data()

    print(f"\n  Loading field from {args.field}...")
    field_df = pd.read_csv(args.field)
    print(f"    ✓ Field size: {len(field_df)} players")

    # Field freshness check — withdrawals happen Tuesday/Wednesday;
    # a field file older than 72 hours may be missing late changes.
    import os as _os
    _field_age_hours = (_os.path.getmtime(args.field) and
                        (datetime.now().timestamp() - _os.path.getmtime(args.field)) / 3600)
    if _field_age_hours and _field_age_hours > 72:
        print(f"\n  ⚠️  FIELD FILE MAY BE STALE: {_field_age_hours:.0f}h old (>{72}h threshold)")
        print(f"      Withdrawals/changes since fetch may not be reflected.")
        print(f"      Re-run: python3 scripts/scrapers/fetch_field_from_pgatour.py "
              f"--pga-id {args.tournament_id or 'RYYYYNNN'} --name \"<name>\" "
              f"--output {args.field} --match-ids")
    elif _field_age_hours:
        print(f"    ✓ Field freshness: {_field_age_hours:.1f}h old (OK)")

    # Size sanity check — a normal PGA Tour field is 100–156 players
    if len(field_df) < 80:
        print(f"\n  ⚠️  SMALL FIELD WARNING: only {len(field_df)} players "
              f"(expected 100–156 for a standard event)")

    # Additional validation: Check field has expected columns
    # DG field files use 'player_num' for the PGA Tour player ID — normalize it
    if 'player_id' not in field_df.columns:
        if 'player_num' in field_df.columns:
            field_df = field_df.rename(columns={"player_num": "player_id"})
            print("    ✓ Mapped player_num → player_id (DG field format)")
        else:
            raise ValueError(f"Field file missing required 'player_id' column: {args.field}")

    field_df = enrich_field_names(field_df, master_df, tournament_id=args.tournament_id)

    print("\n  Building feature matrix...")
    features_df = build_feature_matrix(
        field_df, args.tournament, master_df,stats_current,
        sg_method=args.sg_method,stats_prior=stats_prior,
        tournament_id=args.tournament_id
    )

    print("\n  Filling missing values...")
    features_df = fill_missing_values(features_df, stats_current, master_df)

    print("\n  Making predictions...")
    predictions_df = make_predictions(features_df, models)



    predictions_df['top20_prob_raw'] = (
        predictions_df['top10_prob'] + (predictions_df['top10_prob'] - predictions_df['top5_prob']) * 1.2
        
    ).clip(0, 0.95)
    predictions_df['top20_prob'] = predictions_df['top20_prob_raw']




    # Apply probability calibration (fixes overconfidence in top5/top10)
    # Calibration is ON by default - use --no-calibrate to disable
    apply_calibration = not getattr(args, 'no_calibrate', False)
    if apply_calibration:
        print("\n  Applying probability calibration...")
        calibrator = ProbabilityCalibrator()
        predictions_df = calibrator.calibrate_predictions(
            predictions_df,
            method="bucket",
            tournament_type=args.tournament_type,
        )
        # Use calibrated probabilities for downstream calculations
        if 'win_prob_calibrated' in predictions_df.columns:
            predictions_df['win_prob_raw'] = predictions_df['win_prob']
            predictions_df['win_prob'] = predictions_df['win_prob_calibrated']
        if 'top5_prob_calibrated' in predictions_df.columns:
            predictions_df['top5_prob_raw'] = predictions_df['top5_prob']
            predictions_df['top5_prob'] = predictions_df['top5_prob_calibrated']
        if 'top10_prob_calibrated' in predictions_df.columns:
            predictions_df['top10_prob_raw'] = predictions_df['top10_prob']
            predictions_df['top10_prob'] = predictions_df['top10_prob_calibrated']
            
        predictions_df["top20_prob"] = (
            predictions_df["top10_prob"] + (predictions_df["top10_prob"] - predictions_df["top5_prob"]) * 1.2
        ).clip(0, 0.95)
        
        
        top20_cfg = calibrator._select_calibration(args.tournament_type).get("top20_prob")
        if top20_cfg:
            predictions_df["top20_prob_raw"] = predictions_df["top20_prob"]
            predictions_df["top20_prob"] = predictions_df["top20_prob"].apply(
                lambda v: calibrator._calibrate_value(v, top20_cfg)
            ).clip(0, 1)
        print("    ✓ Calibration applied (top5/top10/top20)")
        print("    → Raw probabilities saved as *_raw columns")
    else:
        print("\n  ⚠️ Calibration DISABLED (--no-calibrate flag)")
        print("    → Using raw model probabilities (may be overconfident)")

    # Apply course win boost (venue specialists — e.g. TPC Sawgrass winners)
    print("\n  Applying course win boost...")
    predictions_df = apply_course_win_boost(predictions_df)

    # Apply course history upside boost (WR 50-200 players with strong course history)
    print("\n  Applying course history upside boost...")
    predictions_df = apply_course_history_upside_boost(predictions_df)

    # Apply finish variance adjustment (boom-bust win boost, consistent player placement boost)
    print("\n  Applying finish variance adjustment...")
    predictions_df = apply_finish_variance_adjustment(predictions_df)

    # Apply course performance adjustment before other post-processing
    if "course_perf_score" in predictions_df.columns:
        print("\n  Applying course performance adjustment...")
        predictions_df = apply_course_performance_adjustment(
            predictions_df,
            boost_strength=float(np.clip(args.course_adjust_strength, 0.0, 0.5)),
            min_starts=max(0, int(args.course_adjust_min_starts)),
            max_abs_adjust=float(np.clip(args.course_adjust_max, 0.0, 0.5)),
            min_players_with_history=max(3, int(args.course_adjust_min_players)),
            allow_similar_fallback=(not args.no_similar_course_adjust),
        )

    # Apply KFT adjustment for players with limited PGA Tour history
    print("\n  Applying KFT development tour adjustment...")
    predictions_df = apply_kft_adjustment(predictions_df)

    if not args.no_prob_postprocess:
        print("\n  Applying probability post-processing constraints...")
        predictions_df = apply_probability_constraints(
            predictions_df,
            normalize_topk=True,
            favorite_bias_strength=max(0.0, float(args.favorite_bias_strength)),
            favorite_bias_half_life=max(1e-6, float(args.favorite_bias_half_life)),
            top5_cap=float(np.clip(args.top5_cap, 0.0, 1.0)),
            top10_cap=float(np.clip(args.top10_cap, 0.0, 1.0)),
            top20_cap=float(np.clip(args.top20_cap, 0.0, 1.0)),
        )
        sums = {}
        for c in ["win_prob", "top5_prob", "top10_prob", "top20_prob"]:
            if c in predictions_df.columns:
                sums[c] = float(predictions_df[c].sum())
        sum_msg = ", ".join([f"{k}={v:.2f}" for k, v in sums.items()])
        print(f"    ✓ Probability totals: {sum_msg}")

        top5_lt_win = int((predictions_df["top5_prob"] < predictions_df["win_prob"]).sum()) if {"top5_prob", "win_prob"}.issubset(predictions_df.columns) else 0
        top10_lt_top5 = int((predictions_df["top10_prob"] < predictions_df["top5_prob"]).sum()) if {"top10_prob", "top5_prob"}.issubset(predictions_df.columns) else 0
        top20_lt_top10 = int((predictions_df["top20_prob"] < predictions_df["top10_prob"]).sum()) if {"top20_prob", "top10_prob"}.issubset(predictions_df.columns) else 0
        print(
            "    ✓ Monotonic violations: "
            f"top5<win={top5_lt_win}, top10<top5={top10_lt_top5}, top20<top10={top20_lt_top10}"
        )

    # Add cut probability (risk of missing the cut)
    print("\n  Calculating cut probability...")
    try:
        predictions_df = add_cut_probability(predictions_df)
        high_risk = (predictions_df['cut_risk'].isin(['HIGH', 'ELEVATED'])).sum()
        print(f"    ✓ Cut probabilities calculated")
        print(f"    → {high_risk} players flagged as elevated/high cut risk")
    except Exception as e:
        print(f"    ⚠️ Cut model not available: {e}")

    print(f"\n  Calculating expected value (purse: ${args.purse:,})...")
    predictions_df = calculate_expected_value(predictions_df, args.purse, tournament_type=args.tournament_type)

    # ODDS INTEGRATION: Add Vegas odds and create ensemble predictions
    if args.odds or args.tournament_id:
        try:
            predictions_df = add_odds_to_predictions(
                predictions_df,
                tournament_id=args.tournament_id,
                odds_path=args.odds,
                model_weight=args.model_weight,
                method=args.ensemble_method
            )
        except Exception as e:
            print(f"  ⚠️ Odds ensemble failed: {e}")
            print("  Continuing with model-only probabilities.")

        # Apply elite market blend now that vegas_prob is available
        print("\n  Applying elite market blend...")
        predictions_df = apply_elite_market_blend(predictions_df)

        # Blend cut_prob toward sportsbook-implied make_cut probability
        if args.tournament_id:
            print("\n  Applying market cut blend...")
            predictions_df = apply_market_cut_blend(predictions_df, args.tournament_id)

        # Apply expert consensus blend
        if args.tournament_id:
            print("\n  Applying expert consensus blend...")
            predictions_df = apply_expert_consensus_blend(predictions_df, args.tournament_id)


        _course_hist_coverage = (
            (predictions_df.get('course_sg_starts', pd.Series(0)) > 1).mean()
            if "course_sg_starts" in predictions_df.columns else 0.0
        )
        
        _dg_blend_weight = 0.50 if _course_hist_coverage > 0.25 else 0.30
        print(f"\n Applying DG pre-tournament blend (weight={_dg_blend_weight:.2f}, course history coverage={_course_hist_coverage:.1%})...")
        print("\n  Applying DG pre-tournament blend...")
        predictions_df = apply_dg_pretournament_blend(predictions_df, blend_weight=_dg_blend_weight)

        print("\n  Applying DG skill nudge...")
        predictions_df = apply_dg_skill_nudge(predictions_df)

        # Apply Augusta fit blend (Masters only — skipped silently for other events)
        if args.tournament_id:
            print("\n  Applying Augusta fit blend...")
            predictions_df = apply_augusta_fit_blend(predictions_df, args.tournament_id)

    print("\n" + "=" * 70)
    print(f"  TOP {args.top_n} RECOMMENDATIONS")
    print("=" * 70)
    recommendations = generate_recommendations(predictions_df, top_n=args.top_n)

    # Optional: usage strategy annotation (no usage recorded)
    if args.usage_strategy:
        try:
            optimizer = UsageOptimizer()
            usage_recs = []
            usage_scores = []
            usage_remaining = []
            for _, row in recommendations.iterrows():
                rec = optimizer.should_use_player(row['player_name'], args.tournament)
                usage_recs.append(rec.get('recommendation', 'UNKNOWN'))
                usage_scores.append(rec.get('score', 0))
                usage_remaining.append(rec.get('remaining_uses', 3))
            recommendations = recommendations.copy()
            recommendations['usage_recommendation'] = usage_recs
            recommendations['usage_score'] = usage_scores
            recommendations['uses_remaining'] = usage_remaining
        except Exception as e:
            print(f"  ⚠️ Usage strategy annotation failed: {e}")

    # Format probabilities as percentages
    recommendations_display = recommendations.copy()
    recommendations_display['win_prob'] = recommendations_display['win_prob'].apply(lambda x: f"{x*100:.2f}%")
    recommendations_display['top5_prob'] = recommendations_display['top5_prob'].apply(lambda x: f"{x*100:.2f}%")
    recommendations_display['top10_prob'] = recommendations_display['top10_prob'].apply(lambda x: f"{x*100:.2f}%")
    recommendations_display['expected_value'] = recommendations_display['expected_value'].apply(lambda x: f"${x:,.0f}")

    print(recommendations_display.to_string(index=False))

    # Optional: build fantasy strategy lineups from model + usage + leverage.
    if args.lineup_strategies:
        try:
            optimizer = UsageOptimizer()
            lineup_bundle = optimizer.build_strategy_lineups(
                predictions_df=predictions_df,
                tournament_name=args.tournament,
                lineup_size=max(1, int(args.lineup_size)),
                candidate_pool_size=max(12, int(args.lineup_candidate_pool)),
                max_overlap_between_lineups=max(0, int(args.lineup_max_overlap)),
            )
            _print_strategy_lineups(lineup_bundle)
        except Exception as e:
            lineup_bundle = {}
            print(f"  ⚠️ Strategy lineup generation failed: {e}")
    else:
        lineup_bundle = {}

    # ── DFS ownership proxy ──────────────────────────────────────────────────
    # Approximates what % of DFS lineups will contain each player.
    # Formula: consensus_prob^0.75 scales the win probability into an ownership
    # range (~2-35%). Lower exponent = more compressed top, less "chalky" feel.
    # The lineup optimizer uses this to reward high-edge, low-ownership picks.
    if "vegas_prob" in predictions_df.columns:
        _vp = predictions_df["vegas_prob"].clip(lower=0)
        predictions_df["dfs_ownership_proj"] = (_vp ** 0.75 * 100).round(1)
    elif "win_prob" in predictions_df.columns:
        _vp = predictions_df["win_prob"].clip(lower=0)
        predictions_df["dfs_ownership_proj"] = (_vp ** 0.75 * 100).round(1)

    # Always persist predictions to a standard location for downstream tools
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Primary user-specified output (if provided)
    if args.output:
        predictions_df.to_csv(args.output, index=False)
        print(f"\n✓ Full predictions saved to: {args.output}")

    # Consistent "latest" pointers for automation / GolfAssistant
    # Stamp tournament_id so downstream tools (chatbot, context builder) can identify the week
    if args.tournament_id and "tournament_id" not in predictions_df.columns:
        predictions_df.insert(0, "tournament_id", str(args.tournament_id).strip().upper())
    latest_path = outputs_dir / "latest_predictions.csv"
    predictions_df.to_csv(latest_path, index=False)

    # Also save a tournament-scoped latest file (e.g., farmers_insurance_open_latest.csv)
    safe_tournament = re.sub(r"[^a-z0-9]+", "_", args.tournament.lower()).strip("_")
    scoped_latest_path = outputs_dir / f"{safe_tournament}_latest.csv"
    predictions_df.to_csv(scoped_latest_path, index=False)

    # Write data dictionaries alongside outputs
    write_data_dictionary(predictions_df, outputs_dir / "latest_predictions_data_dictionary.md")
    write_data_dictionary(predictions_df, outputs_dir / f"{safe_tournament}_latest_data_dictionary.md")
    if args.output:
        output_path = Path(args.output)
        dd_path = output_path.with_suffix(output_path.suffix + ".data_dictionary.md")
        write_data_dictionary(predictions_df, dd_path)

    print(f"✓ Latest predictions pointers written to: {latest_path} and {scoped_latest_path}")
    if args.lineup_strategies and lineup_bundle:
        _save_strategy_lineups(lineup_bundle, args.tournament, outputs_dir)

    if not args.skip_calibration_report:
        print("\n  Refreshing calibration report...")
        cal_cmd = [
            "python3",
            str(PROJECT_ROOT / "scripts" / "validation" / "generate_calibration_data.py"),
        ]
        cal_result = subprocess.run(cal_cmd, cwd=str(PROJECT_ROOT), capture_output=False, text=True)
        if cal_result.returncode != 0:
            print("  ⚠️ Calibration report refresh failed; continuing.")

    # Optional tracked betting recommendations (enabled by default for direct runs).
    if args.tournament_id and not args.skip_bet_recs:
        print("\n  Generating tracked bet recommendations...")
        pred_source = str(Path(args.output)) if args.output else str(scoped_latest_path)
        rec_cmd = [
            "python3",
            str(PROJECT_ROOT / "scripts" / "models" / "recommend_bets.py"),
            "--tournament-id",
            str(args.tournament_id).strip().upper(),
            "--predictions",
            pred_source,
        ]
        rec_result = subprocess.run(rec_cmd, cwd=str(PROJECT_ROOT), capture_output=False, text=True)
        if rec_result.returncode != 0:
            print("  ⚠️ Bet recommendations failed; continuing.")

    # Generate insights if requested
    run_insights = args.insights or args.auto_insights or args.insights_ollama or args.insights_llm

    if run_insights:
        print("\n" + "=" * 70)
        print("  GENERATING INSIGHTS...")
        print("=" * 70)

        # Load course weights for this tournament
        course_weights = {}
        weights_file = DATA_DIR / "course_sg_weights.csv"
        if weights_file.exists():
            weights_df = pd.read_csv(weights_file)
            # Try to match tournament name
            match = weights_df[weights_df['tournament_name'].str.lower().str.contains(
                args.tournament.lower().replace('the ', ''), na=False
            )]
            if len(match) > 0:
                row = match.iloc[0]
                course_weights = {
                    'ott_sg': row['ott_sg'],
                    'app_sg': row['app_sg'],
                    'arg_sg': row['arg_sg'],
                    'putt_sg': row['putt_sg'],
                }
                print(f"  Loaded course weights for: {row['tournament_name']}")

        generator = InsightsGenerator()

        if args.insights_llm:
            # Use Claude API for deeper insights
            print("  Using Claude API...")
            insights_text = generator.generate_llm_insights(
                predictions_df, args.tournament, course_weights, top_n=args.top_n
            )
            print("\n" + insights_text)
        elif args.insights_ollama:
            # Use Ollama (free, local) for LLM insights
            print(f"  Using Ollama ({args.ollama_model})...")
            insights_text = generator.generate_ollama_insights(
                predictions_df, args.tournament, course_weights,
                top_n=args.top_n, model=args.ollama_model
            )
            print("\n" + insights_text)
        else:
            # Use local rule-based insights
            insights = generator.generate_local_insights(
                predictions_df, args.tournament, course_weights, top_n=args.top_n
            )
            print(generator.format_insights_text(insights))

    print("\n" + "=" * 70)
    print("  PREDICTION COMPLETE!")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Auto-save predictions to tracking on every run
    # ------------------------------------------------------------------
    try:
        tracker = PredictionTracker()
        tracker.save_predictions(
            predictions_df,
            tournament_name=args.tournament,
            tournament_date=args.tournament_date,
            tournament_id=getattr(args, "tournament_id", None),
        )
        # Sync to outputs/prediction_history.csv so the dashboard can read it
        _out_base = Path(args.output) if args.output else Path("outputs/latest_predictions.csv")
        _outputs_hist = _out_base.parent / "prediction_history.csv"
        _tracking_hist = tracker.tracking_file
        if _tracking_hist.exists():
            import shutil as _shutil
            _shutil.copy2(_tracking_hist, _outputs_hist)
            print(f"  Prediction history synced → {_outputs_hist}")
    except Exception as _te:
        print(f"  Warning: prediction tracking skipped ({_te})")

    if args.record_lineup:
        lineup = [p.strip() for p in args.record_lineup.split(",") if p.strip()]
        if lineup:
            usage_tracker = UsageTracker()
            for player in lineup:
                usage_tracker.record_usage(player, args.tournament, tournament_date=args.tournament_date)
            print(f"  Recorded lineup usage for: {', '.join(lineup)}")

if __name__ == '__main__':
    main()


# ============================================================================
# CODING CHALLENGES STATUS
# ============================================================================
# ✅ Challenge 1: Better SG Stats (Rolling Average) - IMPLEMENTED
#    - Added 'last_5' method that uses only last 5 tournaments
#
# ✅ Challenge 2: Weighted Recent Form - IMPLEMENTED
#    - Added 'weighted' method with customizable weights
#    - Default: [0.4, 0.3, 0.2, 0.1] for last 4 tournaments
#
# ✅ Challenge 3: Better Missing Value Handling - IMPLEMENTED
#    - Calculates median SG stats from actual 2025 data
#    - Adds rookie penalty for players without course history
#
# ✅ Challenge 4: More Accurate EV Calculation - IMPLEMENTED
#    - Uses actual PGA Tour prize distributions
#    - Accounts for tournament type (Standard/Signature/Major)
#    - Breaks down top-5 into individual positions
#    - Improvement: 10-20% higher EV for strong players
#
# ⏳ Challenge 5: Field CSV Creator - TODO
#    - Build helper script to scrape fields from PGA Tour website
#    - See: scripts/scrapers/ for examples
# ============================================================================
