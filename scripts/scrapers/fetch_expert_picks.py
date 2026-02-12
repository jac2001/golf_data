#!/usr/bin/env python3
"""
Expert Picks Scraper
====================
Scrapes expert golf picks from various sources for comparison with our model.

Sources:
- CBS Sports / SportsLine
- Action Network
- Golf.com
- Sports Illustrated

Usage:
    python3 fetch_expert_picks.py --tournament "WM Phoenix Open"
    python fetch_expert_picks.py --tournament-id R2026003

Output:
    data/expert_picks/expert_picks_<tournament_id>.csv
"""

import re
import json
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import argparse

# Project paths
PROJECT_ROOT = Path("/Users/jacklegnon/Desktop/golf_data")
DATA_DIR = PROJECT_ROOT / "data"
EXPERT_PICKS_DIR = DATA_DIR / "expert_picks"

# Request headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def normalize_player_name(name: str) -> str:
    """Normalize player name for matching."""
    if not name:
        return ""
    # Remove common suffixes/prefixes
    name = re.sub(r'\s*(Jr\.?|Sr\.?|III|IV|II)\s*$', '', name, flags=re.IGNORECASE)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def scrape_cbs_sports(tournament_name: str) -> List[Dict]:
    """
    Scrape expert picks from CBS Sports.

    CBS Sports publishes detailed expert picks articles with model predictions.
    """
    picks = []

    # CBS Sports article URL pattern
    tournament_slug = tournament_name.lower().replace(" ", "-").replace("'", "")
    tournament_slug = re.sub(r'[^a-z0-9-]', '', tournament_slug)

    urls = [
        f"https://www.cbssports.com/golf/news/{tournament_slug}-odds-predictions-golf-picks-field-projected-leaderboard-bets/",
        f"https://www.cbssports.com/golf/news/2026-{tournament_slug}-odds-predictions-golf-picks-field-projected-leaderboard-bets/",
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for article content
            article = soup.find('article') or soup.find('div', class_='Article-body')
            if not article:
                continue

            text = article.get_text()

            # Extract picks using patterns
            # Pattern: "The model is high on [Player Name]" or "[Player Name] is a top pick"
            patterns = [
                r"(?:model is (?:extremely |very )?high on|backing|likes?|picking)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
                r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+(?:is a|as a)\s+(?:top|strong|solid)\s+(?:pick|bet|play)",
                r"(?:top pick|best bet)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    player = normalize_player_name(match)
                    if len(player.split()) >= 2:  # Must be at least first + last name
                        picks.append({
                            'player_name': player,
                            'source': 'CBS Sports',
                            'pick_type': 'model_pick',
                            'url': url,
                        })

            # Look for "fade" picks
            fade_patterns = [
                r"(?:fading?|avoid(?:ing)?|skip(?:ping)?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
                r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+(?:is a|to)\s+(?:fade|avoid)",
            ]

            for pattern in fade_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    player = normalize_player_name(match)
                    if len(player.split()) >= 2:
                        picks.append({
                            'player_name': player,
                            'source': 'CBS Sports',
                            'pick_type': 'fade',
                            'url': url,
                        })

            if picks:
                print(f"  Found {len(picks)} picks from CBS Sports")
                break

        except Exception as e:
            print(f"  CBS Sports error: {e}")
            continue

    return picks


def scrape_action_network(tournament_name: str) -> List[Dict]:
    """
    Scrape expert picks from Action Network.

    Action Network has "One and Done" picks which are similar to our format.
    """
    picks = []

    tournament_slug = tournament_name.lower().replace(" ", "-").replace("'", "")
    tournament_slug = re.sub(r'[^a-z0-9-]', '', tournament_slug)

    urls = [
        f"https://www.actionnetwork.com/golf/5-best-{tournament_slug}-one-and-done-picks-2026",
        f"https://www.actionnetwork.com/golf/{tournament_slug}-one-and-done-picks-2026",
        f"https://www.actionnetwork.com/golf/best-{tournament_slug}-picks-2026",
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Action Network uses h2/h3 tags for player picks
            headings = soup.find_all(['h2', 'h3'])

            for heading in headings:
                text = heading.get_text().strip()
                # Look for patterns like "1. Scottie Scheffler" or "Scottie Scheffler (+250)"
                match = re.match(r'(?:\d+\.\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:\s*\([+-]?\d+\))?', text)
                if match:
                    player = normalize_player_name(match.group(1))
                    if len(player.split()) >= 2:
                        picks.append({
                            'player_name': player,
                            'source': 'Action Network',
                            'pick_type': 'one_and_done',
                            'url': url,
                        })

            if picks:
                print(f"  Found {len(picks)} picks from Action Network")
                break

        except Exception as e:
            print(f"  Action Network error: {e}")
            continue

    return picks


def scrape_golf_digest(tournament_name: str) -> List[Dict]:
    """
    Scrape expert picks from Golf Digest.

    Golf Digest publishes DFS picks which overlap with fantasy golf.
    """
    picks = []

    tournament_slug = tournament_name.lower().replace(" ", "-").replace("'", "")
    tournament_slug = re.sub(r'[^a-z0-9-]', '', tournament_slug)

    urls = [
        f"https://www.golfdigest.com/story/{tournament_slug}-dfs-picks-2026",
        f"https://www.golfdigest.com/story/{tournament_slug}-picks-2026",
    ]

    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            # Golf Digest uses bold/strong for player names
            article = soup.find('article') or soup.find('div', class_='article-body')
            if not article:
                continue

            # Look for strong/bold tags which often contain player names
            bolds = article.find_all(['strong', 'b'])

            for bold in bolds:
                text = bold.get_text().strip()
                # Check if it looks like a player name (First Last format)
                if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$', text):
                    player = normalize_player_name(text)
                    if len(player.split()) >= 2:
                        picks.append({
                            'player_name': player,
                            'source': 'Golf Digest',
                            'pick_type': 'dfs_pick',
                            'url': url,
                        })

            if picks:
                print(f"  Found {len(picks)} picks from Golf Digest")
                break

        except Exception as e:
            print(f"  Golf Digest error: {e}")
            continue

    return picks


def add_manual_expert_picks(tournament_name: str) -> List[Dict]:
    """
    Add expert picks from web search results that we found.

    These are hard-coded from the search results since some sites
    use JavaScript rendering that's hard to scrape.
    """
    picks = []

    # WM Phoenix Open 2026 picks from web search
    tournament_lower = tournament_name.lower()

    if "phoenix" in tournament_lower or "waste management" in tournament_lower:
        # From CBS Sports / web search results
        expert_data = [
            # Favorites
            {"player": "Scottie Scheffler", "type": "favorite", "source": "Multiple",
             "note": "World #1, won back-to-back 2022-23, won 4 of last 7 starts"},
            {"player": "Hideki Matsuyama", "type": "course_specialist", "source": "CBS Sports",
             "note": "Two-time winner (2016, 2017), top 30 every year since"},
            {"player": "Ben Griffin", "type": "model_pick", "source": "CBS Sports Model",
             "note": "Model extremely high on him, made cut both times (36th, 28th)"},
            {"player": "Xander Schauffele", "type": "favorite", "source": "Odds",
             "note": "Second favorite at +1900"},
            {"player": "Cameron Young", "type": "value_pick", "source": "Odds",
             "note": "+2000 odds, strong ball striker"},

            # Fades
            {"player": "Si Woo Kim", "type": "fade", "source": "CBS Sports",
             "note": "Missed 3 of past 5 cuts here despite hot start to season"},
            {"player": "J.J. Spaun", "type": "fade", "source": "Brady Kannon",
             "note": "40th and MC in two starts, 2 WDs and 2 MCs in 7 trips to TPC Scottsdale"},
        ]

        for pick in expert_data:
            picks.append({
                'player_name': pick['player'],
                'source': pick['source'],
                'pick_type': pick['type'],
                'note': pick.get('note', ''),
                'url': 'web_search_aggregated',
            })

        print(f"  Added {len(picks)} manual expert picks for WM Phoenix Open")

    return picks


def fetch_expert_picks(
    tournament_name: str,
    tournament_id: str = None,
    save: bool = True
) -> pd.DataFrame:
    """
    Fetch expert picks from all sources.

    Args:
        tournament_name: Tournament name (e.g., "WM Phoenix Open")
        tournament_id: Optional tournament ID for file naming
        save: Whether to save to CSV

    Returns:
        DataFrame with expert picks
    """
    print(f"\n{'='*60}")
    print(f"  FETCHING EXPERT PICKS: {tournament_name}")
    print(f"{'='*60}")

    all_picks = []

    # Scrape each source
    print("\n  Scraping sources...")

    # CBS Sports
    cbs_picks = scrape_cbs_sports(tournament_name)
    all_picks.extend(cbs_picks)

    # Action Network
    action_picks = scrape_action_network(tournament_name)
    all_picks.extend(action_picks)

    # Golf Digest
    digest_picks = scrape_golf_digest(tournament_name)
    all_picks.extend(digest_picks)

    # Add manual picks from web search
    manual_picks = add_manual_expert_picks(tournament_name)
    all_picks.extend(manual_picks)

    if not all_picks:
        print("\n  No expert picks found!")
        return pd.DataFrame()

    # Create DataFrame
    df = pd.DataFrame(all_picks)
    df['tournament'] = tournament_name
    df['scraped_date'] = datetime.now().isoformat()

    # Deduplicate by player + source
    df = df.drop_duplicates(subset=['player_name', 'source', 'pick_type'])

    # Add consensus scoring
    player_counts = df[df['pick_type'] != 'fade'].groupby('player_name').size()
    df['consensus_count'] = df['player_name'].map(player_counts).fillna(0).astype(int)

    print(f"\n  Summary:")
    print(f"    Total picks: {len(df)}")
    print(f"    Unique players: {df['player_name'].nunique()}")
    print(f"    Sources: {df['source'].nunique()}")

    # Show consensus picks
    consensus = df[df['consensus_count'] >= 2]['player_name'].unique()
    if len(consensus) > 0:
        print(f"\n  Consensus picks (2+ sources):")
        for player in consensus:
            count = player_counts.get(player, 0)
            print(f"    - {player} ({count} sources)")

    # Save
    if save:
        EXPERT_PICKS_DIR.mkdir(parents=True, exist_ok=True)

        if tournament_id:
            filename = f"expert_picks_{tournament_id}.csv"
        else:
            safe_name = re.sub(r'[^a-z0-9]+', '_', tournament_name.lower())
            filename = f"expert_picks_{safe_name}.csv"

        output_path = EXPERT_PICKS_DIR / filename
        df.to_csv(output_path, index=False)
        print(f"\n  Saved to: {output_path}")

        # Also save as "latest" for easy access
        latest_path = EXPERT_PICKS_DIR / "expert_picks_latest.csv"
        df.to_csv(latest_path, index=False)

    return df


def load_expert_picks(tournament_name: str = None) -> pd.DataFrame:
    """
    Load expert picks from saved file.

    Args:
        tournament_name: Tournament to load picks for (None = latest)

    Returns:
        DataFrame with expert picks
    """
    if tournament_name:
        safe_name = re.sub(r'[^a-z0-9]+', '_', tournament_name.lower())
        path = EXPERT_PICKS_DIR / f"expert_picks_{safe_name}.csv"
    else:
        path = EXPERT_PICKS_DIR / "expert_picks_latest.csv"

    if path.exists():
        return pd.read_csv(path)

    return pd.DataFrame()


def compare_with_model(
    expert_picks: pd.DataFrame,
    predictions: pd.DataFrame,
    top_n: int = 15
) -> Dict[str, Any]:
    """
    Compare expert picks with model predictions.

    Args:
        expert_picks: DataFrame with expert picks
        predictions: Model predictions DataFrame
        top_n: Number of top model picks to compare

    Returns:
        Dict with comparison analysis
    """
    if expert_picks.empty or predictions.empty:
        return {"error": "Missing data for comparison"}

    # Normalize player names for matching
    def normalize(name):
        if pd.isna(name):
            return ""
        name = str(name).lower().strip()
        # Handle "Last, First" format
        if ',' in name:
            parts = name.split(',')
            name = f"{parts[1].strip()} {parts[0].strip()}"
        return name

    expert_picks['name_norm'] = expert_picks['player_name'].apply(normalize)
    predictions['name_norm'] = predictions['player_name'].apply(normalize)

    # Get top model picks
    model_top = predictions.nlargest(top_n, 'expected_value')
    model_names = set(model_top['name_norm'].tolist())

    # Get expert picks (excluding fades)
    expert_names = set(expert_picks[expert_picks['pick_type'] != 'fade']['name_norm'].tolist())
    expert_fades = set(expert_picks[expert_picks['pick_type'] == 'fade']['name_norm'].tolist())

    # Find overlaps
    model_agrees = model_names & expert_names
    model_unique = model_names - expert_names
    expert_unique = expert_names - model_names
    model_disagrees = model_names & expert_fades  # Model likes, experts fade

    # Build detailed comparison
    comparison = {
        "model_agrees_with_experts": [],
        "model_unique_picks": [],
        "expert_unique_picks": [],
        "disagreements": [],  # Model likes but experts fade
    }

    for name in model_agrees:
        player_row = model_top[model_top['name_norm'] == name].iloc[0]
        comparison["model_agrees_with_experts"].append({
            "player": player_row['player_name'],
            "model_ev": player_row.get('expected_value', 0),
            "model_rank": model_top[model_top['name_norm'] == name].index[0] + 1,
        })

    for name in model_unique:
        player_row = model_top[model_top['name_norm'] == name].iloc[0]
        comparison["model_unique_picks"].append({
            "player": player_row['player_name'],
            "model_ev": player_row.get('expected_value', 0),
        })

    for name in expert_unique:
        expert_row = expert_picks[expert_picks['name_norm'] == name].iloc[0]
        comparison["expert_unique_picks"].append({
            "player": expert_row['player_name'],
            "source": expert_row.get('source', 'Unknown'),
        })

    for name in model_disagrees:
        player_row = model_top[model_top['name_norm'] == name].iloc[0]
        fade_row = expert_picks[(expert_picks['name_norm'] == name) & (expert_picks['pick_type'] == 'fade')].iloc[0]
        comparison["disagreements"].append({
            "player": player_row['player_name'],
            "model_ev": player_row.get('expected_value', 0),
            "fade_source": fade_row.get('source', 'Unknown'),
            "fade_reason": fade_row.get('note', ''),
        })

    comparison["summary"] = {
        "total_model_picks": len(model_names),
        "total_expert_picks": len(expert_names),
        "agreement_count": len(model_agrees),
        "agreement_pct": len(model_agrees) / len(model_names) * 100 if model_names else 0,
        "disagreement_count": len(model_disagrees),
    }

    return comparison


def main():
    parser = argparse.ArgumentParser(description="Fetch expert golf picks")
    parser.add_argument("--tournament", "-t", required=True, help="Tournament name")
    parser.add_argument("--tournament-id", help="Tournament ID for file naming")
    parser.add_argument("--compare", action="store_true", help="Compare with model predictions")
    parser.add_argument("--predictions", help="Path to predictions CSV for comparison")

    args = parser.parse_args()

    # Fetch expert picks
    expert_df = fetch_expert_picks(
        args.tournament,
        tournament_id=args.tournament_id
    )

    # Compare with model if requested
    if args.compare and not expert_df.empty:
        pred_path = args.predictions or (PROJECT_ROOT / "outputs" / "latest_predictions.csv")
        if Path(pred_path).exists():
            predictions = pd.read_csv(pred_path)
            comparison = compare_with_model(expert_df, predictions)

            print(f"\n{'='*60}")
            print("  MODEL VS EXPERT COMPARISON")
            print(f"{'='*60}")

            summary = comparison.get("summary", {})
            print(f"\n  Agreement: {summary.get('agreement_count', 0)}/{summary.get('total_model_picks', 0)} ({summary.get('agreement_pct', 0):.1f}%)")

            if comparison.get("model_agrees_with_experts"):
                print("\n  Model agrees with experts:")
                for p in comparison["model_agrees_with_experts"]:
                    print(f"    - {p['player']} (EV: ${p['model_ev']:,.0f})")

            if comparison.get("disagreements"):
                print("\n  ⚠️ Model likes, experts fade:")
                for p in comparison["disagreements"]:
                    print(f"    - {p['player']} (EV: ${p['model_ev']:,.0f})")
                    print(f"      Fade reason: {p.get('fade_reason', 'N/A')}")

            if comparison.get("model_unique_picks"):
                print("\n  Model-only picks (not in expert picks):")
                for p in comparison["model_unique_picks"][:5]:
                    print(f"    - {p['player']} (EV: ${p['model_ev']:,.0f})")


if __name__ == "__main__":
    main()
