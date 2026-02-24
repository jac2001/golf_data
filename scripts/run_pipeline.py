#!/usr/bin/env python3
"""
Golf Prediction Pipeline Runner
================================
Single script to run the entire prediction pipeline end-to-end.

Stages:
1. DATA REFRESH - Fetch latest rankings, player database, form stats
2. FIELD FETCH - Get tournament field (from PGA TOUR or manual)
3. PREDICTIONS - Run the prediction model
4. INSIGHTS - Generate AI insights (optional)
5. LINEUP - Recommend optimal lineup with usage strategy

Usage:
    # Run everything for a tournament
    python scripts/run_pipeline.py --tournament "The American Express" --purse 8400000

    # Skip data refresh (use cached data)
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 --skip-refresh

    # With specific field file
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
        --field data/fields/masters_2026.csv

    # Full pipeline with insights and lineup
    python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
        --insights --lineup

    # Weekly automation mode
    python scripts/run_pipeline.py --weekly-refresh
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import json
import pandas as pd
from typing import Optional

# ============================================================================
# Configuration
# ============================================================================

# Resolve project root dynamically from this file location so the
# pipeline can run on any machine/path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure project root is on path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SCHEDULE_PATH = DATA_DIR / "raw" / "schedule_2026.csv"

# Pipeline stages and their scripts
PIPELINE_STAGES = {
    "player_database": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_player_database.py",
        "description": "Fetch PGA Tour player database",
        "output": DATA_DIR / "players" / f"pga_players_{datetime.now().year}.csv",
    },
    "world_rankings": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_world_rankings.py",
        "description": "Fetch OWGR world rankings",
        "output": DATA_DIR / "rankings" / f"owgr_{datetime.now().year}.csv",
    },
    "form_stats": {
        "script": SCRIPTS_DIR / "scrapers" / "fetch_form_stats.py",
        "description": "Fetch recent form statistics",
        "output": DATA_DIR / "historical" / f"form_stats_{datetime.now().year}.csv",
    },
    "course_form_features": {
        "script": SCRIPTS_DIR / "features" / "consolidate_course_form_stats.py",
        "description": "Build player-course performance features",
        "output": DATA_DIR / "processed" / "player_course_performance.csv",
    },
    "course_similarity": {
        "script": SCRIPTS_DIR / "features" / "course_similarity.py",
        "description": "Build course similarity matrix and profiles",
        "output": DATA_DIR / "processed" / "course_similarity_matrix.csv",
    },
    "predictions": {
        "script": SCRIPTS_DIR / "predictions" / "predict_tournament.py",
        "description": "Generate tournament predictions",
    },
}


def slugify(name: str) -> str:
    """Basic slugify for filenames and optional power rankings slug."""
    import re
    slug = name.lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"\\s+", "-", slug.strip())
    return slug


def print_header(text: str, char: str = "="):
    """Print a formatted header."""
    print()
    print(char * 70)
    print(f"  {text}")
    print(char * 70)


def print_stage(stage_num: int, total: int, name: str):
    """Print stage progress."""
    print(f"\n[{stage_num}/{total}] {name}")
    print("-" * 50)


def run_command(cmd: list, description: str = "", check: bool = True) -> bool:
    """Run a command and return success status."""
    print(f"  Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=False,
            text=True,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  Error: {e}")
        return False


def check_file_fresh(filepath: Path, max_age_hours: int = 24) -> bool:
    """Check if a file exists and is recent enough."""
    if not filepath.exists():
        return False

    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    age_hours = (datetime.now() - mtime).total_seconds() / 3600

    return age_hours < max_age_hours


def load_schedule(path: Path = SCHEDULE_PATH) -> pd.DataFrame:
    """Load schedule CSV (expects columns: tournament_name, start_date, end_date, purse, tournament_type)."""
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # Normalize money columns
    for col in ["purse", "winner_share"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Normalize names for lookup
    if "tournament_name" in df.columns:
        df["name_key"] = df["tournament_name"].str.lower().str.strip()
    return df


def find_schedule_row(
    tournament_name: str = None,
    on_date: str = None,
    schedule_path: Path = SCHEDULE_PATH,
) -> Optional[dict]:
    """Find a tournament row by name or by date (YYYY-MM-DD).

    If on_date is provided and falls between tournaments, returns the NEXT
    upcoming tournament (prep week behavior).
    """
    df = load_schedule(schedule_path)
    if df.empty:
        return None

    if tournament_name:
        key = tournament_name.lower().strip()
        match = df[df["name_key"] == key]
        if match.empty:
            # fallback partial match
            match = df[df["name_key"].str.contains(key[:12], na=False)]
        if not match.empty:
            return match.iloc[0].to_dict()

    if on_date:
        try:
            d = datetime.strptime(on_date, "%Y-%m-%d").date()
            df["start_date_dt"] = pd.to_datetime(df["start_date"]).dt.date
            df["end_date_dt"] = pd.to_datetime(df["end_date"]).dt.date

            # First try: find tournament currently in progress
            match = df[(df["start_date_dt"] <= d) & (df["end_date_dt"] >= d)]
            if not match.empty:
                return match.iloc[0].to_dict()

            # Second try: find next upcoming tournament (prep week)
            upcoming = df[df["start_date_dt"] > d].sort_values("start_date_dt")
            if not upcoming.empty:
                return upcoming.iloc[0].to_dict()
        except Exception:
            pass

    return None


def refresh_data(force: bool = False, max_age_hours: int = 24):
    """Refresh all data sources."""
    print_header("DATA REFRESH")

    stages = ["player_database", "world_rankings", "form_stats", "course_form_features", "course_similarity"]
    total = len(stages)

    for i, stage_name in enumerate(stages, 1):
        stage = PIPELINE_STAGES[stage_name]
        print_stage(i, total, stage["description"])

        # Check if refresh needed
        output_file = stage.get("output")
        should_use_freshness = stage_name != "course_form_features"
        if should_use_freshness and output_file and not force and check_file_fresh(output_file, max_age_hours):
            print(f"  Skipping - data is fresh ({output_file.name})")
            continue

        # Run the script
        script_path = stage["script"]
        if script_path.exists():
            cmd = ["python3", str(script_path)]
            if stage_name == "form_stats":
                cmd.extend(["--year", str(datetime.now().year)])
            elif stage_name == "course_form_features":
                now_year = datetime.now().year
                # Use 5 years of history for better course performance data
                years = [str(now_year - i) for i in range(5, -1, -1)]  # 5 years back + current
                cmd.extend(["--years"] + years)
            success = run_command(cmd)
            if success:
                print(f"  Done")
            else:
                print(f"  Warning: {stage_name} failed, continuing...")
        else:
            print(f"  Warning: Script not found: {script_path}")


def find_field_file(tournament_name: str, tournament_id: str = None) -> Path:
    """Try to find an existing field file for a tournament.

    Lookup order:
    1. Canonical ID-based file  data/fields/field_{tournament_id}.csv  (most reliable)
    2. Fuzzy name match inside data/fields/ and data/fields/archive/
    """
    import re

    # 1. Canonical ID-based lookup — guaranteed to be the right tournament
    if tournament_id:
        canonical = DATA_DIR / "fields" / f"field_{tournament_id}.csv"
        if canonical.exists():
            return canonical

    # 2. Fuzzy name-based fallback (first 10 chars of normalized name)
    name_clean = re.sub(r'[^\w\s]', '', tournament_name.lower()).replace(' ', '_')
    field_dirs = [
        DATA_DIR / "fields",
        DATA_DIR / "fields" / "archive",
    ]
    for field_dir in field_dirs:
        if not field_dir.exists():
            continue
        for f in field_dir.glob("*.csv"):
            if name_clean[:10] in f.stem.lower():
                return f

    return None


def fetch_field_from_pga(tournament_name: str, tournament_id: str = None) -> Path:
    """Fetch field from PGA TOUR if possible."""
    print("\n  Attempting to fetch field from PGA TOUR...")

    # If no tournament_id provided, we can't fetch
    if not tournament_id:
        print("  No PGA TOUR tournament ID provided, cannot auto-fetch field")
        return None

    # Always use canonical ID-based path to avoid stale name-based files
    output_path = DATA_DIR / "fields" / f"field_{tournament_id}.csv"

    script_path = SCRIPTS_DIR / "scrapers" / "fetch_field_from_pgatour.py"
    if script_path.exists():
        success = run_command([
            "python3", str(script_path),
            "--pga-id", tournament_id,
            "--output", str(output_path),
            "--match-ids",
            "--name", tournament_name,
        ])
        if success and output_path.exists():
            return output_path

    return None


def run_predictions(
    tournament_name: str,
    purse: int,
    field_path: Path,
    tournament_type: str = "Standard",
    sg_method: str = "last_5",
    insights: bool = False,
    insights_ollama: bool = False,
    save_tracking: bool = False,
    odds_path: Path = None,
    calibrate: bool = False,
) -> Path:
    """Run the prediction model."""
    print_header("GENERATING PREDICTIONS")

    # Build output path
    date_str = datetime.now().strftime("%Y%m%d")
    output_name = f"{tournament_name.lower().replace(' ', '_')}_{date_str}_predictions.csv"
    output_path = OUTPUTS_DIR / output_name

    # Build command
    cmd = [
        "python3", str(SCRIPTS_DIR / "predictions" / "predict_tournament.py"),
        "--tournament", tournament_name,
        "--purse", str(purse),
        "--field", str(field_path),
        "--tournament-type", tournament_type,
        "--sg-method", sg_method,
        "--course-adjust-strength", "0.12",
        "--course-adjust-max", "0.08",
        "--course-adjust-min-starts", "2",
        "--course-adjust-min-players", "5",
        "--output", str(output_path),
        "--top-n", "20",
        "--skip-bet-recs",
    ]

    if insights:
        cmd.append("--insights")

    if insights_ollama:
        cmd.append("--insights-ollama")

    if save_tracking:
        cmd.append("--save-tracking")

    if odds_path and odds_path.exists():
        cmd.extend(["--odds", str(odds_path)])

    if calibrate:
        cmd.append("--calibrate")

    success = run_command(cmd)

    if success and output_path.exists():
        print(f"\n  Predictions saved to: {output_path}")
        return output_path

    return None


def run_lineup_recommendation(
    tournament_name: str,
    predictions_path: Path = None,
):
    """Run strategic lineup recommendation."""
    print_header("LINEUP RECOMMENDATION")

    from scripts.predictions.golf_assistant import GolfAssistant

    # Pass the predictions path so we use the correct file
    assistant = GolfAssistant(predictions_path=str(predictions_path) if predictions_path else None)

    result = assistant.get_lineup_recommendation(tournament_name=tournament_name)

    if "error" in result:
        print(f"  Error: {result['error']}")
        return

    print(f"\n  Tournament: {result['tournament_name']}")
    print(f"  Tier: {result.get('tournament_importance', 'N/A')}/10 importance")
    print()

    for reason in result['reasoning']:
        print(f"  {reason}")

    if result.get('strategic_notes'):
        print("\n  Strategic Notes:")
        for note in result['strategic_notes']:
            print(f"    - {note}")

    print("\n  RECOMMENDED LINEUP:")
    print("  " + "-" * 60)

    for i, player in enumerate(result['lineup'], 1):
        uses = player.get('uses_remaining', '?')
        rec = player.get('usage_recommendation', '')
        print(f"  {i}. {player['name']}")
        print(f"     EV: ${player['ev']:,.0f} | Win: {player['win_prob']*100:.1f}% | Uses: {uses}")
        if rec and rec not in ['USE', 'STRONG USE']:
            print(f"     Note: {rec}")


def run_bet_recommendations(
    tournament_id: str,
    predictions_path: Optional[Path] = None,
):
    """Generate deterministic tracked betting recommendations."""
    if not tournament_id:
        print("\n  Skipping bet recommendations - no tournament ID provided")
        return False

    print_header("BET RECOMMENDATIONS")
    cmd = [
        "python3",
        str(SCRIPTS_DIR / "models" / "recommend_bets.py"),
        "--tournament-id",
        str(tournament_id).strip().upper(),
        "--min-confidence",
        "0.60",
        "--min-edge-points",
        "1.00",
        "--min-ev",
        "0.00",
    ]
    if predictions_path and Path(predictions_path).exists():
        cmd.extend(["--predictions", str(predictions_path)])

    success = run_command(cmd)
    if not success:
        print("  Warning: recommendation generation failed, continuing...")
    return success


def fetch_tournament_assets(
    tournament_name: str,
    pga_id: str,
    field_path: Path,
    power_slug: str = None,
    odds_max_age_hours: float = 6.0,
    force_odds_refresh: bool = False,
    dk_props_max_age_hours: float = 6.0,
    force_dk_props_refresh: bool = False,
    fetch_expert_picks: bool = True,
    fetch_articles: bool = False,
    article_template: str = None,
):
    """Fetch tournament assets used by dashboard and betting workflow."""
    print_header("TOURNAMENT ASSETS")

    total_stages = 5
    if fetch_expert_picks and pga_id:
        total_stages += 1
    if fetch_articles and article_template:
        total_stages += 1

    stage_idx = 1
    dk_props_path = None
    if pga_id:
        dk_props_path = DATA_DIR / "odds" / f"prop_lines_{pga_id}.csv"
        print_stage(stage_idx, total_stages, "Fetch DraftKings props")
        if (not force_dk_props_refresh) and check_file_fresh(dk_props_path, max_age_hours=dk_props_max_age_hours):
            print(
                f"  Skipping DraftKings props - fresh file exists ({dk_props_path.name}, <= {dk_props_max_age_hours:.1f}h old)"
            )
        else:
            run_command([
                "python3",
                str(SCRIPTS_DIR / "scrapers" / "fetch_draftkings_props.py"),
                "--tournament-id",
                pga_id,
                "--no-snapshot",
                "--fetch-profile",
                "fast",
            ])
        stage_idx += 1

    odds_path = None
    if pga_id:
        odds_path = DATA_DIR / "odds" / f"pga_odds_{pga_id}.csv"
        print_stage(stage_idx, total_stages, "Fetch betting odds")
        if (not force_odds_refresh) and check_file_fresh(odds_path, max_age_hours=odds_max_age_hours):
            print(f"  Skipping odds fetch - fresh file exists ({odds_path.name}, <= {odds_max_age_hours:.1f}h old)")
        else:
            run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_pga_odds.py"),
                         "--tournament-id", pga_id,
                         "--output", str(odds_path)])
        stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch betting profiles")
    bp_out = DATA_DIR / "betting_profiles" / f"betting_profiles_{pga_id}.csv"
    bp_cmd = [
        "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_betting_profiles.py"),
        "--tournament-id", pga_id,
        "--field", str(field_path),
        "--output", str(bp_out),
    ]
    if odds_path and odds_path.exists():
        bp_cmd.extend(["--odds-csv", str(odds_path)])
    run_command(bp_cmd)
    stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch power rankings")
    slug = power_slug or slugify(tournament_name)
    run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_power_rankings.py"),
                 "--slug", slug, "--allow-fail"])
    stage_idx += 1

    print_stage(stage_idx, total_stages, "Fetch course characteristics")
    run_command(["python3", str(SCRIPTS_DIR / "scrapers" / "fetch_course_characteristics.py"),
                 "--tournament-id", pga_id, "--profile"])
    stage_idx += 1

    if fetch_expert_picks and pga_id:
        print_stage(stage_idx, total_stages, "Fetch expert picks")
        success = run_command([
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_expert_picks_pga.py"),
            "--tournament-id", pga_id,
        ])
        if not success:
            print("  Warning: expert picks fetch failed, continuing...")
        stage_idx += 1

    if fetch_articles and article_template:
        print_stage(stage_idx, total_stages, "Fetch betting profile articles")
        run_command([
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_betting_profile_articles.py"),
            "--field-csv", str(field_path),
            "--url-template", article_template,
            "--output", str(DATA_DIR / "betting_profiles" / "article_blurbs.csv"),
        ])

    return odds_path


def run_full_pipeline(
    tournament_name: str,
    purse: int,
    field_path: str = None,
    pga_id: str = None,
    tournament_type: str = "Standard",
    skip_refresh: bool = False,
    insights: bool = False,
    insights_ollama: bool = False,
    recommend_lineup: bool = False,
    save_tracking: bool = False,
    power_slug: str = None,
    odds_max_age_hours: float = 6.0,
    force_odds_refresh: bool = False,
    dk_props_max_age_hours: float = 6.0,
    force_dk_props_refresh: bool = False,
    fetch_expert_picks: bool = True,
    fetch_articles: bool = False,
    article_template: str = None,
    calibrate: bool = False,
    generate_bet_recs: bool = True,
):
    """Run the full prediction pipeline."""
    print_header(f"GOLF PREDICTION PIPELINE: {tournament_name}", "=")
    print(f"  Purse: ${purse:,}")
    print(f"  Type: {tournament_type}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Stage 1: Data refresh
    if not skip_refresh:
        refresh_data(force=False, max_age_hours=24)
    else:
        print("\n  Skipping data refresh (--skip-refresh)")

    # Stage 2: Get field
    print_header("TOURNAMENT FIELD")

    if field_path:
        field_file = Path(field_path)
        if not field_file.exists():
            print(f"  Error: Field file not found: {field_path}")
            return
        print(f"  Using provided field: {field_file}")
    else:
        # Try to find existing field file (canonical ID lookup first, then fuzzy name)
        field_file = find_field_file(tournament_name, tournament_id=pga_id)

        if field_file:
            print(f"  Found existing field: {field_file}")
        elif pga_id:
            # Try to fetch from PGA TOUR
            field_file = fetch_field_from_pga(tournament_name, pga_id)

    if not field_file:
        print("\n  No field file found!")
        print("  Please provide one with --field or --pga-id")
        print("\n  Example:")
        print(f"    python scripts/run_pipeline.py --tournament \"{tournament_name}\" \\")
        print(f"        --purse {purse} --field data/fields/your_field.csv")
        return

    # Stage 2b: Fetch tournament assets (odds, profiles, rankings)
    odds_path = None
    if pga_id:
        odds_path = fetch_tournament_assets(
            tournament_name=tournament_name,
            pga_id=pga_id,
            field_path=field_file,
            power_slug=power_slug,
            odds_max_age_hours=odds_max_age_hours,
            force_odds_refresh=force_odds_refresh,
            dk_props_max_age_hours=dk_props_max_age_hours,
            force_dk_props_refresh=force_dk_props_refresh,
            fetch_expert_picks=fetch_expert_picks,
            fetch_articles=fetch_articles,
            article_template=article_template,
        )

    # Stage 3: Run predictions
    predictions_path = run_predictions(
        tournament_name=tournament_name,
        purse=purse,
        field_path=field_file,
        tournament_type=tournament_type,
        insights=insights,
        insights_ollama=insights_ollama,
        save_tracking=save_tracking,
        odds_path=odds_path,
        calibrate=calibrate,
    )

    # Stage 4: Deterministic tracked bet recommendations.
    if generate_bet_recs and predictions_path and pga_id:
        run_bet_recommendations(pga_id, predictions_path=predictions_path)

    # Stage 5: Lineup recommendation (if requested separately)
    if recommend_lineup and predictions_path:
        run_lineup_recommendation(tournament_name, predictions_path)

    print_header("PIPELINE COMPLETE", "=")


def weekly_refresh():
    """Run weekly data refresh for all sources."""
    print_header("WEEKLY DATA REFRESH")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Force refresh all data
    refresh_data(force=True)

    # Update player database
    print("\n  Updating master player database...")
    script_path = SCRIPTS_DIR / "scrapers" / "fetch_player_database.py"
    if script_path.exists():
        run_command(["python3", str(script_path)])

    print_header("WEEKLY REFRESH COMPLETE")


def main():
    parser = argparse.ArgumentParser(
        description='Golf Prediction Pipeline Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic prediction
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000

  # With existing field file
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
      --field data/fields/masters_2026.csv

  # Full pipeline with insights and lineup
  python scripts/run_pipeline.py --tournament "The Masters" --purse 20000000 \\
      --insights-ollama --lineup

  # Skip data refresh (use cached)
  python scripts/run_pipeline.py --tournament "Phoenix Open" --purse 9600000 \\
      --skip-refresh

  # Weekly refresh only (no predictions)
  python scripts/run_pipeline.py --weekly-refresh
        """
    )

    # Tournament options
    parser.add_argument('--tournament', '-t', help='Tournament name')
    parser.add_argument('--purse', '-p', type=int, help='Tournament purse in dollars')
    parser.add_argument('--tournament-type', default='Standard',
                       choices=['Standard', 'Signature', 'Major', 'Playoff'],
                       help='Tournament type (default: Standard)')
    parser.add_argument('--use-schedule', action='store_true',
                       help='Override purse/type using data/raw/schedule_2026.csv')
    parser.add_argument('--schedule-path', type=str, default=str(SCHEDULE_PATH),
                       help='Schedule CSV path (default: data/raw/schedule_2026.csv)')
    parser.add_argument('--auto-weekly', action='store_true',
                       help='Auto-pick current week tournament from schedule and run pipeline')

    # Field options
    parser.add_argument('--field', '-f', help='Path to field CSV file')
    parser.add_argument('--pga-id', help='PGA TOUR tournament ID to fetch field')
    parser.add_argument('--power-slug', help='Power rankings slug (from data/power_rankings/paths.csv)')
    parser.add_argument('--odds-max-age-hours', type=float, default=6.0,
                       help='Skip PGA odds refresh if existing odds file is newer than this many hours (default: 6)')
    parser.add_argument('--force-odds-refresh', action='store_true',
                       help='Force PGA odds refresh even if cached odds are fresh')
    parser.add_argument('--dk-max-age-hours', type=float, default=6.0,
                       help='Skip DraftKings props refresh if existing props file is newer than this many hours (default: 6)')
    parser.add_argument('--force-dk-refresh', action='store_true',
                       help='Force DraftKings props refresh even if cached props are fresh')
    parser.add_argument('--skip-expert-picks', action='store_true',
                       help='Skip expert picks fetch in tournament assets stage')
    parser.add_argument('--skip-bet-recs', action='store_true',
                       help='Skip deterministic bet recommendation generation after predictions')
    parser.add_argument('--fetch-articles', action='store_true',
                       help='Fetch betting profile articles (requires --article-template)')
    parser.add_argument('--article-template', help='URL template for betting profile articles (with {name_slug})')

    # Pipeline control
    parser.add_argument('--skip-refresh', action='store_true',
                       help='Skip data refresh, use cached data')
    parser.add_argument('--refresh-only', action='store_true',
                       help='Only refresh data, no predictions')
    parser.add_argument('--weekly-refresh', action='store_true',
                       help='Run weekly data refresh')

    # Output options
    parser.add_argument('--insights', action='store_true',
                       help='Generate rule-based insights')
    parser.add_argument('--insights-ollama', action='store_true',
                       help='Generate LLM insights via Ollama')
    parser.add_argument('--lineup', action='store_true',
                       help='Generate strategic lineup recommendation')
    parser.add_argument('--save-tracking', action='store_true',
                       help='Save predictions to tracking system')
    parser.add_argument('--calibrate', action='store_true',
                       help='Apply probability calibration factors')

    args = parser.parse_args()

    # Ensure we're in the project directory
    os.chdir(PROJECT_ROOT)

    # Weekly refresh mode
    if args.weekly_refresh:
        weekly_refresh()
        return

    # Auto weekly pipeline from schedule
    if args.auto_weekly:
        row = find_schedule_row(on_date=datetime.now().strftime("%Y-%m-%d"),
                                schedule_path=Path(args.schedule_path))
        if not row:
            print("Error: Could not find a tournament for the current date in schedule.")
            return
        args.tournament = row.get("tournament_name")
        args.purse = int(row.get("purse") or 0)
        if row.get("tournament_type"):
            args.tournament_type = str(row.get("tournament_type")).title()
        if row.get("tournament_id"):
            args.pga_id = str(row.get("tournament_id"))
        if row.get("power_slug") and not args.power_slug:
            args.power_slug = str(row.get("power_slug"))


    # If schedule override requested (or purse missing), fill from schedule
    if (args.use_schedule or args.purse is None) and args.tournament:
        row = find_schedule_row(tournament_name=args.tournament,
                                schedule_path=Path(args.schedule_path))
        if row:
            if args.purse is None or args.use_schedule:
                args.purse = int(row.get("purse") or 0)
            if args.use_schedule and row.get("tournament_type"):
                args.tournament_type = str(row.get("tournament_type")).title()
            if args.use_schedule and row.get("tournament_id") and not args.pga_id:
                args.pga_id = str(row.get("tournament_id"))
            if args.use_schedule and row.get("power_slug") and not args.power_slug:
                args.power_slug = str(row.get("power_slug"))
        else:
            print("Warning: tournament not found in schedule; using provided values.")

    # Refresh only mode
    if args.refresh_only:
        refresh_data(force=True)
        return

    # Require tournament and purse for predictions
    if not args.tournament or not args.purse:
        parser.print_help()
        print("\nError: --tournament and --purse are required for predictions")
        print("\nOr use --weekly-refresh for data updates only")
        return

    # Run full pipeline
    run_full_pipeline(
        tournament_name=args.tournament,
        purse=args.purse,
        field_path=args.field,
        pga_id=args.pga_id,
        tournament_type=args.tournament_type,
        skip_refresh=args.skip_refresh,
        insights=args.insights,
        insights_ollama=args.insights_ollama,
        recommend_lineup=args.lineup,
        save_tracking=args.save_tracking,
        power_slug=args.power_slug,
        odds_max_age_hours=args.odds_max_age_hours,
        force_odds_refresh=args.force_odds_refresh,
        dk_props_max_age_hours=args.dk_max_age_hours,
        force_dk_props_refresh=args.force_dk_refresh,
        fetch_expert_picks=(not args.skip_expert_picks),
        generate_bet_recs=(not args.skip_bet_recs),
        fetch_articles=args.fetch_articles,
        article_template=args.article_template,
        calibrate=args.calibrate,
    )


if __name__ == '__main__':
    main()
