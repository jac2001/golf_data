"""                                                                                                                   
Auto Record Results                                                                                                   
===================                                                                                                   
Automatically records tournament results for your picks.                                                              
                                                                                                                    
Usage:                                                                                                                
    python auto_record_results.py                           # Record pending results                                  
    python auto_record_results.py --tournament "WM Phoenix" # Specific tournament                                     
    python auto_record_results.py --dry-run                 # Preview without saving                                  
"""                                                                                                                   
                                                                                                                    
import argparse                                                                                                       
import json                                                                                                           
import pandas as pd                                                                                                   
from pathlib import Path                                                                                              
from datetime import datetime                                                                                         
                                                                                                                    
DATA_DIR = Path(__file__).parent.parent.parent / "data"                                                               
USAGE_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"                                                         
LEADERBOARDS_FILE = DATA_DIR / "historical" / "leaderboards_2026.csv"                                                 
                                                                                                                    
                                                                                                                    
def load_usage_tracker() -> dict:                                                                                     
    if USAGE_FILE.exists():                                                                                           
        with open(USAGE_FILE) as f:                                                                                   
            return json.load(f)                                                                                       
    return {}                                                                                                         
                                                                                                                    
                                                                                                                    
def save_usage_tracker(data: dict):                                                                                   
    with open(USAGE_FILE, 'w') as f:                                                                                  
        json.dump(data, f, indent=2)                                                                                  
                                                                                                                    
                                                                                                                    
def load_leaderboards() -> pd.DataFrame:                                                                              
    if LEADERBOARDS_FILE.exists():                                                                                    
        return pd.read_csv(LEADERBOARDS_FILE)                                                                         
    return pd.DataFrame()                                                                                             
                                                                                                                    
                                                                                                                    
def normalize_name(name: str) -> str:                                                                                 
    """Normalize player name for matching."""                                                                         
    if not name:                                                                                                      
        return ""                                                                                                     
    name = str(name).strip().lower()                                                                                  
    # Handle "Last, First" format                                                                                     
    if ", " in name:                                                                                                  
        parts = name.split(", ", 1)                                                                                   
        name = f"{parts[1]} {parts[0]}"                                                                               
    return name



def normalize_tournament(name: str) -> str:
    """Normalize tournament name for matching."""
    if not name:
        return ""
    return str(name).strip().lower()
    

def find_pending_tournaments(usage_data: dict) -> list:
    """Finding tournaments with pending results in usage data."""
    
    pending = []
    for player_name, player_data in usage_data.get("picks", {}).items():
        for t in player_data.get("tournaments_used", player_data.get("tournament_used", [])):
            if t.get("result") is None or t.get('points') is None:
                tournament = t.get("tournament")
                if tournament and tournament not in pending:
                    pending.append(tournament)
    return pending 



def match_results(usage_data: dict, leaderboards: pd.DataFrame, 
                  tournament_filter: str=None, dry_run:bool=False) -> dict:
    """Match picks to leaderboard results and record them"""
    if leaderboards.empty:
        return {'error': 'No leaderboards data available'}
    
    results_lookup = {}
    for _, row in leaderboards.iterrows():
        t_name = normalize_tournament(row.get("tournament_name", ""))
        p_name = normalize_name(row.get("player_name", ""))
        
        
        key = (t_name, p_name)
        results_lookup[key] = {                                                                                       
              "position": row.get("position"),                                                                          
              "fedex_points": row.get("fedex_points", 0),                                                               
              "earnings": row.get("earnings", "$0"),                                                                    
              "to_par": row.get("to_par"),                                                                              
          } 
        
    updates = []
    not_found = []
    already_recorded = []
    
    picks = usage_data.get("picks", {})
    for player_name, player_data in picks.items():
        for t in player_data.get("tournaments_used", []):
            tournament = t.get("tournament", "")
            #Skip if already has result 
            
            if t.get("result") is not None and t.get("points") is not None:
                already_recorded.append((player_name, tournament))
                continue
            
            #Look up result  
            t_norm = normalize_tournament(tournament)
            p_norm = normalize_name(player_name)
            
            #Try exact match first 
            key = (t_norm, p_norm)
            result = results_lookup.get(key)
            
            
            
            if not result:
                for (t_key, p_key), res in results_lookup.items():
                    if p_key == p_norm and (t_norm in t_key or t_key in t_norm):
                        result = res 
                        break 
                    
            if result:                                                                                                
                position = result["position"]                                                                         
                # Parse FedEx points (handle string format)                                                           
                try:                                                                                                  
                    points = int(float(result["fedex_points"]))                                                       
                except:                                                                                               
                    points = 0                                                                                        
                                                                                                                    
                updates.append({                                                                                      
                    "player": player_name,                                                                            
                    "tournament": tournament,                                                                         
                    "position": position,                                                                             
                    "points": points,                                                                                 
                    "to_par": result.get("to_par"),                                                                   
                })                                                                                                    
                                                                                                                    
                if not dry_run:                                                                                       
                    t["result"] = str(position)                                                                       
                    t["points"] = points                                                                              
            else:                                                                                                     
                not_found.append((player_name, tournament)) 
    
    if not dry_run and updates:
        for player_name, player_data in picks.items():
            total = sum(t.get("points", 0) or 0 for t in player_data.get("tournaments_used", []))
            player_data['total_points'] = total
            
        usage_data['summary']['total_points'] = sum(
            p.get('total_points', 0) for p in picks.values()
        )          
        usage_data['last_updated'] = datetime.now().isoformat()
        save_usage_tracker(usage_data) 
        
        
    return {                                                                                                          
          "updates": updates,                                                                                           
          "not_found": not_found,                                                                                       
          "already_recorded": already_recorded,                                                                         
          "dry_run": dry_run,                                                                                           
      }                                                
                                
def display_results(result: dict):                                                                                    
    """Display auto-record results."""                                                                                
    print()                                                                                                           
    print("=" * 70)                                                                                                   
    print("  AUTO-RECORD RESULTS")                                                                                    
    print("=" * 70)                                                                                                   
                                                                                                                    
    if result.get("dry_run"):                                                                                         
        print("  ⚠️  DRY RUN - No changes saved")                                                                     
                                                                                                                    
    print()                                                                                                           
                                                                                                                    
    updates = result.get("updates", [])                                                                               
    if updates:                                                                                                       
        print(f"  ✅ RECORDED ({len(updates)} picks)")                                                                
        print("  " + "-" * 65)                                                                                        
        print(f"  {'Player':<25} {'Tournament':<25} {'Finish':<8} {'Pts':<6}")                                        
        print("  " + "-" * 65)                                                                                        
                                                                                                                    
        for u in updates:                                                                                             
            print(f"  {u['player']:<25} {u['tournament'][:25]:<25} {u['position']:<8} {u['points']:<6}")              
                                                                                                                    
        total_pts = sum(u["points"] for u in updates)                                                                 
        print("  " + "-" * 65)                                                                                        
        print(f"  {'TOTAL':<25} {'':<25} {'':<8} {total_pts:<6}")                                                     
        print()                                                                                                       
                                                                                                                    
    not_found = result.get("not_found", [])                                                                           
    if not_found:                                                                                                     
        print(f"  ❌ NOT FOUND IN LEADERBOARD ({len(not_found)})")                                                    
        print("  " + "-" * 65)                                                                                        
        for player, tournament in not_found:                                                                          
            print(f"  • {player} @ {tournament}")                                                                     
        print()                                                                                                       
        print("  💡 Tip: Make sure leaderboard data is up to date")                                                   
        print("     Run: python scripts/scrapers/fetch_leaderboard.py")                                               
        print()                                                                                                       
                                                                                                                    
    already = result.get("already_recorded", [])                                                                      
    if already:                                                                                                       
        print(f"  ℹ️  Already recorded: {len(already)} picks")                                                        
                                                                                                                    
    if not updates and not not_found:                                                                                 
        print("  ✓ All picks already have results recorded")                                                          
                                                                                                                    
    print()         
    
    
def trigger_recalibration():                                                                                          
    """Trigger model recalibration after recording new results."""                                                    
    import subprocess                                                                                                 
                                                                                                                    
    calibration_script = Path(__file__).parent / "calibration.py"                                                     
    if calibration_script.exists():                                                                                   
        print("\n🔄 Triggering model recalibration...")                                                               
        try:                                                                                                          
            result = subprocess.run(                                                                                  
                ["python3", str(calibration_script), "--update"],                                                     
                capture_output=True,                                                                                  
                text=True,                                                                                            
                timeout=60                                                                                            
            )                                                                                                         
            if result.returncode == 0:                                                                                
                print("✓ Calibration factors updated")                                                                
            else:                                                                                                     
                print(f"⚠️ Calibration warning: {result.stderr[:200]}")                                               
        except Exception as e:                                                                                        
            print(f"⚠️ Could not run recalibration: {e}")                                                             
    else:                                                                                                             
        print("💡 Tip: Create calibration.py to auto-update calibration factors")                                     
        


def main():                                                                                                           
    parser = argparse.ArgumentParser(description="Auto-record tournament results")                                    
    parser.add_argument("--tournament", "-t", help="Filter to specific tournament")                                   
    parser.add_argument("--dry-run", "-n", action="store_true", help="Preview without saving")                        
                                                                                                                    
    args = parser.parse_args()                                                                                        
                                                                                                                    
    usage_data = load_usage_tracker()                                                                                 
    leaderboards = load_leaderboards()                                                                                
                                                                                                                    
    if leaderboards.empty:                                                                                            
        print("❌ No leaderboard data found at", LEADERBOARDS_FILE)                                                   
        print("   Run the leaderboard scraper first.")                                                                
        return                                                                                                        
                                                                                                                    
    # Show pending tournaments                                                                                        
    pending = find_pending_tournaments(usage_data)                                                                    
    if pending and not args.tournament:                                                                               
        print(f"\n📋 Pending tournaments: {', '.join(pending)}")                                                      
                                                                                                                    
    result = match_results(                                                                                           
        usage_data,                                                                                                   
        leaderboards,                                                                                                 
        tournament_filter=args.tournament,                                                                            
        dry_run=args.dry_run                                                                                          
    )                                                                                                                 
                                                                                                                    
    display_results(result)   
    
    if result.get("updates") and not args.dry_run:
        trigger_recalibration()                                                                             
                                                                                                                    
                                                                                                                    
if __name__ == "__main__":                                                                                            
      main()  