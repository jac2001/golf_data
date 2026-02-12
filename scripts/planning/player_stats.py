"""                                                                                                                   
Player Stats Lookup                                                                                                   
===================                                                                                                   
Shows strokes gained breakdown and recent results for any player.                                                     
                                                                                                                    
Usage:                                                                                                                
    python player_stats.py "Scottie Scheffler"                                                                        
    python player_stats.py "Scottie Scheffler" --recent 10                                                            
    python player_stats.py --top 20                                                                                   
"""                                                                                                                   
                                                                                                                    
import argparse                                                                                                       
import pandas as pd                                                                                                   
from pathlib import Path                                                                                              
                                                                                                                    
DATA_DIR = Path(__file__).parent.parent.parent / "data"                                                               
                                                                                                                    
                                                                                                                    
def load_strokes_gained(years: list[int] = None) -> pd.DataFrame:                                                     
    """Load strokes gained data from tournament stats files."""                                                       
    if years is None:                                                                                                 
        years = [2024, 2025, 2026]                                                                                    
                                                                                                                    
    dfs = []                                                                                                          
    for year in years:                                                                                                
        path = DATA_DIR / "historical" / f"tournament_stats_{year}.csv"                                               
        if path.exists():                                                                                             
            df = pd.read_csv(path)                                                                                    
            dfs.append(df)                                                                                            
                                                                                                                    
    if not dfs:                                                                                                       
        return pd.DataFrame()                                                                                         
                                                                                                                    
    df = pd.concat(dfs, ignore_index=True)                                                                            
                                                                                                                    
    # Filter for strokes gained stats with "Avg" component                                                            
    sg_stats = [                                                                                                      
        "Strokes Gained: Total",                                                                                      
        "Strokes Gained: Off-the-Tee",                                                                                
        "Strokes Gained: Approach",                                                                                   
        "Strokes Gained: Tee-to-Green",                                                                               
        "Strokes Gained: Putting"                                                                                     
    ]                                                                                                                 
                                                                                                                    
    df = df[                                                                                                          
        (df["stat_name"].isin(sg_stats)) &                                                                            
        (df["stat_component"] == "Avg")                                                                               
    ].copy()                                                                                                          
                                                                                                                    
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")                                               
                                                                                                                    
    return df                                                                                                         
                                                                                                                    
                                                                                                                    
def load_recent_results(years: list[int] = None) -> pd.DataFrame:                                                     
    """Load leaderboard data for recent results."""                                                                   
    if years is None:                                                                                                 
        years = [2024, 2025, 2026]                                                                                    
                                                                                                                    
    dfs = []                                                                                                          
    for year in years:                                                                                                
        path = DATA_DIR / "historical" / f"leaderboards_{year}.csv"                                                   
        if path.exists():                                                                                             
            df = pd.read_csv(path)                                                                                    
            dfs.append(df)                                                                                            
                                                                                                                    
    if not dfs:                                                                                                       
        return pd.DataFrame()                                                                                         
                                                                                                                    
    return pd.concat(dfs, ignore_index=True)                                                                          
                                                                                                                    
                                                                                                                    
def get_player_sg(player_name: str, sg_df: pd.DataFrame) -> dict:                                                     
    """Get strokes gained breakdown for a player."""                                                                  
    # Fuzzy match player name                                                                                         
    mask = sg_df["player_name"].str.lower().str.contains(player_name.lower())                                         
    player_data = sg_df[mask]                                                                                         
                                                                                                                    
    if player_data.empty:                                                                                             
        return None                                                                                                   
                                                                                                                    
    # Get actual player name                                                                                          
    actual_name = player_data["player_name"].iloc[0]                                                                  
                                                                                                                    
    # Aggregate by stat category                                                                                      
    sg_breakdown = {}                                                                                                 
    stat_map = {                                                                                                      
        "Strokes Gained: Total": "SG: Total",                                                                         
        "Strokes Gained: Off-the-Tee": "SG: Off-the-Tee",                                                             
        "Strokes Gained: Approach": "SG: Approach",                                                                   
        "Strokes Gained: Tee-to-Green": "SG: Tee-to-Green",                                                           
        "Strokes Gained: Putting": "SG: Putting"                                                                      
    }                                                                                                                 
                                                                                                                    
    for stat_name, display_name in stat_map.items():                                                                  
        stat_data = player_data[player_data["stat_name"] == stat_name]                                                
        if not stat_data.empty:                                                                                       
            sg_breakdown[display_name] = {                                                                            
                "avg": stat_data["stat_value"].mean(),                                                                
                "events": len(stat_data),                                                                             
                "best": stat_data["stat_value"].max(),                                                                
                "worst": stat_data["stat_value"].min()                                                                
            }                                                                                                         
                                                                                                                    
    return {"name": actual_name, "stats": sg_breakdown}                                                               
                                                                                                                    
                                                                                                                    
def get_player_results(player_name: str, results_df: pd.DataFrame, limit: int = 10) -> list:                          
    """Get recent tournament results for a player."""                                                                 
    mask = results_df["player_name"].str.lower().str.contains(player_name.lower())                                    
    player_data = results_df[mask].copy()                                                                             
                                                                                                                    
    if player_data.empty:                                                                                             
        return []                                                                                                     
                                                                                                                    
    # Sort by year and tournament (most recent first)                                                                 
    player_data = player_data.sort_values(["year", "tournament_id"], ascending=[False, False])                        
                                                                                                                    
    results = []                                                                                                      
    for _, row in player_data.head(limit).iterrows():                                                                 
        results.append({                                                                                              
            "tournament": row["tournament_name"],                                                                     
            "year": row["year"],                                                                                      
            "position": row["position"],                                                                              
            "to_par": row.get("to_par", "—"),                                                                         
            "earnings": row.get("earnings", "—")                                                                      
        })                                                                                                            
                                                                                                                    
    return results                                                                                                    
                                                                                                                    
                                                                                                                    
def format_sg_bar(value: float, width: int = 20) -> str:                                                              
    """Create a visual bar for SG value."""                                                                           
    # Scale: -2 to +2 maps to 0 to width                                                                              
    normalized = (value + 2) / 4  # 0 to 1                                                                            
    normalized = max(0, min(1, normalized))                                                                           
    filled = int(normalized * width)                                                                                  
                                                                                                                    
    if value >= 0.5:                                                                                                  
        color = "█"  # Strong positive                                                                                
    elif value >= 0:                                                                                                  
        color = "▓"  # Positive                                                                                       
    elif value >= -0.5:                                                                                               
        color = "░"  # Slight negative                                                                                
    else:                                                                                                             
        color = "·"  # Negative                                                                                       
                                                                                                                    
    bar = color * filled + "·" * (width - filled)                                                                     
    return f"[{bar}]"                                                                                                 
                                                                                                                    
                                                                                                                    
def display_player_stats(player_name: str, recent: int = 5):                                                          
    """Display full player stats."""                                                                                  
    print(f"\nLoading stats for: {player_name}")                                                                      
    print("=" * 70)                                                                                                   
                                                                                                                    
    # Load data                                                                                                       
    sg_df = load_strokes_gained()                                                                                     
    results_df = load_recent_results()                                                                                
                                                                                                                    
    # Get strokes gained                                                                                              
    sg_data = get_player_sg(player_name, sg_df)                                                                       
                                                                                                                    
    if not sg_data:                                                                                                   
        print(f"❌ Player '{player_name}' not found")                                                                 
        return                                                                                                        
                                                                                                                    
    print(f"\n  {sg_data['name'].upper()}")                                                                           
    print("=" * 70)                                                                                                   
                                                                                                                    
    # Strokes Gained Breakdown                                                                                        
    print("\n  STROKES GAINED (per round avg, last 2 years)")                                                         
    print("  " + "-" * 66)                                                                                            
                                                                                                                    
    stats_order = ["SG: Total", "SG: Off-the-Tee", "SG: Approach", "SG: Putting"]                                     
                                                                                                                    
    for stat in stats_order:                                                                                          
        if stat in sg_data["stats"]:                                                                                  
            s = sg_data["stats"][stat]                                                                                
            sign = "+" if s["avg"] >= 0 else ""                                                                       
            bar = format_sg_bar(s["avg"])                                                                             
            print(f"  {stat:<20} {sign}{s['avg']:>6.3f}  {bar}  ({s['events']} events)")                              
                                                                                                                    
    # Strength/Weakness summary                                                                                       
    print("\n  ANALYSIS")                                                                                             
    print("  " + "-" * 66)                                                                                            
                                                                                                                    
    stats = sg_data["stats"]                                                                                          
    categories = ["SG: Off-the-Tee", "SG: Approach", "SG: Putting"]                                                   
                                                                                                                    
    ranked = sorted(                                                                                                  
        [(cat, stats[cat]["avg"]) for cat in categories if cat in stats],                                             
        key=lambda x: x[1],                                                                                           
        reverse=True                                                                                                  
    )                                                                                                                 
                                                                                                                    
    if ranked:                                                                                                        
        best = ranked[0]                                                                                              
        worst = ranked[-1]                                                                                            
        print(f"  💪 Strength: {best[0].replace('SG: ', '')} ({best[1]:+.3f})")                                       
        print(f"  ⚠️  Weakness: {worst[0].replace('SG: ', '')} ({worst[1]:+.3f})")                                    
                                                                                                                    
    # Recent Results                                                                                                  
    results = get_player_results(player_name, results_df, limit=recent)                                               
                                                                                                                    
    if results:                                                                                                       
        print(f"\n  RECENT RESULTS (last {len(results)} events)")                                                     
        print("  " + "-" * 66)                                                                                        
        print(f"  {'Tournament':<35} {'Pos':>6} {'To Par':>8}")                                                       
        print("  " + "-" * 66)                                                                                        
                                                                                                                    
        for r in results:                                                                                             
            tourney = r["tournament"][:35]                                                                            
            print(f"  {tourney:<35} {r['position']:>6} {r['to_par']:>8}")                                             
                                                                                                                    
    print()                                                                                                           
                                                                                                                    
                                                                                                                    
def display_top_sg(n: int = 20):                                                                                      
    """Display top players by strokes gained total."""                                                                
    print(f"\n  TOP {n} PLAYERS BY STROKES GAINED (2024-2026)")                                                       
    print("=" * 70)                                                                                                   
                                                                                                                    
    sg_df = load_strokes_gained()                                                                                     
                                                                                                                    
    # Filter for SG Total                                                                                             
    total_df = sg_df[sg_df["stat_name"] == "Strokes Gained: Total"]                                                   
                                                                                                                    
    # Aggregate by player                                                                                             
    player_avg = total_df.groupby("player_name").agg({                                                                
        "stat_value": ["mean", "count"]                                                                               
    }).reset_index()                                                                                                  
    player_avg.columns = ["player", "avg_sg", "events"]                                                               
                                                                                                                    
    # Filter for minimum events                                                                                       
    player_avg = player_avg[player_avg["events"] >= 5]                                                                
    player_avg = player_avg.sort_values("avg_sg", ascending=False).head(n)                                            
                                                                                                                    
    print(f"\n  {'#':<4} {'Player':<30} {'SG Total':>10} {'Events':>8}")                                              
    print("  " + "-" * 56)                                                                                            
                                                                                                                    
    for i, row in enumerate(player_avg.itertuples(), 1):                                                              
        bar = format_sg_bar(row.avg_sg, width=15)                                                                     
        print(f"  {i:<4} {row.player:<30} {row.avg_sg:>+10.3f} {int(row.events):>8}")                                 
                                                                                                                    
    print()                                                                                                           
                                                                                                                    
                                                                                                                    
def main():                                                                                                           
    parser = argparse.ArgumentParser(description="Player strokes gained lookup")                                      
    parser.add_argument("player", nargs="?", help="Player name to look up")                                           
    parser.add_argument("--recent", "-r", type=int, default=5,                                                        
                        help="Number of recent results to show")                                                      
    parser.add_argument("--top", "-t", type=int,                                                                      
                        help="Show top N players by SG Total")                                                        
                                                                                                                    
    args = parser.parse_args()                                                                                        
                                                                                                                    
    if args.top:                                                                                                      
        display_top_sg(args.top)                                                                                      
    elif args.player:                                                                                                 
        display_player_stats(args.player, recent=args.recent)                                                         
    else:                                                                                                             
        parser.print_help()                                                                                           
                                                                                                                    
                                                                                                                    
if __name__ == "__main__":                                                                                            
    main()  