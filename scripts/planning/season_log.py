"""
Season Log
==========
Track and display Season-Long fantasy golf performance.

Usage:                                                                                                                
    python season_log.py                    # Show season summary                                                     
    python season_log.py --detailed         # Show week-by-week breakdown                                             
    python season_log.py --export           # Export to CSV  
"""


import argparse 
import json 
import pandas as pd 
from pathlib import Path 
from datetime import datetime 

DATA_DIR = Path(__file__).parent.parent.parent / "data"                                                               
USAGE_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"                                                         
TRACKING_DIR = DATA_DIR / "prediction_tracking"                                                                       
PICKS_LOG_FILE = DATA_DIR / "fantasy" / "season_picks_log.csv" 




def load_usage_data() -> dict:
    if USAGE_FILE.exists():
        with open(USAGE_FILE, 'r') as f:
            return json.load(f)
    return {}



def load_calibration_reports() -> list:
    """Load all calibration reports."""
    reports = []
    reports_dir = Path("outputs/picks_reports")
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("*.json")):
            try:
                with open(f) as file:
                    data = json.load(file)
                    data['_file'] = f.stem 
                    reports.append(data)
            except:
                pass 
    return reports


def build_season_log() -> pd.DataFrame:
    """Build season log from usage tracker."""
    usage = load_usage_data()
    lineups = usage.get("weekly_lineups", {})
    picks = usage.get("picks", {})
    rows = []
    
    for wek_key, lineup in sorted(lineups.items()):
        week_num = lineup.get("week", 0)
        tournament = lineup.get("tournament", "")
        date = lineup.get("date", "")
        
        
        week_points = 0
        week_picks = []
        
        for player_name in lineup.get("lineup", []):
            player_data = picks.get(player_name, [])
            
            result = None 
            points = 0
            for t in player_data.get("tournaments_used", []):
                if t.get("tournament") == tournament:
                    result = t.get('result', "?")
                    points = t.get("points", 0)
                    break 
            week_points += points 
            week_picks.append({
                "week": week_num, 
                "tournament": tournament, 
                'date': date, 
                'player': player_name, 
                'finish': result, 
                'points': points
            })
            
        for pick in week_picks:
            pick['week_total'] = week_picks 
            rows.append(pick)
    return pd.DataFrame(rows)



def display_summary():
    """Display season summary."""
    usage = load_usage_data()
    df = build_season_log()
    
    print()
    print("=" * 70)
    print(" SEASON 2026 - FANTASY GOLF PERFORMANCE")
    print("=" * 70)
    print()
    
    total_points = usage.get("summary", {}).get("total_points", 0)
    weeks_played = len(usage.get("weekly_lineups", {}))
    
                       
    print(f"  Total Points:     {total_points}")                                                                      
    print(f"  Weeks Played:     {weeks_played}")                                                                      
    print(f"  Avg Points/Week:  {total_points/weeks_played:.1f}" if weeks_played else "  Avg Points/Week:  -")        
    print()                                                                                                           
                                                                                                                        
    # Week by week                                                                                                    
    print("  WEEKLY RESULTS")                                                                                         
    print("  " + "-" * 65)                                                                                            
    print(f"  {'Week':<6} {'Tournament':<35} {'Points':<10}")                                                         
    print("  " + "-" * 65)    
    
    
    weekly = df.groupby(['week', 'tournament']).agg({"points": "sum"}).reset_index()
    cumulative = 0
    
    for _, row in weekly.iterrows():                                                                                  
          cumulative += row["points"]                                                                                   
          print(f"  {row['week']:<6} {row['tournament'][:35]:<35} {int(row['points']):<10} (cum: {cumulative})")        
                                                                                                                        
    print()                                                                                                           
                                                                                                                        
    # Top performers                                                                                                  
    print("  TOP PICKS (by points)")                                                                                  
    print("  " + "-" * 65)                                                                                            
                                                                                                                        
    player_totals = df.groupby("player")["points"].sum().sort_values(ascending=False)                                 
    for player, pts in player_totals.head(5).items():                                                                 
        print(f"  • {player:<30} {int(pts)} pts")
        
        
    print()
    
    # Accuracy stats 
    
    if not df.empty:
        df['made_cut'] = ~df['finish'].isin(['MC', 'CUT', 'WD', 'DQ', None, "?"])
        df["top10"] = df["finish"].apply(lambda x: _is_top_n(x, 10))                                                  
        df["won"] = df["finish"].apply(lambda x: x == "1" or x == 1)                                                  
                                                                                                                    
        total_picks = len(df)                                                                                         
        cuts_made = df["made_cut"].sum()                                                                              
        top10s = df["top10"].sum()                                                                                    
        wins = df["won"].sum()                                                                                        
                                                                                                                    
        print("  PICK ACCURACY")                                                                                      
        print("  " + "-" * 65)                                                                                        
        print(f"  Cuts Made:  {cuts_made}/{total_picks} ({cuts_made/total_picks*100:.0f}%)")                          
        print(f"  Top 10s:    {top10s}/{total_picks} ({top10s/total_picks*100:.0f}%)")                                
        print(f"  Wins:       {wins}/{total_picks}")                                                                  
                                                                                                                    
    print()      
    
    
    
def _is_top_n(finish, n):                                                                                             
    """Check if finish is top N."""                                                                                   
    if finish is None or finish == "?" or finish in ["MC", "CUT", "WD", "DQ"]:                                        
        return False                                                                                                  
    try:                                                                                                              
        pos = int(str(finish).replace("T", ""))                                                                       
        return pos <= n                                                                                               
    except:                                                                                                           
        return False

def display_detailed():
    """Display detailed week-by-week breakdown.""" 
    df = build_season_log()
    
    if df.empty:
        print("No picks recorded yet.")
        return 
    
    print()                                                                                                           
    print("=" * 70)                                                                                                   
    print("  DETAILED SEASON LOG")                                                                                    
    print("=" * 70)    
    
    
    for week in sorted(df["week"].unique()):                                                                          
        week_df = df[df["week"] == week]                                                                              
        tournament = week_df["tournament"].iloc[0]                                                                    
        week_total = week_df["week_total"].iloc[0]                                                                    
                                                                                                                    
        print()                                                                                                       
        print(f"  WEEK {week}: {tournament}")                                                                         
        print("  " + "-" * 60)                                                                                        
        print(f"  {'Player':<30} {'Finish':<10} {'Points':<10}")                                                      
        print("  " + "-" * 60)                                                                                        
                                                                                                                    
        for _, row in week_df.iterrows():                                                                             
            finish = row["finish"] if row["finish"] else "?"                                                          
            points = int(row["points"]) if row["points"] else 0                                                       
            print(f"  {row['player']:<30} {finish:<10} {points:<10}")                                                 
                                                                                                                    
        print(f"  {'TOTAL':<30} {'':<10} {int(week_total):<10}")                                                      
                                                                                                                        
    print()  
    
     


def export_to_csv():
    """Export season log to CSV."""
    df = build_season_log()
    PICKS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PICKS_LOG_FILE, index=False)
    
    print(f"Exported to {PICKS_LOG_FILE}")
    print()
    print(df.to_string(index=False))
    
    
def main():                                                                                                           
    parser = argparse.ArgumentParser(description="View season performance log")                                       
    parser.add_argument("--detailed", "-d", action="store_true", help="Show week-by-week breakdown")                  
    parser.add_argument("--export", "-e", action="store_true", help="Export to CSV")                                  
                                                                                                                    
    args = parser.parse_args()                                                                                        
                                                                                                                    
    if args.export:                                                                                                   
        export_to_csv()                                                                                               
    elif args.detailed:                                                                                               
        display_detailed()                                                                                            
    else:                                                                                                             
        display_summary()                                                                                             
                                                                                                                    
                                                                                                                    
if __name__ == "__main__":                                                                                            
    main()                                                                                                            
               