#!/usr/bin/env python3
"""
Course Fit Analyzer
===================
Shows how a player's skills match different course types.

Usage:
    python course_fit.py "Scottie Scheffler"              # Player's course fit profile
    python course_fit.py --course "TPC Scottsdale"        # Course requirements
    python course_fit.py "Scottie Scheffler" --this-week  # Fit for current tournament
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent.parent / "data"
COURSE_SG_FILE = DATA_DIR / "course_sg_weights.csv"
SCHEDULE_FILE = DATA_DIR / "raw" / "schedule_2026.csv"
COURSE_TOUGHNESS_FILE = DATA_DIR / "reference" / "course_toughness_latest.csv"


def load_course_profiles() -> pd.DataFrame:
    """Load course SG weight profiles."""
    if COURSE_SG_FILE.exists():
        return pd.read_csv(COURSE_SG_FILE)
    return pd.DataFrame()



def load_course_toughness() -> pd.DataFrame:
    """Load course toughness data."""
    if COURSE_TOUGHNESS_FILE.exists():
        return pd.read_csv(COURSE_TOUGHNESS_FILE)
    return pd.DataFrame()










def load_player_sg() -> pd.DataFrame:
    """Load player strokes gained data."""
    years = [2024, 2025, 2026]
    dfs = []
    for year in years:
        path = DATA_DIR / "historical" / f"tournament_stats_{year}.csv"
        if path.exists():
            dfs.append(pd.read_csv(path))
    
    if not dfs:
        return pd.DataFrame()
    
    df = pd.concat(dfs, ignore_index=True)
    
    sg_stats = [
        "Strokes Gained: Total",
        "Strokes Gained: Off-the-Tee",
        "Strokes Gained: Approach",
        "Strokes Gained: Putting"
    ]
    
    df = df[
        (df["stat_name"].isin(sg_stats)) &
        (df["stat_component"] == "Avg")
    ].copy()
    
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")
    return df


def get_current_tournament() -> str:
    """Get current tournament name."""
    if not SCHEDULE_FILE.exists():
        return None
    
    schedule = pd.read_csv(SCHEDULE_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    
    upcoming = schedule[schedule['start_date'] >= today]
    if not upcoming.empty:
        return upcoming.iloc[0]['tournament_name']
    
    return None


def get_player_sg_profile(name: str, sg_df: pd.DataFrame) -> dict:
    """Get player's SG breakdown."""
    player_data = sg_df[sg_df["player_name"].str.lower().str.contains(name.lower(), na=False)]
    
    if player_data.empty:
        return {}
    
    profile = {}
    stat_map = {
        "Strokes Gained: Total": "total",
        "Strokes Gained: Off-the-Tee": "ott",
        "Strokes Gained: Approach": "app",
        "Strokes Gained: Putting": "putt"
    }
    
    for stat_name, key in stat_map.items():
        stat_data = player_data[player_data["stat_name"] == stat_name]
        if not stat_data.empty:
            profile[key] = stat_data["stat_value"].mean()
    
    return profile


def categorize_course(row) -> tuple:
    """Categorize a course by its primary SG emphasis using absolute values."""
    ott = abs(row.get('ott_sg', 0))
    app = abs(row.get('app_sg', 0))
    arg = abs(row.get('arg_sg', 0))
    putt = abs(row.get('putt_sg', 0))
    
    max_sg = max(ott, app, arg, putt)
    
    if max_sg == 0:
        return "Balanced", None
    
    if ott == max_sg:
        return "Driving", "ott"
    elif app == max_sg:
        return "Approach", "app"
    elif arg == max_sg:
        return "Short Game", "arg"
    else:
        return "Putting", "putt"


def calculate_fit_score(player_sg: dict, course_row) -> float:
    """Calculate how well a player fits a course (0-100)."""
    if not player_sg:
        return 50
    
    # Use absolute values for weights (importance)
    ott_w = abs(course_row.get('ott_sg', 0.03))
    app_w = abs(course_row.get('app_sg', 0.03))
    putt_w = abs(course_row.get('putt_sg', 0.01))
    
    total_w = ott_w + app_w + putt_w
    if total_w == 0:
        return 50
    
    # Normalize weights
    ott_w /= total_w
    app_w /= total_w
    putt_w /= total_w
    
    # Player SG scores (scale -1 to +1 range to 0-100)
    # +1.0 SG = 100, 0 SG = 50, -1.0 SG = 0
    ott_score = min(100, max(0, (player_sg.get('ott', 0) + 1) * 50))
    app_score = min(100, max(0, (player_sg.get('app', 0) + 1) * 50))
    putt_score = min(100, max(0, (player_sg.get('putt', 0) + 1) * 50))
    
    # Weighted fit score
    fit = ott_w * ott_score + app_w * app_score + putt_w * putt_score
    
    # Cap at 100
    return min(100, fit)


def display_course_profile(course_name: str = None):
    """Display a course's profile and requirements."""
    courses = load_course_profiles()
    
    if courses.empty:
        print("No course data available")
        return
    
    if course_name:
        matches = courses[courses['course_name'].str.lower().str.contains(course_name.lower(), na=False)]
        if matches.empty:
            matches = courses[courses['tournament_name'].str.lower().str.contains(course_name.lower(), na=False)]
        
        if matches.empty:
            print(f"Course '{course_name}' not found")
            return
        
        course = matches.iloc[0]
    else:
        tournament = get_current_tournament()
        if tournament:
            matches = courses[courses['tournament_name'].str.lower().str.contains(tournament.lower().split()[0], na=False)]
            if not matches.empty:
                course = matches.iloc[0]
            else:
                print(f"No course data for {tournament}")
                return
        else:
            print("No current tournament found")
            return
        
        
    
    
    
    print()
    print("=" * 65)
    print(f"  COURSE PROFILE: {course['course_name'].upper()}")
    print(f"  Tournament: {course['tournament_name']}")
    print("=" * 65)
    print()
    
    # Physical characteristics
    print("  COURSE CHARACTERISTICS")
    print("  " + "-" * 60)
    print(f"  Yardage:        {course.get('yardage', 'N/A'):,}")
    print(f"  Par:            {int(course.get('par', 0))}")
    print(f"  Fairway Width:  {course.get('fw_width', 'N/A')} yards")
    print(f"  Rough Penalty:  {course.get('rgh_diff', 'N/A')}")
    toughness_df = load_course_toughness()                                                                            
    if not toughness_df.empty:                                                                                        
        course_name_lower = course['course_name'].lower()                                                             
        match = toughness_df[toughness_df['course_name'].str.lower().str.contains(                                    
            course_name_lower.split('(')[0].strip()[:20], na=False                                                    
        )]                                                                                                            
        if not match.empty:                                                                                           
            t = match.iloc[0]                                                                                         
            print()                                                                                                   
            print("  PGA TOUR SCORING STATS")                                                                         
            print("  " + "-" * 60)                                                                                    
            print(f"  Toughness Rank:  #{int(t['rank'])} of {len(toughness_df)}")                                     
            print(f"  Scoring Avg:     {t['scoring_avg']:.3f}")                                                       
            print(f"  To Par:          {t['scoring_to_par']:+.3f}")                                                   
                                                                                                                    
            # Difficulty indicator                                                                                    
            to_par = t['scoring_to_par']                                                                              
            if to_par > -1:                                                                                           
                diff = "🔴 VERY TOUGH"                                                                                
            elif to_par > -2:                                                                                         
                diff = "🟠 TOUGH"                                                                                     
            elif to_par > -3:                                                                                         
                diff = "🟡 MODERATE"                                                                                  
            else:                                                                                                     
                diff = "🟢 SCORABLE"                                                                                  
            print(f"  Difficulty:      {diff}")   

    
    print()
    
    # SG importance - use absolute values and rank them
    print("  SKILL IMPORTANCE (ranked by impact)")
    print("  " + "-" * 60)
    
    ott = course.get('ott_sg', 0)
    app = course.get('app_sg', 0)
    arg = course.get('arg_sg', 0)
    putt = course.get('putt_sg', 0)
    
    # Create ranked list by absolute value
    skills = [
        ("Off-the-Tee", ott, abs(ott)),
        ("Approach", app, abs(app)),
        ("Around Green", arg, abs(arg)),
        ("Putting", putt, abs(putt))
    ]
    skills.sort(key=lambda x: x[2], reverse=True)
    
    # Display with rank indicators
    rank_icons = ["1️⃣ ", "2️⃣ ", "3️⃣ ", "4️⃣ "]
    
    for i, (name, val, abs_val) in enumerate(skills):
        # Create bar based on relative importance (normalized to highest)
        max_abs = skills[0][2] if skills[0][2] > 0 else 1
        bar_len = int((abs_val / max_abs) * 15)
        bar = "█" * bar_len + "░" * (15 - bar_len)
        
        # Show the actual value with sign
        val_str = f"{val:+.3f}" if val != 0 else "0.000"
        
        print(f"  {rank_icons[i]}{name:<14} {bar} {val_str}")
    
    print()
    
    # Course type and interpretation
    course_type, primary_skill = categorize_course(course)
    print(f"  Course Type: {course_type.upper()} COURSE")
    
    interpretations = {
        "Driving": "→ Favors long, accurate drivers off the tee",
        "Approach": "→ Favors elite iron players and ball strikers",
        "Short Game": "→ Favors players with strong wedge/chip games",
        "Putting": "→ Favors hot putters on these greens",
        "Balanced": "→ Rewards all-around players"
    }
    print(f"  {interpretations.get(course_type, '')}")
    
    # Additional insights
    print()
    print("  COURSE NOTES")
    print("  " + "-" * 60)
    
    fw_width = course.get('fw_width', 30)
    if fw_width < 28:
        print("  • Narrow fairways - accuracy off the tee is critical")
    elif fw_width > 35:
        print("  • Wide fairways - bombers can grip and rip")
    
    rgh_diff = course.get('rgh_diff', 0.25)
    if rgh_diff > 0.35:
        print("  • Penal rough - must hit fairways")
    elif rgh_diff < 0.2:
        print("  • Forgiving rough - missing fairways less costly")
    
    yardage = course.get('yardage', 7000)
    if isinstance(yardage, str):
        yardage = int(yardage.replace(',', ''))
    if yardage > 7400:
        print("  • Long course - distance is an advantage")
    elif yardage < 7000:
        print("  • Shorter course - accuracy trumps distance")
    
    print()


def display_player_fit(player_name: str, this_week: bool = False):
    """Display a player's course fit analysis."""
    sg_df = load_player_sg()
    courses = load_course_profiles()
    
    player_sg = get_player_sg_profile(player_name, sg_df)
    
    if not player_sg:
        print(f"No SG data found for {player_name}")
        return
    
    print()
    print("=" * 65)
    print(f"  COURSE FIT ANALYSIS: {player_name.upper()}")
    print("=" * 65)
    print()
    
    # Player's SG profile
    print("  STROKES GAINED PROFILE")
    print("  " + "-" * 60)
    
    def sg_bar(val, width=15):
        normalized = (val + 1) / 2
        normalized = max(0, min(1, normalized))
        filled = int(normalized * width)
        return "█" * filled + "░" * (width - filled)
    
    ott = player_sg.get('ott', 0)
    app = player_sg.get('app', 0)
    putt = player_sg.get('putt', 0)
    total = player_sg.get('total', 0)
    
    print(f"  SG: Total       {sg_bar(total)} {total:+.2f}")
    print(f"  SG: Off-Tee     {sg_bar(ott)} {ott:+.2f}")
    print(f"  SG: Approach    {sg_bar(app)} {app:+.2f}")
    print(f"  SG: Putting     {sg_bar(putt)} {putt:+.2f}")
    print()
    
    # Identify strengths/weaknesses
    skills = [("Off-the-Tee", ott), ("Approach", app), ("Putting", putt)]
    skills.sort(key=lambda x: x[1], reverse=True)
    
    print(f"  💪 Strength: {skills[0][0]} ({skills[0][1]:+.2f})")
    print(f"  ⚠️  Weakness: {skills[-1][0]} ({skills[-1][1]:+.2f})")
    print()
    
    # This week's fit
    tournament = get_current_tournament()
    if tournament and not courses.empty:
        matches = courses[courses['tournament_name'].str.lower().str.contains(
            tournament.lower().replace("the ", "").split()[0], na=False
        )]
        
        if not matches.empty:
            course = matches.iloc[0]
            fit_score = calculate_fit_score(player_sg, course)
            
            print("  " + "-" * 60)
            print(f"  THIS WEEK: {tournament}")
            print(f"  Course: {course['course_name']}")
            print("  " + "-" * 60)
            
            if fit_score >= 70:
                rating = "EXCELLENT"
                emoji = "🟢"
            elif fit_score >= 60:
                rating = "GOOD"
                emoji = "🟡"
            elif fit_score >= 50:
                rating = "FAIR"
                emoji = "🟠"
            else:
                rating = "POOR"
                emoji = "🔴"
            
            print(f"  Course Fit: {emoji} {fit_score:.0f}/100 ({rating})")
            
            # Explain fit
            course_type, primary_skill = categorize_course(course)
            player_strength = skills[0][0]
            player_weakness = skills[-1][0]
            
            if course_type == "Driving" and "Tee" in player_strength:
                print("  ✓ Driving course matches their strength")
            elif course_type == "Approach" and "Approach" in player_strength:
                print("  ✓ Approach course matches their strength")
            elif course_type == "Putting" and "Putting" in player_strength:
                print("  ✓ Putting course matches their strength")
            
            if course_type == "Driving" and "Tee" in player_weakness:
                print("  ⚠️ Driving course exposes their weakness")
            elif course_type == "Approach" and "Approach" in player_weakness:
                print("  ⚠️ Approach course exposes their weakness")
            elif course_type == "Putting" and "Putting" in player_weakness:
                print("  ⚠️ Putting course exposes their weakness")
            
            print()
    
    # Best/worst course types
    if not courses.empty:
        print("  " + "-" * 60)
        print("  BEST FIT TOURNAMENTS (based on skill match)")
        print("  " + "-" * 60)
        
        courses['fit_score'] = courses.apply(lambda r: calculate_fit_score(player_sg, r), axis=1)
        best = courses.nlargest(5, 'fit_score')
        
        for _, row in best.iterrows():
            fit = row['fit_score']
            print(f"  • {row['tournament_name'][:40]:<40} {fit:.0f}/100")
        
        print()
        
        print("  WORST FIT TOURNAMENTS")
        print("  " + "-" * 60)
        worst = courses.nsmallest(5, 'fit_score')
        
        for _, row in worst.iterrows():
            fit = row['fit_score']
            print(f"  • {row['tournament_name'][:40]:<40} {fit:.0f}/100")
        
        print()


def main():
    parser = argparse.ArgumentParser(description="Analyze course fit for players")
    parser.add_argument("player", nargs="?", help="Player name to analyze")
    parser.add_argument("--course", "-c", help="Show specific course profile")
    parser.add_argument("--this-week", "-t", action="store_true", help="Focus on this week's tournament")
    
    args = parser.parse_args()
    
    if args.course:
        display_course_profile(args.course)
    elif args.player:
        display_player_fit(args.player, args.this_week)
    else:
        display_course_profile()


if __name__ == "__main__":
    main()
