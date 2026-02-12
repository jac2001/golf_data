#!/usr/bin/env python3
"""
Weekly Tournament Workflow - Automated Pipeline
================================================

Runs the complete weekly workflow:
1. Identify current/upcoming tournament from calendar
2. Fetch tournament field from PGA Tour
3. Fetch betting profiles with SG data
4. Run predictions
5. Fetch PGA Tour expert picks
6. Generate comprehensive picks report

Usage:
    # Auto-detect current tournament
    python run_weekly_workflow.py

    # Specify tournament
    python run_weekly_workflow.py --tournament "WM Phoenix Open"

    # Specify PGA Tour ID
    python run_weekly_workflow.py --tournament-id R2026005
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Tuple
import pandas as pd
import json

PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# 2026 Tournament Calendar with PGA Tour IDs
TOURNAMENT_CALENDAR_2026 = [
    {"name": "The Sentry", "id": "R2026016", "start": "2026-01-02", "purse": 20000000, "type": "Signature"},
    {"name": "Sony Open in Hawaii", "id": "R2026006", "start": "2026-01-09", "purse": 8900000, "type": "Standard"},
    {"name": "The American Express", "id": "R2026002", "start": "2026-01-16", "purse": 8800000, "type": "Standard"},
    {"name": "Farmers Insurance Open", "id": "R2026004", "start": "2026-01-22", "purse": 9500000, "type": "Standard"},
    {"name": "AT&T Pebble Beach Pro-Am", "id": "R2026005", "start": "2026-01-30", "purse": 20000000, "type": "Signature"},
    {"name": "WM Phoenix Open", "id": "R2026003", "start": "2026-02-06", "purse": 20000000, "type": "Signature", "field_pattern": "phoenix"},
    {"name": "The Genesis Invitational", "id": "R2026007", "start": "2026-02-13", "purse": 20000000, "type": "Signature"},
    {"name": "Mexico Open at Vidanta", "id": "R2026540", "start": "2026-02-20", "purse": 9200000, "type": "Standard"},
    {"name": "Cognizant Classic", "id": "R2026010", "start": "2026-02-27", "purse": 9000000, "type": "Standard"},
    {"name": "Arnold Palmer Invitational", "id": "R2026009", "start": "2026-03-06", "purse": 20000000, "type": "Signature"},
    {"name": "THE PLAYERS Championship", "id": "R2026011", "start": "2026-03-12", "purse": 25000000, "type": "Signature"},
    {"name": "Valspar Championship", "id": "R2026475", "start": "2026-03-19", "purse": 8400000, "type": "Standard"},
    {"name": "Texas Children's Houston Open", "id": "R2026020", "start": "2026-03-26", "purse": 9400000, "type": "Standard"},
    {"name": "Valero Texas Open", "id": "R2026041", "start": "2026-04-02", "purse": 9200000, "type": "Standard"},
    {"name": "RBC Heritage", "id": "R2026012", "start": "2026-04-16", "purse": 20000000, "type": "Signature"},
]


def log(msg: str, level: str = "INFO"):
    """Print formatted log message."""
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",   # Red
        "STEP": "\033[95m",    # Magenta
    }
    reset = "\033[0m"
    timestamp = datetime.now().strftime("%H:%M:%S")
    color = colors.get(level, "")
    print(f"{color}[{timestamp}] {level}: {msg}{reset}")


def get_current_tournament() -> Optional[Dict]:
    """Get the current or upcoming tournament from calendar."""
    today = datetime.now().date()

    for tourney in TOURNAMENT_CALENDAR_2026:
        start = datetime.strptime(tourney["start"], "%Y-%m-%d").date()
        end = start + timedelta(days=6)  # Tournaments run ~4 days but include practice

        # If we're within the tournament week (including 2 days before for prep)
        if start - timedelta(days=2) <= today <= end:
            return tourney

    # Find next upcoming tournament
    for tourney in TOURNAMENT_CALENDAR_2026:
        start = datetime.strptime(tourney["start"], "%Y-%m-%d").date()
        if start > today:
            return tourney

    return None


def find_tournament_by_name(name: str) -> Optional[Dict]:
    """Find tournament by partial name match."""
    name_lower = name.lower()
    for tourney in TOURNAMENT_CALENDAR_2026:
        if name_lower in tourney["name"].lower():
            return tourney
    return None


def find_tournament_by_id(tid: str) -> Optional[Dict]:
    """Find tournament by PGA Tour ID."""
    for tourney in TOURNAMENT_CALENDAR_2026:
        if tourney["id"] == tid:
            return tourney
    return None


def run_command(cmd: list, description: str, check: bool = True) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    log(f"Running: {' '.join(cmd)}", "INFO")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            check=check
        )
        return True, result.stdout + result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout + e.stderr
    except Exception as e:
        return False, str(e)


def step_fetch_field(tournament: Dict) -> Tuple[bool, Path]:
    """Step 1: Fetch tournament field from PGA Tour."""
    log("STEP 1: Fetching Tournament Field", "STEP")

    safe_name = tournament["name"].lower().replace(" ", "_").replace("'", "")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
    field_path = DATA_DIR / "fields" / f"{safe_name}_field.csv"

    # Check for existing field files with different naming conventions
    fields_dir = DATA_DIR / "fields"
    search_pattern = tournament.get("field_pattern", safe_name.split("_")[0])
    for f in fields_dir.glob("*.csv"):
        fname_lower = f.name.lower()
        if search_pattern in fname_lower and ("field" in fname_lower or f.name.endswith("_field.csv")):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if datetime.now() - mtime < timedelta(hours=48):
                log(f"Found existing field: {f.name}", "INFO")
                return True, f

    # Check if recent field exists (within 24 hours)
    if field_path.exists():
        mtime = datetime.fromtimestamp(field_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=24):
            log(f"Using cached field from {mtime.strftime('%Y-%m-%d %H:%M')}", "INFO")
            return True, field_path

    # Fetch from PGA Tour
    cmd = [
        "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_field_from_pgatour.py"),
        "--pga-id", tournament["id"],
        "--name", tournament["name"],
        "--output", str(field_path),
        "--match-ids"
    ]

    success, output = run_command(cmd, "Fetch field")
    if success:
        log(f"Field saved to {field_path}", "SUCCESS")
    else:
        log(f"Failed to fetch field: {output}", "ERROR")

    return success, field_path


def step_fetch_betting_profiles(tournament: Dict, field_path: Path) -> Tuple[bool, Path]:
    """Step 2: Fetch betting profiles with SG data."""
    log("STEP 2: Fetching Betting Profiles", "STEP")

    profiles_path = DATA_DIR / "betting_profiles" / f"betting_profiles_{tournament['id']}.csv"

    # Check if recent profiles exist
    if profiles_path.exists():
        mtime = datetime.fromtimestamp(profiles_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=12):
            log(f"Using cached betting profiles from {mtime.strftime('%Y-%m-%d %H:%M')}", "INFO")
            return True, profiles_path

    cmd = [
        "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_betting_profiles.py"),
        "--tournament-id", tournament["id"],
        "--field", str(field_path)
    ]

    success, output = run_command(cmd, "Fetch betting profiles", check=False)
    if profiles_path.exists():
        log(f"Betting profiles saved to {profiles_path}", "SUCCESS")
        return True, profiles_path
    else:
        log("Betting profiles fetch failed or no data available", "WARNING")
        return False, profiles_path


def step_run_predictions(tournament: Dict, field_path: Path) -> Tuple[bool, Path]:
    """Step 3: Run predictions."""
    log("STEP 3: Running Predictions", "STEP")

    safe_name = tournament["name"].lower().replace(" ", "_").replace("'", "")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
    predictions_path = OUTPUTS_DIR / f"{safe_name}_predictions.csv"

    cmd = [
        "python3", str(SCRIPTS_DIR / "predictions" / "predict_tournament.py"),
        "--tournament", tournament["name"],
        "--purse", str(tournament["purse"]),
        "--field", str(field_path),
        "--tournament-type", tournament["type"],
        "--output", str(predictions_path)
    ]

    success, output = run_command(cmd, "Run predictions")
    if success and predictions_path.exists():
        log(f"Predictions saved to {predictions_path}", "SUCCESS")

        # Also create latest_predictions.csv symlink/copy
        latest_path = OUTPUTS_DIR / "latest_predictions.csv"
        try:
            df = pd.read_csv(predictions_path)
            df.to_csv(latest_path, index=False)
            log(f"Updated latest_predictions.csv", "INFO")
        except Exception as e:
            log(f"Could not update latest_predictions.csv: {e}", "WARNING")
    else:
        log(f"Predictions failed: {output}", "ERROR")

    return success, predictions_path


def step_fetch_expert_picks(tournament: Dict, article_path: Optional[str] = None) -> Tuple[bool, Path]:
    """Step 4: Fetch PGA Tour expert picks."""
    log("STEP 4: Fetching PGA Tour Expert Picks", "STEP")

    expert_path = DATA_DIR / "expert_picks" / "expert_picks_ep_table.csv"

    # Try to find the expert picks article path
    # This typically follows a pattern like /content/dam/pgatour/editorial/.../ep-table
    # For now, we'll check if we have a recent file

    if expert_path.exists():
        mtime = datetime.fromtimestamp(expert_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=24):
            log(f"Using cached expert picks from {mtime.strftime('%Y-%m-%d %H:%M')}", "INFO")
            return True, expert_path

    # If no article path provided, try common patterns
    if not article_path:
        # Check if we have paths.csv with article paths
        paths_file = DATA_DIR / "betting_profiles" / "paths.csv"
        if paths_file.exists():
            try:
                paths_df = pd.read_csv(paths_file)
                # Look for expert picks path
                ep_rows = paths_df[paths_df["fragment_path"].str.contains("ep-table", na=False)]
                if not ep_rows.empty:
                    article_path = ep_rows.iloc[0]["fragment_path"]
                    log(f"Found expert picks path: {article_path}", "INFO")
            except Exception:
                pass

    if article_path:
        cmd = [
            "python3", str(SCRIPTS_DIR / "scrapers" / "fetch_expert_picks_pga.py"),
            "--path", article_path,
            "--output", str(expert_path)
        ]

        success, output = run_command(cmd, "Fetch expert picks", check=False)
        if expert_path.exists():
            log(f"Expert picks saved to {expert_path}", "SUCCESS")
            return True, expert_path

    log("Expert picks not available (no article path found)", "WARNING")
    return False, expert_path


def step_generate_report(tournament: Dict, predictions_path: Path) -> Tuple[bool, Path]:
    """Step 5: Generate comprehensive picks report using golf assistant."""
    log("STEP 5: Generating Picks Report", "STEP")

    safe_name = tournament["name"].lower().replace(" ", "_").replace("'", "")
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
    report_path = OUTPUTS_DIR / f"{safe_name}_weekly_report.md"

    # Load predictions
    try:
        df = pd.read_csv(predictions_path)
    except Exception as e:
        log(f"Could not load predictions: {e}", "ERROR")
        return False, report_path

    # Generate report
    report = []
    report.append(f"# {tournament['name']} - Weekly Picks Report")
    report.append(f"\n**Generated**: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    report.append(f"**Tournament Type**: {tournament['type']}")
    report.append(f"**Purse**: ${tournament['purse']:,}")
    report.append(f"**Field Size**: {len(df)} players")
    report.append("")

    # Top 10 by EV
    report.append("## 🏆 TOP 10 PICKS BY EXPECTED VALUE")
    report.append("")
    report.append("| Rank | Player | EV | Win % | Top-5 % | Top-10 % | World Rank |")
    report.append("|------|--------|-----|-------|---------|----------|------------|")

    top10 = df.nlargest(10, "expected_value")
    for idx, (_, row) in enumerate(top10.iterrows(), 1):
        name = row.get("player_name", "Unknown")
        ev = row.get("expected_value", 0)
        win = row.get("win_prob", 0) * 100
        top5 = row.get("top5_prob", 0) * 100
        top10_prob = row.get("top10_prob", 0) * 100
        wr = int(row.get("world_rank", 999)) if pd.notna(row.get("world_rank")) else "N/A"
        report.append(f"| {idx} | {name} | ${ev:,.0f} | {win:.1f}% | {top5:.1f}% | {top10_prob:.1f}% | #{wr} |")

    report.append("")

    # Value plays (high EV relative to world rank)
    report.append("## 💎 VALUE PLAYS")
    report.append("*Players with high EV relative to world ranking*")
    report.append("")

    df_with_value = df.copy()
    df_with_value["value_score"] = df_with_value["expected_value"] / (df_with_value["world_rank"].clip(lower=1) ** 0.5)
    value_plays = df_with_value[df_with_value["world_rank"] > 30].nlargest(5, "value_score")

    for _, row in value_plays.iterrows():
        name = row.get("player_name", "Unknown")
        ev = row.get("expected_value", 0)
        wr = int(row.get("world_rank", 999))
        report.append(f"- **{name}** (#{wr}) - EV: ${ev:,.0f}")

    report.append("")

    # Load and add expert picks summary
    expert_path = DATA_DIR / "expert_picks" / "expert_picks_ep_table.csv"
    if expert_path.exists():
        try:
            expert_df = pd.read_csv(expert_path)
            report.append("## 📰 PGA TOUR EXPERT PICKS")
            report.append(f"*Based on {len(expert_df)} PGA Tour experts*")
            report.append("")

            # Count winner picks
            winner_counts = {}
            for _, row in expert_df.iterrows():
                winner = row.get("winner_name", "")
                if winner:
                    winner_counts[winner] = winner_counts.get(winner, 0) + 1

            if winner_counts:
                report.append("**Winner Picks:**")
                sorted_winners = sorted(winner_counts.items(), key=lambda x: x[1], reverse=True)
                for player, count in sorted_winners[:5]:
                    pct = count / len(expert_df) * 100
                    report.append(f"- {player}: {count}/{len(expert_df)} ({pct:.0f}%)")
                report.append("")
        except Exception as e:
            log(f"Could not load expert picks: {e}", "WARNING")

    # Load and add expert fades
    latest_picks = DATA_DIR / "expert_picks" / "expert_picks_latest.csv"
    if latest_picks.exists():
        try:
            picks_df = pd.read_csv(latest_picks)
            fades = picks_df[picks_df["pick_type"] == "fade"]
            if not fades.empty:
                report.append("## ⚠️ EXPERT FADES (AVOID)")
                report.append("")
                for _, row in fades.iterrows():
                    name = row.get("player_name", "Unknown")
                    note = row.get("note", "")
                    source = row.get("source", "")
                    report.append(f"- **{name}** ({source}): {note}")
                report.append("")
        except Exception:
            pass

    # Strategy notes
    report.append("## 🎯 STRATEGY NOTES")
    report.append("")
    report.append(f"### Tournament Type: {tournament['type']}")

    if tournament["type"] == "Major":
        report.append("- **High stakes** - Consider saving elite player uses for this event")
        report.append("- **Course demands precision** - Look for players with strong SG: Approach")
        report.append("- **Experience matters** - Weight course history heavily")
    elif tournament["type"] == "Signature":
        report.append("- **Strong field** - Elite players are must-plays")
        report.append("- **Good value event** - Worth using top picks here")
        report.append("- **High purse** - EV calculations favor aggressive plays")
    else:
        report.append("- **Standard event** - Good opportunity for mid-tier value plays")
        report.append("- **Consider saving elite uses** for Signature/Major events")
        report.append("- **Course specialists** can provide edge over favorites")

    report.append("")
    report.append("---")
    report.append(f"*Generated by weekly workflow - {datetime.now().isoformat()}*")

    # Write report
    try:
        with open(report_path, "w") as f:
            f.write("\n".join(report))
        log(f"Report saved to {report_path}", "SUCCESS")
        return True, report_path
    except Exception as e:
        log(f"Could not write report: {e}", "ERROR")
        return False, report_path


def print_summary(tournament: Dict, predictions_path: Path):
    """Print workflow summary with top picks."""
    print("\n" + "=" * 70)
    print("  WORKFLOW COMPLETE - TOP PICKS SUMMARY")
    print("=" * 70)
    print(f"\n  Tournament: {tournament['name']}")
    print(f"  Type: {tournament['type']} | Purse: ${tournament['purse']:,}")
    print("")

    try:
        df = pd.read_csv(predictions_path)
        top5 = df.nlargest(5, "expected_value")

        print("  YOUR TOP 5 PICKS:")
        print("  " + "-" * 60)
        for idx, (_, row) in enumerate(top5.iterrows(), 1):
            name = row.get("player_name", "Unknown")
            ev = row.get("expected_value", 0)
            win = row.get("win_prob", 0) * 100
            print(f"  {idx}. {name:<25} EV: ${ev:>8,.0f}  Win: {win:>5.1f}%")
        print("")
    except Exception as e:
        log(f"Could not print summary: {e}", "WARNING")

    print("  NEXT STEPS:")
    print("  1. Review detailed report in outputs/")
    print("  2. Use golf_assistant.py for player analysis")
    print("  3. Make your picks before tournament starts")
    print("")
    print("  Quick commands:")
    print(f'  python scripts/predictions/golf_assistant.py -q "What are the expert picks?" --no-llm')
    print(f'  python scripts/predictions/golf_assistant.py -q "Tell me about [player]" --no-llm')
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run weekly tournament prediction workflow")
    parser.add_argument("--tournament", "-t", help="Tournament name (partial match)")
    parser.add_argument("--tournament-id", help="PGA Tour tournament ID (e.g., R2026005)")
    parser.add_argument("--expert-path", help="Path to expert picks article (GraphQL fragment)")
    parser.add_argument("--skip-field", action="store_true", help="Skip field fetch (use cached)")
    parser.add_argument("--skip-profiles", action="store_true", help="Skip betting profiles fetch")
    parser.add_argument("--skip-experts", action="store_true", help="Skip expert picks fetch")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  WEEKLY TOURNAMENT WORKFLOW")
    print("=" * 70 + "\n")

    # Find tournament
    tournament = None
    if args.tournament_id:
        tournament = find_tournament_by_id(args.tournament_id)
        if not tournament:
            log(f"Tournament ID {args.tournament_id} not found in calendar", "ERROR")
            sys.exit(1)
    elif args.tournament:
        tournament = find_tournament_by_name(args.tournament)
        if not tournament:
            log(f"Tournament '{args.tournament}' not found in calendar", "ERROR")
            sys.exit(1)
    else:
        tournament = get_current_tournament()
        if not tournament:
            log("Could not determine current tournament", "ERROR")
            sys.exit(1)

    log(f"Tournament: {tournament['name']}", "INFO")
    log(f"ID: {tournament['id']} | Type: {tournament['type']} | Purse: ${tournament['purse']:,}", "INFO")
    print("")

    # Step 1: Fetch field
    if args.skip_field:
        safe_name = tournament["name"].lower().replace(" ", "_").replace("'", "")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
        field_path = DATA_DIR / "fields" / f"{safe_name}_field.csv"
        if not field_path.exists():
            log("No cached field found, fetching...", "WARNING")
            success, field_path = step_fetch_field(tournament)
        else:
            log(f"Using cached field: {field_path}", "INFO")
            success = True
    else:
        success, field_path = step_fetch_field(tournament)

    if not success or not field_path.exists():
        log("Cannot proceed without field data", "ERROR")
        sys.exit(1)
    print("")

    # Step 2: Fetch betting profiles
    if not args.skip_profiles:
        step_fetch_betting_profiles(tournament, field_path)
    print("")

    # Step 3: Run predictions
    success, predictions_path = step_run_predictions(tournament, field_path)
    if not success:
        log("Predictions failed, cannot continue", "ERROR")
        sys.exit(1)
    print("")

    # Step 4: Fetch expert picks
    if not args.skip_experts:
        step_fetch_expert_picks(tournament, args.expert_path)
    print("")

    # Step 5: Generate report
    step_generate_report(tournament, predictions_path)
    print("")

    # Print summary
    print_summary(tournament, predictions_path)


if __name__ == "__main__":
    main()
