"""
Weekly Prep Automation
======================
Runs all scrapers to prepare data for the current week's tournament.
 Usage:                                                                                                                
      python3 weekly_prep.py                    # Run all scrapers                                                       
      python3 weekly_prep.py --quick            # Essential scrapers only                                                
      python3 weekly_prep.py --dry-run          # Show what would run                                                    
      python3 weekly_prep.py --tournament "WM Phoenix Open"  # Specific tournament                                       
 """  
 
 
 
import argparse
import subprocess 
import sys 
import pandas as pd 
from datetime import datetime 
from pathlib import Path 


PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
SCRAPERS_DIR = SCRIPTS_DIR / 'scrapers'


# Tournament name to power rankings slug mapping
POWER_RANKINGS_SLUGS = {
    "The Sentry": "the_sentry_2026",
    "Sony Open in Hawaii": "sony_open_2026",
    "The American Express": "american_express_2026",
    "Farmers Insurance Open": "farmers_2026",
    "AT&T Pebble Beach Pro-Am": "pebble_beach_2026",
    "WM Phoenix Open": "wm_phoenix_open_2026",
    "The Genesis Invitational": "genesis_2026",
    "Mexico Open at VidantaWorld": "mexico_open_2026",
    "Cognizant Classic in The Palm Beaches": "cognizant_classic_2026",
    "Arnold Palmer Invitational presented by Mastercard": "api_2026",
    "THE PLAYERS Championship": "players_2026",
    "Valspar Championship": "valspar_2026",
    "Texas Children's Houston Open": "houston_open_2026",
    "Valero Texas Open": "texas_open_2026",
    "Masters Tournament": "masters_2026",
    "RBC Heritage": "rbc_heritage_2026",
}

# Tournament name to URL slug for betting profile articles
BETTING_ARTICLE_SLUGS = {
    "The Sentry": "the-sentry",
    "Sony Open in Hawaii": "sony-open-in-hawaii",
    "The American Express": "the-american-express",
    "Farmers Insurance Open": "farmers-insurance-open",
    "AT&T Pebble Beach Pro-Am": "at-t-pebble-beach-pro-am",
    "WM Phoenix Open": "wm-phoenix-open",
    "The Genesis Invitational": "the-genesis-invitational",
    "Mexico Open at VidantaWorld": "mexico-open-at-vidantaworld",
    "Cognizant Classic in The Palm Beaches": "cognizant-classic",
    "Arnold Palmer Invitational presented by Mastercard": "arnold-palmer-invitational",
    "THE PLAYERS Championship": "the-players-championship",
    "Valspar Championship": "valspar-championship",
    "Texas Children's Houston Open": "texas-childrens-houston-open",
    "Valero Texas Open": "valero-texas-open",
    "Masters Tournament": "masters-tournament",
    "RBC Heritage": "rbc-heritage",
}


def get_power_rankings_slug(tournament_name: str) -> str:
    """Get power rankings slug for a tournament name."""
    if not tournament_name:
        return ""

    # Direct lookup
    if tournament_name in POWER_RANKINGS_SLUGS:
        return POWER_RANKINGS_SLUGS[tournament_name]

    # Try partial match
    name_lower = tournament_name.lower()
    for t_name, slug in POWER_RANKINGS_SLUGS.items():
        if t_name.lower() in name_lower or name_lower in t_name.lower():
            return slug

    # Generate a slug from the name as fallback
    slug = tournament_name.lower()
    slug = slug.replace("&", "").replace("'", "").replace(".", "")
    slug = "_".join(slug.split())
    slug = f"{slug}_2026"
    return slug


def get_betting_article_slug(tournament_name: str) -> str:
    """Get betting article URL slug for a tournament name."""
    if not tournament_name:
        return ""

    # Direct lookup
    if tournament_name in BETTING_ARTICLE_SLUGS:
        return BETTING_ARTICLE_SLUGS[tournament_name]

    # Try partial match
    name_lower = tournament_name.lower()
    for t_name, slug in BETTING_ARTICLE_SLUGS.items():
        if t_name.lower() in name_lower or name_lower in t_name.lower():
            return slug

    # Generate a slug from the name as fallback
    slug = tournament_name.lower()
    slug = slug.replace("&", "").replace("'", "").replace(".", "")
    slug = "-".join(slug.split())
    return slug



def get_current_tournament() -> dict:
    """Get current tournament info from schedule."""
    schedule_file = DATA_DIR / "raw" / "schedule_2026.csv"
    if not schedule_file.exists():
        return None

    schedule = pd.read_csv(schedule_file)
    today = datetime.now().strftime("%Y-%m-%d")

    upcoming = schedule[schedule['start_date'] >= today]
    if not upcoming.empty:
        row = upcoming.iloc[0]
        return {
            "name": row['tournament_name'],
            "id": row.get('tournament_id', ''),
            "week": row.get('week', 0),
            "start_date": row.get('start_date', ''),
        }
    return None 


def run_scraper(name: str, args: list = None, dry_run: bool = False) -> dict:                                         
    """Run a scraper and return result."""                                                                            
    script_path = SCRAPERS_DIR / name                                                                                 
                                                                                                                    
    if not script_path.exists():                                                                                      
        return {"name": name, "status": "not_found", "error": f"Script not found: {script_path}"}                     
                                                                                                                    
    cmd = [sys.executable, str(script_path)] + (args or [])                                                           
                                                                                                                    
    if dry_run:                                                                                                       
        return {"name": name, "status": "dry_run", "command": " ".join(cmd)}                                          
                                                                                                                    
    print(f"\n{'='*60}")                                                                                              
    print(f"  Running: {name}")                                                                                       
    print(f"{'='*60}")                                                                                                
                                                                                                                    
    try:                                                                                                              
        result = subprocess.run(                                                                                      
            cmd,                                                                                                      
            capture_output=True,                                                                                      
            text=True,                                                                                                
            timeout=120,                                                                                              
            cwd=str(PROJECT_ROOT)                                                                                     
        )                                                                                                             
                                                                                                                    
        if result.returncode == 0:                                                                                    
            print(f"  ✅ Success")                                                                                    
            if result.stdout:                                                                                         
                # Show last few lines of output                                                                       
                lines = result.stdout.strip().split('\n')                                                             
                for line in lines[-5:]:                                                                               
                    print(f"     {line}")                                                                             
            return {"name": name, "status": "success", "output": result.stdout}                                       
        else:                                                                                                         
            print(f"  ❌ Failed")                                                                                     
            if result.stderr:                                                                                         
                print(f"     {result.stderr[:200]}")                                                                  
            return {"name": name, "status": "failed", "error": result.stderr}                                         
                                                                                                                    
    except subprocess.TimeoutExpired:                                                                                 
        print(f"  ⚠️ Timeout (120s)")                                                                                 
        return {"name": name, "status": "timeout"}                                                                    
    except Exception as e:                                                                                            
        print(f"  ❌ Error: {e}")                                                                                     
        return {"name": name, "status": "error", "error": str(e)}                                                     
                                                                                                                    
                                                                                                                    
                                                                                                                    
                                                                                                                    
def run_weekly_prep(tournament_name: str = None, quick: bool = False, dry_run: bool = False):
    """Run all weekly prep scrapers."""

    # Get tournament info
    tourney_info = get_current_tournament()

    if tournament_name:
        # Override with provided name
        tourney_info = tourney_info or {}
        tourney_info["name"] = tournament_name

    t_name = tourney_info.get("name", "Unknown") if tourney_info else "Unknown"
    t_id = tourney_info.get("id", "") if tourney_info else ""

    print()
    print("=" * 60)
    print("  WEEKLY PREP AUTOMATION")
    print("=" * 60)
    print(f"  Tournament: {t_name}")
    print(f"  Tournament ID: {t_id}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'QUICK' if quick else 'FULL'}")
    print("=" * 60)

    if not t_id:
        print("  ⚠️  Warning: No tournament ID found. Some scrapers may fail.")

    # Build field output path
    field_output = str(DATA_DIR / "fields" / f"field_{t_id}.csv") if t_id else ""
    current_year = datetime.now().year
    recent_years = [str(current_year - 2), str(current_year - 1), str(current_year)]

    # Build paths for betting profile articles
    betting_slug = get_betting_article_slug(t_name)
    betting_articles_output = str(DATA_DIR / "betting_profiles" / f"articles_{t_id}.csv") if t_id else ""
    betting_articles_template = (
        f"https://www.pgatour.com/article/news/betting-profile/2026/{betting_slug}/"
        "{name_slug}-pga-tour-betting-stats-" + f"{betting_slug}-2026"
    ) if betting_slug else ""

    # Define scrapers to run with proper arguments
    if quick:
        scrapers = [
            ("fetch_field_from_pgatour.py", ["--pga-id", t_id, "--output", field_output, "--name", t_name] if t_id else []),
            ("fetch_pga_odds.py", ["--tournament-id", t_id] if t_id else []),
            ("fetch_tournament_stats.py", ["--year", str(current_year), "--refresh-latest", "3"]),
            ("../features/consolidate_course_form_stats.py", ["--years", *recent_years]),
            ("../features/course_similarity.py", []),
            # Note: PGA expert picks require --path arg; run via run_pipeline.py flow when needed.
        ]
    else:
        scrapers = [
            ("fetch_field_from_pgatour.py", ["--pga-id", t_id, "--output", field_output, "--name", t_name] if t_id else []),
            ("fetch_world_rankings.py", []),
            ("fetch_form_stats.py", ["--year", str(current_year), "--quick"]),
            ("fetch_tournament_stats.py", ["--year", str(current_year), "--refresh-latest", "3"]),
            ("../features/consolidate_course_form_stats.py", ["--years", *recent_years]),
            ("../features/course_similarity.py", []),
            ("fetch_betting_profiles.py", ["--tournament-id", t_id, "--field", field_output] if t_id else []),
            ("fetch_pga_odds.py", ["--tournament-id", t_id] if t_id else []),
            # Note: PGA expert picks require --path arg; run via run_pipeline.py flow when needed.
            ("fetch_betting_profile_articles.py", [
                "--field-csv", field_output,
                "--url-template", betting_articles_template,
                "--output", betting_articles_output
            ] if field_output and betting_articles_template else []),
            ("fetch_power_rankings.py", ["--slug", get_power_rankings_slug(t_name), "--allow-fail"]),
            ("fetch_course_toughness.py", ["--year", "2026"]),
        ]                                                                                                             
                                                                                                                    
    results = []                                                                                                      
                                                                                                                    
    for script_name, args in scrapers:                                                                                
        result = run_scraper(script_name, args, dry_run=dry_run)                                                      
        results.append(result)                                                                                        
                                                                                                                    
    # Summary                                                                                                         
    print()                                                                                                           
    print("=" * 60)                                                                                                   
    print("  SUMMARY")                                                                                                
    print("=" * 60)                                                                                                   
                                                                                                                    
    success = sum(1 for r in results if r["status"] == "success")                                                     
    failed = sum(1 for r in results if r["status"] in ["failed", "error", "timeout"])                                 
                                                                                                                    
    print(f"  ✅ Succeeded: {success}/{len(results)}")                                                                
    if failed:                                                                                                        
        print(f"  ❌ Failed: {failed}/{len(results)}")                                                                
        for r in results:                                                                                             
            if r["status"] in ["failed", "error", "timeout"]:                                                         
                print(f"     - {r['name']}: {r['status']}")                                                           
                                                                                                                    
    if dry_run:                                                                                                       
        print()                                                                                                       
        print("  Commands that would run:")                                                                           
        for r in results:                                                                                             
            if "command" in r:                                                                                        
                print(f"    $ {r['command']}")                                                                        
                                                                                                                    
    print()                                                                                                           
                                                                                                                    
    # Suggest next steps                                                                                              
    if not dry_run and success > 0:                                                                                   
        print("  📋 Next steps:")                                                                                     
        print("     1. Run predictions: python scripts/run_pipeline.py")                                              
        print("     2. Open dashboard: streamlit run dashboard.py")                                                   
        print()                                                                                                       
                                                                                                                    
    return results                                                                                                    
                                                                                                                    
                                                                                                                    
def main():                                                                                                           
    parser = argparse.ArgumentParser(description="Weekly prep automation")                                            
    parser.add_argument("--tournament", "-t", help="Tournament name")                                                 
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode (essential scrapers only)")            
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would run")                           
                                                                                                                    
    args = parser.parse_args()                                                                                        
                                                                                                                    
    run_weekly_prep(
        tournament_name=args.tournament,
        quick=args.quick,
        dry_run=args.dry_run
    )                                                                                                                 
                                                                                                                    
                                                                                                                    
if __name__ == "__main__":                                                                                            
    main()                                                                                                                
                                                                                                                    
