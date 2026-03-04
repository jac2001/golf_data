"""                                                                                                                   
Auto Record Results                                                                                                   
===================                                                                                                   
Automatically records tournament results and earnings for your picks.                                                              
                                                                                                                    
Usage:                                                                                                                
    python auto_record_results.py                           # Record pending results                                  
    python auto_record_results.py --tournament "WM Phoenix" # Specific tournament                                     
    python auto_record_results.py --dry-run                 # Preview without saving                                  
"""                                                                                                                   
                                                                                                                    
import argparse                                                                                                       
import json                                                                                                           
import pandas as pd                                                                                                   
import requests
from pathlib import Path                                                                                              
from datetime import datetime                                                                                         

try:
    from scripts.utils.tournament_context import resolve_tournament_context
except ModuleNotFoundError:
    import sys
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.utils.tournament_context import resolve_tournament_context
                                                                                                                    
DATA_DIR = Path(__file__).parent.parent.parent / "data"
OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"
SEASON_LOG_FILE = OUTPUTS_DIR / "season_log.csv"                                                               
USAGE_FILE = DATA_DIR / "fantasy" / "usage_tracker_2026.json"                                                         
LEADERBOARDS_FILE = DATA_DIR / "historical" / "leaderboards_2026.csv"                                                 
GRAPHQL_URL = "https://orchestrator.pgatour.com/graphql"
GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "x-pgat-platform": "web",
    "x-api-key": "da2-gsrx5bibzbb4njvhl7t37wqyl4",
    "Origin": "https://www.pgatour.com",
    "Referer": "https://www.pgatour.com/",
}
PAST_RESULTS_QUERY = """
query TournamentPastResults($tournamentId: ID!) {
  tournamentPastResults(id: $tournamentId) {
    id
    players {
      position
      total
      parRelativeScore
      additionalData
      player {
        id
        displayName
      }
    }
  }
}
"""


def parse_money(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    text = text.replace("$", "").replace(",", "")
    try:
        return int(round(float(text)))
    except Exception:
        return None

def load_usage_tracker() -> dict:                                                                                     
    if USAGE_FILE.exists():                                                                                           
        with open(USAGE_FILE) as f:                                                                                   
            return json.load(f)                                                                                       
    return {}                                                                                                         
                                                                                                                    
                                                                                                                    
def save_usage_tracker(data: dict):                                                                                   
    with open(USAGE_FILE, 'w') as f:                                                                                  
        json.dump(data, f, indent=2)                                                                                  
                                                                                                                    
                                                                                                                    
def load_leaderboards() -> pd.DataFrame:
    frames = []
    if LEADERBOARDS_FILE.exists():
        frames.append(pd.read_csv(LEADERBOARDS_FILE))

    # Also load any live leaderboard CSVs so recently-finished tournaments
    # don't need to wait for the historical scraper to run.
    live_dir = DATA_DIR / "live"
    if live_dir.exists():
        import re as _re
        for live_path in sorted(live_dir.glob("leaderboard_r*.csv")):
            if "_meta" in live_path.name:
                continue
            try:
                ldf = pd.read_csv(live_path)
                # Derive tournament_id from filename (e.g. leaderboard_r2026010.csv → R2026010)
                m = _re.search(r"leaderboard_(r\d+)", live_path.stem, _re.I)
                tid = m.group(1).upper() if m else ""
                ldf["tournament_id"] = tid
                # Normalise column names to match historical schema
                if "total" in ldf.columns and "to_par" not in ldf.columns:
                    ldf = ldf.rename(columns={"total": "to_par"})
                if "position" not in ldf.columns and "rank" in ldf.columns:
                    ldf = ldf.rename(columns={"rank": "position"})
                ldf["tournament_name"] = ""  # empty so fallback name-only match works
                frames.append(ldf[["tournament_id", "tournament_name", "player_name", "position", "to_par"]
                                   + [c for c in ["fedex_points", "total_score"] if c in ldf.columns]])
            except Exception:
                pass

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()                                                                                            


def fetch_pga_past_results(tournament_id: str, tournament_name: str) -> dict:
    """Fetch official final results/earnings for a single tournament from PGA TOUR."""
    if not tournament_id:
        return {}

    payload = {
        "query": PAST_RESULTS_QUERY,
        "variables": {"tournamentId": tournament_id},
        "operationName": "TournamentPastResults",
    }
    try:
        resp = requests.post(
            GRAPHQL_URL,
            headers=GRAPHQL_HEADERS,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            return {}
        players = ((data.get("data") or {}).get("tournamentPastResults") or {}).get("players") or []
    except Exception:
        return {}

    lookup = {}
    t_norm = normalize_tournament(tournament_name)
    for p in players:
        player = p.get("player") or {}
        p_norm = normalize_name(player.get("displayName", ""))
        if not p_norm:
            continue
        additional = p.get("additionalData") or []
        # additionalData[0] = FedEx Cup points (e.g. 500.000 for win)
        # additionalData[1] = prize money (e.g. '$1,728,000.00')
        # We track FedEx Cup points as the scoring currency
        fedex_pts_raw = additional[0] if len(additional) > 0 else None
        earnings = str(round(float(fedex_pts_raw))) if fedex_pts_raw is not None else None
        row = {
            "position": p.get("position"),
            "earnings": earnings,
            "to_par": p.get("parRelativeScore"),
            "source": "pga_past_results",
        }
        lookup[(t_norm, p_norm)] = row
    return lookup


def build_pga_past_results_lookup(usage_data: dict, tournament_filter: str = None) -> dict:
    """Build lookup for exact pending tournaments using PGA official past results."""
    target_tournaments = []
    filter_norm = normalize_tournament(tournament_filter) if tournament_filter else ""

    for player_data in usage_data.get("picks", {}).values():
        for t in player_data.get("tournaments_used", []):
            tournament = str(t.get("tournament", "")).strip()
            if not tournament:
                continue
            if t.get("result") is not None and t.get("earnings", t.get("points")) is not None:
                continue
            if filter_norm and filter_norm not in normalize_tournament(tournament):
                continue
            if tournament not in target_tournaments:
                target_tournaments.append(tournament)

    lookups = {}
    # Resolve exact schedule context, newest finished tournament first.
    resolved = []
    for tournament in target_tournaments:
        ctx = resolve_tournament_context(tournament_name=tournament)
        if not ctx.get("tournament_id"):
            continue
        resolved.append((ctx.get("end_date", ""), tournament, ctx))
    resolved.sort(reverse=True)

    for _, tracker_tournament, ctx in resolved:
        official_name = ctx.get("tournament_name") or tracker_tournament
        lookup = fetch_pga_past_results(ctx.get("tournament_id", ""), official_name)
        if not lookup:
            continue
        # Store under both the official schedule name and the tracker-entered name.
        tracker_norm = normalize_tournament(tracker_tournament)
        official_norm = normalize_tournament(official_name)
        for (t_norm, p_norm), row in lookup.items():
            lookups[(t_norm, p_norm)] = row
            if tracker_norm and tracker_norm != t_norm:
                lookups[(tracker_norm, p_norm)] = row
            if official_norm and official_norm != t_norm:
                lookups[(official_norm, p_norm)] = row
    return lookups
                                                                                                                    
                                                                                                                    
def normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    import unicodedata
    if not name:
        return ""
    name = str(name).strip().lower()
    # Transliterate non-ASCII letters (ø→o, å→a, ä→a, etc.)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    # Drop any remaining non-ASCII (covers ø, ð, þ, etc. that don't decompose)
    name = name.encode("ascii", "ignore").decode("ascii")
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
            if t.get("result") is None or t.get("earnings", t.get("points")) is None:
                tournament = t.get("tournament")
                if tournament and tournament not in pending:
                    pending.append(tournament)
    return pending 



def match_results(usage_data: dict, leaderboards: pd.DataFrame, 
                  tournament_filter: str=None, dry_run:bool=False) -> dict:
    """Match picks to leaderboard results and record them"""
    results_lookup = {}
    if not leaderboards.empty:
        for _, row in leaderboards.iterrows():
            t_name = normalize_tournament(row.get("tournament_name", ""))
            p_name = normalize_name(row.get("player_name", ""))
            key = (t_name, p_name)
            results_lookup[key] = {
                "position": row.get("position"),
                "earnings": row.get("earnings", "$0"),
                "to_par": row.get("to_par"),
            }

    pga_results_lookup = build_pga_past_results_lookup(usage_data, tournament_filter=tournament_filter)
    if not results_lookup and not pga_results_lookup:
        return {'error': 'No leaderboard or PGA past-results data available'}
        
    updates = []
    not_found = []
    already_recorded = []
    filter_norm = normalize_tournament(tournament_filter) if tournament_filter else ""
    
    picks = usage_data.get("picks", {})
    for player_name, player_data in picks.items():
        for t in player_data.get("tournaments_used", []):
            tournament = t.get("tournament", "")
            if filter_norm and filter_norm not in normalize_tournament(tournament):
                continue
            #Skip if already has result 
            
            if t.get("result") is not None and t.get("earnings", t.get("points")) is not None:
                already_recorded.append((player_name, tournament))
                continue
            
            #Look up result  
            t_norm = normalize_tournament(tournament)
            p_norm = normalize_name(player_name)
            
            #Try exact match first 
            key = (t_norm, p_norm)
            result = results_lookup.get(key)
            pga_result = pga_results_lookup.get(key)
            
            
            
            if not result:
                for (t_key, p_key), res in results_lookup.items():
                    if p_key == p_norm and (t_norm in t_key or t_key in t_norm):
                        result = dict(res)
                        result.setdefault("source", "leaderboard")
                        break 
            if not pga_result:
                for (t_key, p_key), res in pga_results_lookup.items():
                    if p_key == p_norm and (t_norm in t_key or t_key in t_norm):
                        pga_result = dict(res)
                        break

            if result and pga_result:
                if parse_money(result.get("earnings")) is None and parse_money(pga_result.get("earnings")) is not None:
                    result["earnings"] = pga_result.get("earnings")
                    result["source"] = "pga_past_results"
                else:
                    result.setdefault("source", "leaderboard")
                if not result.get("position") and pga_result.get("position"):
                    result["position"] = pga_result.get("position")
                if not result.get("to_par") and pga_result.get("to_par") is not None:
                    result["to_par"] = pga_result.get("to_par")
            elif not result and pga_result:
                result = dict(pga_result)
                result["source"] = "pga_past_results"
            elif result:
                result.setdefault("source", "leaderboard")
                    
            if result:                                                                                                
                position = result["position"]                                                                         
                earnings = parse_money(result.get("earnings"))
                                                                                                                    
                updates.append({                                                                                      
                    "player": player_name,                                                                            
                    "tournament": tournament,                                                                         
                    "position": position,                                                                             
                    "earnings": earnings,
                    "source": result.get("source", "unknown"),                                                                                 
                    "to_par": result.get("to_par"),                                                                   
                })                                                                                                    
                                                                                                                    
                if not dry_run:                                                                                       
                    t["result"] = str(position)                                                                       
                    t["earnings"] = earnings
                    t["points"] = earnings
                    t["result_source"] = result.get("source", "unknown")
            else:                                                                                                     
                not_found.append((player_name, tournament)) 
    
    if not dry_run and updates:
        for player_name, player_data in picks.items():
            total = sum((t.get("earnings", t.get("points")) or 0) for t in player_data.get("tournaments_used", []))
            player_data['total_earnings'] = total
            player_data['total_points'] = total
        for lineup in usage_data.get("weekly_lineups", {}).values():
            lineup_total = 0
            has_any = False
            tournament = lineup.get("tournament")
            for player_name in lineup.get("lineup", []):
                player_data = picks.get(player_name, {})
                for t in player_data.get("tournaments_used", []):
                    if t.get("tournament") == tournament:
                        earned = t.get("earnings", t.get("points"))
                        if earned is not None:
                            lineup_total += earned
                            has_any = True
                        break
            lineup["earnings_earned"] = lineup_total if has_any else None
            lineup["points_earned"] = lineup["earnings_earned"]
            
        usage_data['summary']['total_earnings'] = sum(
            p.get('total_earnings', 0) for p in picks.values()
        )          
        usage_data['summary']['total_points'] = usage_data['summary']['total_earnings']
        usage_data['last_updated'] = datetime.now().isoformat()
        save_usage_tracker(usage_data)
        _rebuild_season_log(usage_data)
        _upsert_picks_to_db(usage_data)
        _compute_clv(usage_data)

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
        print(f"  {'Player':<25} {'Tournament':<25} {'Finish':<8} {'Earnings':<12} {'Source':<16}")                                        
        print("  " + "-" * 65)                                                                                        
                                                                                                                    
        for u in updates:                                                                                             
            earned = parse_money(u["earnings"])
            earned_str = f"${earned:,.0f}" if earned is not None else "-"
            source_str = str(u.get("source", "unknown"))
            print(f"  {u['player']:<25} {u['tournament'][:25]:<25} {u['position']:<8} {earned_str:<12} {source_str:<16}")              
                                                                                                                    
        total_earnings = sum((u["earnings"] or 0) for u in updates)                                                                 
        print("  " + "-" * 65)                                                                                        
        print(f"  {'TOTAL':<25} {'':<25} {'':<8} ${total_earnings:,.0f}")                                                     
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
        




def _rebuild_season_log(usage_data: dict):
    """Rebuild outputs/season_log.csv from usage tracker data.

    Overwrites pick1/2/3, result1/2/3, and points for each week.
    Preserves league_rank, notes, rank1/2/3, avg_model_rank if they exist.
    """
    SEASON_LOG_COLS = [
        "week", "date", "tournament",
        "pick1", "pick2", "pick3",
        "result1", "result2", "result3",
        "points", "league_rank", "notes",
        "rank1", "rank2", "rank3", "avg_model_rank",
    ]

    # Load existing log to preserve manual columns
    existing = {}
    if SEASON_LOG_FILE.exists():
        try:
            existing_df = pd.read_csv(SEASON_LOG_FILE)
            for _, row in existing_df.iterrows():
                wk = int(row.get("week", 0))
                if wk:
                    existing[wk] = row.to_dict()
        except Exception:
            pass

    picks = usage_data.get("picks", {})
    rows = []
    for wk_key, wk in sorted(usage_data.get("weekly_lineups", {}).items()):
        week_num = int(wk.get("week", wk_key.replace("week_", "")))
        tournament = wk.get("tournament", "")
        date = wk.get("date", "")
        lineup = wk.get("lineup", [])

        # Pad lineup to 3
        while len(lineup) < 3:
            lineup.append("")

        pick1, pick2, pick3 = lineup[0], lineup[1], lineup[2]

        def _get_result(player: str) -> tuple:
            """Return (result_str, fedex_points) for player in this tournament."""
            if not player:
                return ("", 0)
            pinfo = picks.get(player, {})
            for t in pinfo.get("tournaments_used", []):
                if t.get("tournament") == tournament:
                    res = t.get("result")
                    pts = t.get("earnings", t.get("points")) or 0
                    if not res and pts == 0:
                        res = "CUT"
                    return (str(res) if res else "", int(pts))
            return ("", 0)

        r1, p1 = _get_result(pick1)
        r2, p2 = _get_result(pick2)
        r3, p3 = _get_result(pick3)
        total_pts = p1 + p2 + p3

        # Preserve manual columns from existing row
        prev = existing.get(week_num, {})

        row = {
            "week": week_num,
            "date": date,
            "tournament": tournament,
            "pick1": pick1,
            "pick2": pick2,
            "pick3": pick3,
            "result1": r1,
            "result2": r2,
            "result3": r3,
            "points": total_pts if total_pts else (prev.get("points", "")),
            "league_rank": prev.get("league_rank", ""),
            "notes": prev.get("notes", ""),
            "rank1": prev.get("rank1", ""),
            "rank2": prev.get("rank2", ""),
            "rank3": prev.get("rank3", ""),
            "avg_model_rank": prev.get("avg_model_rank", ""),
        }
        rows.append(row)

    if not rows:
        return

    df = pd.DataFrame(rows, columns=SEASON_LOG_COLS)
    df.to_csv(SEASON_LOG_FILE, index=False)
    print(f"    Season log updated: {len(df)} weeks written to {SEASON_LOG_FILE}")


def _upsert_picks_to_db(usage_data: dict):
    """Write picks + results to DuckDB picks table."""
    try:
        import sys as _sys
        _proj = Path(__file__).resolve().parents[2]
        if str(_proj) not in _sys.path:
            _sys.path.insert(0, str(_proj))
        from scripts.database.db import get_conn
    except Exception as e:
        print(f"    DB upsert skipped (could not import db): {e}")
        return

    picks = usage_data.get("picks", {})
    season = str(usage_data.get("season", "2026"))
    rows = []
    for wk_key, wk in usage_data.get("weekly_lineups", {}).items():
        week_num = int(wk.get("week", wk_key.replace("week_", "")))
        tid = wk.get("tournament_id", None)
        tournament = wk.get("tournament", "")
        pick_date = wk.get("date", None)
        for player in wk.get("lineup", []):
            if not player:
                continue
            pinfo = picks.get(player, {})
            tourney_result = next(
                (t for t in pinfo.get("tournaments_used", []) if t.get("tournament") == tournament),
                {}
            )
            result = tourney_result.get("result")
            fedex_points = tourney_result.get("earnings", tourney_result.get("points"))
            model_rank = tourney_result.get("model_rank", None)
            rows.append({
                "season": season,
                "week": week_num,
                "tournament_id": tid,
                "tournament": tournament,
                "pick_date": pick_date,
                "player_name": player,
                "result": result,
                "fedex_points": int(fedex_points) if fedex_points is not None else None,
                "model_rank": int(model_rank) if model_rank is not None else None,
            })

    if not rows:
        return

    df = pd.DataFrame(rows)
    cols = "season, week, tournament_id, tournament, pick_date, player_name, result, fedex_points, model_rank"
    try:
        with get_conn() as conn:
            conn.execute(f"INSERT OR REPLACE INTO picks ({cols}) SELECT {cols} FROM df")
        print(f"    DB picks upserted: {len(rows)} rows")
    except Exception as e:
        print(f"    DB upsert error: {e}")


def _compute_clv(usage_data: dict):
    """Compute closing line value for the most recently completed week's tournament."""
    try:
        import sys as _sys
        _proj = Path(__file__).resolve().parents[2]
        if str(_proj) not in _sys.path:
            _sys.path.insert(0, str(_proj))
        from scripts.validation.track_clv import run as clv_run
    except Exception as e:
        print(f"    CLV skipped (import error): {e}")
        return

    # Find the most recent week that has a tournament_id
    weeks = usage_data.get("weekly_lineups", {})
    tid, t_name = None, ""
    for wk in sorted(weeks.values(), key=lambda w: w.get("week", 0), reverse=True):
        if wk.get("tournament_id"):
            tid = wk["tournament_id"]
            t_name = wk.get("tournament", "")
            break

    if not tid:
        print("    CLV skipped: no tournament_id found in weekly_lineups")
        return

    print(f"\n  Computing CLV for {tid} ({t_name})...")
    clv_run(tid, t_name, save=True)


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
