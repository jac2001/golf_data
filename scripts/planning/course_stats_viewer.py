 #!/usr/bin/env python3                                                                                                
"""                                                                                                                   
Course Stats Viewer                                                                                                   
===================                                                                                                   
View PGA Tour course toughness and scoring statistics.                                                                
                                                                                                                    
Usage:                                                                                                                
    python course_stats_viewer.py                    # All courses ranked by toughness                                
    python course_stats_viewer.py --easiest          # Easiest courses (most scorable)                                
    python course_stats_viewer.py --course "Torrey"  # Search specific course                                         
"""                                                                                                                   
                                                                                                                    
import argparse                                                                                                       
import pandas as pd                                                                                                   
from pathlib import Path                                                                                              
                                                                                                                    
DATA_DIR = Path(__file__).parent.parent.parent / "data"                                                               
TOUGHNESS_FILE = DATA_DIR / "reference" / "course_toughness_latest.csv"                                               
                                                                                                                    
                                                                                                                    
def load_toughness() -> pd.DataFrame:                                                                                 
    if TOUGHNESS_FILE.exists():                                                                                       
        return pd.read_csv(TOUGHNESS_FILE)                                                                            
    return pd.DataFrame()                                                                                             
                                                                                                                    
                                                                                                                    
def display_toughest(top_n: int = 20):                                                                                
    """Display toughest courses."""                                                                                   
    df = load_toughness()                                                                                             
                                                                                                                    
    if df.empty:                                                                                                      
        print("No course toughness data found. Run fetch_course_toughness.py first.")                                 
        return                                                                                                        
                                                                                                                    
    df = df.sort_values('rank').head(top_n)                                                                           
                                                                                                                    
    print()                                                                                                           
    print("=" * 75)                                                                                                   
    print("  PGA TOUR COURSE TOUGHNESS RANKINGS")                                                                     
    print("=" * 75)                                                                                                   
    print(f"  Season: {df['year'].iloc[0]}")                                                                          
    print("=" * 75)                                                                                                   
    print()                                                                                                           
    print(f"  {'#':<4} {'Course':<35} {'Par':<5} {'Yards':<7} {'Avg':<8} {'+/-':<8}")                                 
    print("  " + "-" * 70)                                                                                            
                                                                                                                    
    for _, row in df.iterrows():                                                                                      
        course = row['course_name'][:35]                                                                              
        par = int(row['par']) if pd.notna(row['par']) else '-'                                                        
        yards = int(row['yards']) if pd.notna(row['yards']) else '-'                                                  
        avg = f"{row['scoring_avg']:.2f}" if pd.notna(row['scoring_avg']) else '-'                                    
        to_par = row['scoring_to_par']                                                                                
                                                                                                                    
        # Difficulty indicator                                                                                        
        if pd.notna(to_par):                                                                                          
            if to_par > -1:                                                                                           
                indicator = "🔴"                                                                                      
            elif to_par > -2:                                                                                         
                indicator = "🟠"                                                                                      
            elif to_par > -3:                                                                                         
                indicator = "🟡"                                                                                      
            else:                                                                                                     
                indicator = "🟢"                                                                                      
            to_par_str = f"{to_par:+.2f}"                                                                             
        else:                                                                                                         
            indicator = ""                                                                                            
            to_par_str = "-"                                                                                          
                                                                                                                    
        print(f"  {int(row['rank']):<4} {course:<35} {par:<5} {yards:<7} {avg:<8} {indicator} {to_par_str}")          
                                                                                                                    
    print()   
    
    
    
    
    
    
    
def display_easiest(top_n: int = 20):                                                                                 
    """Display easiest (most scorable) courses."""                                                                    
    df = load_toughness()                                                                                             
                                                                                                                    
    if df.empty:                                                                                                      
        print("No course toughness data found.")                                                                      
        return                                                                                                        
                                                                                                                    
    df = df.sort_values('scoring_to_par').head(top_n)                                                                 
                                                                                                                    
    print()                                                                                                           
    print("=" * 75)                                                                                                   
    print("  MOST SCORABLE COURSES (Birdie Fests)")                                                                   
    print("=" * 75)                                                                                                   
    print()                                                                                                           
    print(f"  {'Course':<40} {'Tournament':<25} {'+/-':<8}")                                                          
    print("  " + "-" * 70)                                                                                            
                                                                                                                    
    for _, row in df.iterrows():                                                                                      
        course = row['course_name'][:40]                                                                              
        tournament = row['tournament_name'][:25]                                                                      
        to_par = f"{row['scoring_to_par']:+.2f}"                                                                      
        print(f"  🟢 {course:<38} {tournament:<25} {to_par}")                                                         
                                                                                                                    
    print()                                                                                                           
                   
                   
                   
                   

def search_course(query: str):                                                                                        
    """Search for a specific course."""                                                                                
    df = load_toughness()
    
    if df.empty:
        print("No course toughness data found.")
        return
    matches = df[df['course_name'].str.lower().str.contains(query.lower(), na=False)]
    if matches.empty:                                                                                                 
          matches = df[df['tournament_name'].str.lower().str.contains(query.lower(), na=False)]                         
                                                                                                                        
    if matches.empty:                                                                                                 
        print(f"No courses found matching '{query}'")                                                                 
        return                                                                                                        
                                                                                                                        
    print()                                                                                                           
    print("=" * 75)                                                                                                   
    print(f"  COURSE STATS: {query.upper()}")                                                                         
    print("=" * 75)                                                                                                   
    print()
    for _, row in matches.iterrows():                                                                                 
        print(f"  📍 {row['course_name']}")                                                                           
        print(f"     Tournament: {row['tournament_name']}")                                                           
        print(f"     Par: {int(row['par'])}  |  Yards: {int(row['yards']):,}")                                        
        print(f"     Scoring Avg: {row['scoring_avg']:.3f}")                                                          
        print(f"     To Par: {row['scoring_to_par']:+.3f}")                                                           
        print(f"     Toughness Rank: #{int(row['rank'])}")                                                            
        print()                                                                                                       
                                                                                                                    
        # Scoring breakdown                                                                                           
        print(f"     Scoring Breakdown:")                                                                             
        print(f"       Eagles+:    {int(row['eagle_or_better']):,}")                                                  
        print(f"       Birdies:    {int(row['birdies']):,}")                                                          
        print(f"       Pars:       {int(row['pars']):,}")                                                             
        print(f"       Bogeys:     {int(row['bogeys']):,}")                                                           
        print(f"       Dbl Bogey+: {int(row['dbl_bogeys']) + int(row['dbl_bogey_plus']):,}")                          
        print()
    
                   


def main():
    parser = argparse.ArgumentParser(description="View course stats")
    parser.add_argument("--easiest", action="store_true", help="Display easiest courses")
    parser.add_argument("--course", help="Search for a specific course")
    args = parser.parse_args()
    
    if args.easiest:
        display_easiest()
    elif args.course:
        search_course(args.course)
    else:
        display_toughest()
if __name__ == "__main__":
    main()