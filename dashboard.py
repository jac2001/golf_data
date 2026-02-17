#!/usr/bin/env python3
"""
Golf Fantasy Dashboard
======================

Interactive dashboard for fantasy golf strategy and predictions.

Usage:
    streamlit run dashboard.py
    streamlit run dashboard.py --server.port 8501
"""

import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import subprocess
import textwrap
from datetime import datetime
import plotly.express as px
import requests
import re

try:
    from scripts.props.prop_odds_edges import (
        load_latest_prop_lines,
        score_book_props,
        score_parlay,
    )
    prop_edge_tools_available = True
except Exception:
    load_latest_prop_lines = None
    score_book_props = None
    score_parlay = None
    prop_edge_tools_available = False

# Market availability and betting recommendations
try:
    from scripts.models.market_availability import (
        scan_all_availability,
        load_availability,
        get_staleness_badge,
        get_source_label,
        MarketType,
        DataSource,
        Staleness,
    )
    market_availability_available = True
except Exception:
    market_availability_available = False

try:
    from scripts.models.betting_recommendations import (
        generate_recommendations,
        get_edge_summary,
        format_slip_for_display,
        RiskProfile,
    )
    betting_recs_available = True
except Exception:
    betting_recs_available = False

# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
DATA_DIR = PROJECT_ROOT / "data"
PLANNING_DIR = PROJECT_ROOT / "scripts" / "planning"

# Add planning dir to path for imports
sys.path.insert(0, str(PLANNING_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "predictions"))

# Page config
st.set_page_config(
    page_title="Golf Fantasy Dashboard",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* Headers */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e4d2b;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        margin-top: 0;
    }

    /* Metrics */
    .stMetric {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #1e4d2b;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: bold;
    }

    /* Compact tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
    }

    /* Chat styling */
    [data-testid="stChatMessage"] {
        padding: 0.75rem 1rem;
    }
    [data-testid="stChatMessage"] table {
        font-size: 0.85rem;
    }

    /* Player cards */
    .player-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #1e4d2b;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .player-card:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .player-name {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e4d2b;
        margin-bottom: 0.25rem;
    }
    .player-odds {
        font-size: 1.3rem;
        font-weight: bold;
        color: #2c5530;
    }

    /* Probability badges */
    .prob-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .prob-high {
        background-color: #d4edda;
        color: #155724;
    }
    .prob-mid {
        background-color: #fff3cd;
        color: #856404;
    }
    .prob-low {
        background-color: #f8f9fa;
        color: #6c757d;
    }

    /* Odds comparison table */
    .odds-table {
        width: 100%;
        border-collapse: collapse;
    }
    .odds-table th {
        background-color: #1e4d2b;
        color: white;
        padding: 0.75rem;
        text-align: left;
    }
    .odds-table td {
        padding: 0.75rem;
        border-bottom: 1px solid #dee2e6;
    }
    .odds-table tr:hover {
        background-color: #f8f9fa;
    }
    .best-odds {
        background-color: #d4edda !important;
        font-weight: bold;
    }
    .odds-diff {
        color: #dc3545;
        font-weight: bold;
    }

    /* Quick action bar */
    .action-bar {
        background: linear-gradient(90deg, #1e4d2b 0%, #2c5530 100%);
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }

    /* Status indicators */
    .status-live {
        color: #28a745;
        font-weight: bold;
    }
    .status-updated {
        color: #6c757d;
        font-size: 0.85rem;
    }

    /* Favorite star */
    .favorite-btn {
        cursor: pointer;
        font-size: 1.2rem;
    }
    /* Expert picks cards */
    .expert-card {
        background: linear-gradient(135deg, #f0f7f0 0%, #e8f5e9 100%);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border-left: 4px solid #2e7d32;
    }
    .expert-name {
        font-weight: 600;
        color: #1b5e20;
    }
    .consensus-bar {
        background: #e0e0e0;
        border-radius: 10px;
        height: 8px;
        overflow: hidden;
    }
    .consensus-fill {
        background: linear-gradient(90deg, #4caf50 0%, #2e7d32 100%);
        height: 100%;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SCRIPT RUNNER
# ============================================================================

def run_script(script_name: str, *args) -> str:
    """Run a script and return its output."""
    script_path = PROJECT_ROOT / "scripts" / script_name
    cmd = ["python3", str(script_path)] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        output = result.stdout
        if result.stderr and not output:
            output = result.stderr
        return output.strip() if output else "No output"
    except subprocess.TimeoutExpired:
        return "⚠️ Script timed out after 30 seconds"
    except Exception as e:
        return f"⚠️ Error running script: {e}"


# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_resource
def load_scoring_engine():
    """Load the scoring engine with caching."""
    try:
        from scripts.planning.scoring_engine import ScoringEngine
        return ScoringEngine()
    except Exception as e:
        st.error(f"Failed to load scoring engine: {e}")
        return None


def load_golf_assistant():
    """Load the Golf Assistant for chat functionality (no caching during dev)."""
    try:
        from scripts.predictions.golf_assistant import GolfAssistant
        return GolfAssistant(format_name="earnings")
    except Exception as e:
        st.warning(f"Golf Assistant not available: {e}")
        return None


@st.cache_data(ttl=60)
def load_usage_data():
    """Load usage tracker data."""
    usage_file = DATA_DIR / "fantasy" / "usage_tracker_2026.json"
    if usage_file.exists():
        with open(usage_file) as f:
            return json.load(f)
    return {"picks": {}, "weekly_lineups": {}, "summary": {}}


@st.cache_data(ttl=300)
def load_schedule():
    """Load tournament schedule."""
    schedule_file = DATA_DIR / "raw" / "schedule_2026.csv"
    if schedule_file.exists():
        return pd.read_csv(schedule_file)
    return pd.DataFrame()


def _name_key(name: str) -> str:
    """Normalize player name for loose matching across sources."""
    if pd.isna(name):
        return ""
    cleaned = str(name).replace(",", " ").replace(".", " ").replace("-", " ").lower().strip()
    tokens = [t for t in cleaned.split() if t]
    # Remove common suffixes.
    tokens = [t for t in tokens if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    tokens.sort()
    return " ".join(tokens)


def ensure_player_name_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a DataFrame has a usable `player_name` column.
    Handles common alternate column names and id-only rows.
    """
    out = df.copy()
    if "player_name" not in out.columns:
        alternatives = [
            "player",
            "Player",
            "name",
            "Name",
            "playerName",
            "displayName",
            "golfer",
            "PLAYER",
        ]
        source_col = next((c for c in alternatives if c in out.columns), None)
        if source_col:
            out["player_name"] = out[source_col]
        elif "player_id" in out.columns:
            out["player_name"] = out["player_id"].apply(
                lambda v: f"Player {int(v)}" if pd.notna(v) else ""
            )
        else:
            out["player_name"] = ""
    else:
        out["player_name"] = out["player_name"].fillna("")

    if "player_id" in out.columns:
        missing_mask = out["player_name"].astype(str).str.strip().eq("")
        if missing_mask.any():
            out.loc[missing_mask, "player_name"] = out.loc[missing_mask, "player_id"].apply(
                lambda v: f"Player {int(v)}" if pd.notna(v) else ""
            )

    out["player_name"] = out["player_name"].astype(str).str.strip()
    return out


# ============================================================================
# ODDS COMPARISON HELPERS
# ============================================================================

def load_odds_from_source(source: str) -> pd.DataFrame:
    """Load odds data from a specific source."""
    odds_dir = DATA_DIR / "odds"
    if source == "polymarket":
        files = list(odds_dir.glob("polymarket_*.csv"))
    elif source == "kalshi":
        files = list(odds_dir.glob("kalshi_*.csv"))
    else:
        files = [odds_dir / "multi_book_odds_latest.csv"]

    if files:
        # Get most recent file
        latest = max(files, key=lambda f: f.stat().st_mtime)
        return pd.read_csv(latest)
    return pd.DataFrame()


def merge_odds_sources() -> pd.DataFrame:
    """Merge odds from Polymarket and Kalshi for comparison."""
    poly_df = load_odds_from_source("polymarket")
    kalshi_df = load_odds_from_source("kalshi")

    if poly_df.empty and kalshi_df.empty:
        return pd.DataFrame()

    # Normalize player names for matching
    def normalize_name(name):
        return str(name).lower().strip().replace(".", "").replace("-", " ")

    if not poly_df.empty:
        poly_df["name_key"] = poly_df["player_name"].apply(normalize_name)
        poly_df = poly_df.rename(columns={
            "odds_polymarket": "polymarket_odds",
            "win_prob": "polymarket_prob"
        })

    if not kalshi_df.empty:
        kalshi_df["name_key"] = kalshi_df["player_name"].apply(normalize_name)
        kalshi_df = kalshi_df.rename(columns={
            "odds_kalshi": "kalshi_odds",
            "win_prob": "kalshi_prob"
        })

    # Merge on normalized name
    if not poly_df.empty and not kalshi_df.empty:
        merged = pd.merge(
            poly_df[["player_name", "name_key", "polymarket_odds", "polymarket_prob"]],
            kalshi_df[["name_key", "kalshi_odds", "kalshi_prob"]],
            on="name_key",
            how="outer"
        )
    elif not poly_df.empty:
        merged = poly_df[["player_name", "name_key", "polymarket_odds", "polymarket_prob"]].copy()
        merged["kalshi_odds"] = None
        merged["kalshi_prob"] = None
    else:
        merged = kalshi_df[["player_name", "name_key", "kalshi_odds", "kalshi_prob"]].copy()
        merged["polymarket_odds"] = None
        merged["polymarket_prob"] = None

    # Fill missing player names from kalshi for rows that only exist in kalshi
    if not kalshi_df.empty:
        kalshi_name_map = kalshi_df.set_index("name_key")["player_name"].to_dict()
        # Fill NaN player names using the kalshi mapping
        merged["player_name"] = merged.apply(
            lambda row: kalshi_name_map.get(row["name_key"], row["player_name"])
            if pd.isna(row.get("player_name")) else row["player_name"],
            axis=1
        )

    # Drop any rows still without a player name
    merged = merged[merged["player_name"].notna()]

    # Calculate best odds and consensus
    merged["best_odds"] = merged[["polymarket_odds", "kalshi_odds"]].max(axis=1)
    merged["avg_prob"] = merged[["polymarket_prob", "kalshi_prob"]].mean(axis=1)

    # Calculate odds difference
    merged["odds_diff"] = abs(
        merged["polymarket_odds"].fillna(0) - merged["kalshi_odds"].fillna(0)
    )

    # Sort by average probability
    merged = merged.sort_values("avg_prob", ascending=False).reset_index(drop=True)
    merged["rank"] = range(1, len(merged) + 1)

    return merged


def prob_to_badge_class(prob: float) -> str:
    """Get CSS class for probability badge."""
    if prob >= 0.10:
        return "prob-high"
    elif prob >= 0.03:
        return "prob-mid"
    return "prob-low"


def format_odds_display(odds: float, is_best: bool = False) -> str:
    """Format odds for display with optional highlighting."""
    if pd.isna(odds) or odds == 0:
        return "—"
    sign = "+" if odds > 0 else ""
    if is_best:
        return f"**{sign}{int(odds)}** ✓"
    return f"{sign}{int(odds)}"


def render_odds_comparison_table(df: pd.DataFrame, max_rows: int = 25):
    """Render an interactive odds comparison table."""
    if df.empty:
        st.info("No odds data available. Fetch from Polymarket or Kalshi first.")
        return

    st.caption(f"{len(df)} players with odds from prediction markets")

    # Create display dataframe
    display_data = []
    for _, row in df.head(max_rows).iterrows():
        poly_odds = row.get("polymarket_odds")
        kalshi_odds = row.get("kalshi_odds")
        best = row.get("best_odds")

        # Determine which is best
        poly_is_best = pd.notna(poly_odds) and poly_odds == best
        kalshi_is_best = pd.notna(kalshi_odds) and kalshi_odds == best
        if poly_is_best and kalshi_is_best:
            best_market = "Tie"
        elif poly_is_best:
            best_market = "Polymarket"
        elif kalshi_is_best:
            best_market = "Kalshi"
        else:
            best_market = "—"

        display_data.append({
            "Rank": int(row["rank"]),
            "Player": row["player_name"],
            "Polymarket": format_odds_display(poly_odds),
            "Kalshi": format_odds_display(kalshi_odds),
            "Best Market": best_market,
            "Best Odds": format_odds_display(best),
            "Win %": f"{row['avg_prob']*100:.1f}%" if pd.notna(row.get('avg_prob')) else "—",
            "Diff": int(row["odds_diff"]) if pd.notna(row.get("odds_diff")) else 0
        })

    display_df = pd.DataFrame(display_data)
    st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=520,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="medium"),
            "Polymarket": st.column_config.TextColumn(width="small"),
            "Kalshi": st.column_config.TextColumn(width="small"),
            "Best Market": st.column_config.TextColumn(width="small"),
            "Best Odds": st.column_config.TextColumn(width="small"),
            "Win %": st.column_config.TextColumn(width="small"),
            "Diff": st.column_config.NumberColumn(width="small"),
        },
    )




def render_player_odds_card(player_name: str, poly_odds: float, kalshi_odds: float,
                            avg_prob: float, rank: int):
    """Render a visual player card with odds using native Streamlit components."""
    # Handle NaN values
    poly_val = poly_odds if pd.notna(poly_odds) else 0
    kalshi_val = kalshi_odds if pd.notna(kalshi_odds) else 0
    best_odds = max(poly_val, kalshi_val)
    best_display = f"+{int(best_odds)}" if best_odds > 0 else "—"
    avg_prob_display = f"{avg_prob*100:.1f}%" if pd.notna(avg_prob) else "—"

    with st.container():
        st.markdown(f"**#{rank} {player_name}**")
        st.metric("Win Probability", avg_prob_display)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Polymarket", format_odds_display(poly_odds))
        with c2:
            st.metric("Kalshi", format_odds_display(kalshi_odds))
        with c3:
            st.metric("Best Odds", best_display, delta="Best" if best_odds > 0 else None)





def calculate_value_score(poly_odds: float, kalshi_odds: float) -> dict:
    """Calculate value score based on odds difference between markets"""
    poly_val = poly_odds if pd.notna(poly_odds) else 0
    kalshi_val = kalshi_odds if pd.notna(kalshi_odds) else 0
    
    
    if poly_val == 0 or kalshi_val == 0:
        return {"score": 0, "better_market": None, "edge_pct": 0}
    
    diff = abs(poly_val - kalshi_val)
    avg = (poly_val + kalshi_val) / 2
    edge_pct = (diff / avg) * 100 if avg > 0 else 0
    
    if poly_val > kalshi_val:
        better_market = "Polymarket"
        better_odds = poly_val
    else:
        better_market = "Kalshi"
        better_odds = kalshi_val
        
    score = min(100, edge_pct * 2)
    
    return {
        "score": round(score, 1),
        "better_market": better_market,
        "edge_pct": round(edge_pct, 1),
        "better_odds": better_odds,
        'diff': diff
    }
    
def render_value_finder(comparison_df: pd.DataFrame):
    """Render the value finder section using native Streamlit components."""
    if comparison_df.empty:
        st.info("No odds data. Fetch from Polymarket and Kalshi first.")
        return

    st.markdown("#### 💎 Value Finder")
    st.caption("Players where one market offers significantly better odds")

    # Calculate value for each player
    value_data = []
    for _, row in comparison_df.iterrows():
        value = calculate_value_score(
            row.get("polymarket_odds"),
            row.get("kalshi_odds")
        )
        if value["score"] > 10:  # Only show meaningful differences
            value_data.append({
                "Player": row["player_name"],
                "Polymarket": f"+{int(row['polymarket_odds'])}" if pd.notna(row.get('polymarket_odds')) else "—",
                "Kalshi": f"+{int(row['kalshi_odds'])}" if pd.notna(row.get('kalshi_odds')) else "—",
                "Best Market": value["better_market"],
                "Edge %": f"{value['edge_pct']}%",
                "Value Score": value["score"],
            })

    if not value_data:
        st.success("No significant value gaps found - markets are well aligned!")
        return

    value_df = pd.DataFrame(value_data)
    value_df = value_df.sort_values("Value Score", ascending=False)

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Value Opportunities", len(value_df))
    with col2:
        poly_better = len([v for v in value_data if v["Best Market"] == "Polymarket"])
        st.metric("Polymarket Better", poly_better)
    with col3:
        kalshi_better = len(value_df) - poly_better
        st.metric("Kalshi Better", kalshi_better)

    # Top value plays using native components
    st.markdown("##### 🔥 Top Value Plays")
    for _, row in value_df.head(5).iterrows():
        better = row["Best Market"]
        indicator = "🟣" if better == "Polymarket" else "🟠"
        with st.container():
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                st.markdown(f"**{row['Player']}**")
            with c2:
                st.caption(f"Poly: {row['Polymarket']}")
            with c3:
                st.caption(f"Kalshi: {row['Kalshi']}")
            with c4:
                st.metric(f"{indicator} {better}", row['Edge %'])

    # Full table
    with st.expander("View All Value Opportunities"):
        st.dataframe(value_df, hide_index=True, use_container_width=True)






def save_odds_snapshot():                                                                                                
    """Save current odds as a timestamped snapshot."""                                                                   
    snapshot_dir = DATA_DIR / "odds" / "snapshots"                                                                       
    snapshot_dir.mkdir(parents=True, exist_ok=True)                                                                      
                                                                                                                        
    # Load current odds                                                                                                  
    comparison_df = merge_odds_sources()                                                                                 
    if comparison_df.empty:                                                                                              
        return None                                                                                                      
                                                                                                                        
    # Save with timestamp                                                                                                
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")                                                                   
    snapshot_path = snapshot_dir / f"odds_{timestamp}.csv"                                                               
    comparison_df.to_csv(snapshot_path, index=False)                                                                     
                                                                                                                        
    return snapshot_path  


def load_odds_history(player_name: str, days: int = 7) -> pd.DataFrame:                                                  
    """Load historical odds for a specific player."""                                                                    
    snapshot_dir = DATA_DIR / "odds" / "snapshots"                                                                       
    if not snapshot_dir.exists():                                                                                        
        return pd.DataFrame()                                                                                            
                                                                                                                        
    # Get all snapshots                                                                                                  
    snapshots = sorted(snapshot_dir.glob("odds_*.csv"))                                                                  
                                                                                                                        
    history = []                                                                                                         
    for snap in snapshots[-50:]:  # Last 50 snapshots max                                                                
        try:                                                                                                             
            # Parse timestamp from filename                                                                              
            ts_str = snap.stem.replace("odds_", "")                                                                      
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M")                                                                
                                                                                                                        
            df = pd.read_csv(snap)                                                                                       
            # Normalize name for matching                                                                                
            df["name_lower"] = df["player_name"].str.lower().str.strip()                                                 
            player_row = df[df["name_lower"] == player_name.lower().strip()]                                             
                                                                                                                        
            if not player_row.empty:                                                                                     
                row = player_row.iloc[0]                                                                                 
                history.append({                                                                                         
                    "timestamp": ts,                                                                                     
                    "polymarket_odds": row.get("polymarket_odds"),                                                       
                    "kalshi_odds": row.get("kalshi_odds"),                                                               
                    "avg_prob": row.get("avg_prob"),                                                                     
                })                                                                                                       
        except Exception:                                                                                                
            continue                                                                                                     
                                                                                                                        
    return pd.DataFrame(history)                                                                                         
                                                                                                                        
                                                                                                                           
def render_odds_history(comparison_df: pd.DataFrame):                                                                    
    """Render odds history and line movement."""                                                                         
    st.markdown("#### 📈 Odds History & Line Movement")                                                                  
    st.caption("Track how odds change over time")                                                                        
                                                                                                                        
    # Save snapshot button                                                                                               
    col1, col2 = st.columns([3, 1])                                                                                      
    with col2:                                                                                                           
        if st.button("📸 Save Snapshot", help="Save current odds for tracking"):                                         
            path = save_odds_snapshot()                                                                                  
            if path:                                                                                                     
                st.success(f"Saved!")                                                                                    
            else:                                                                                                        
                st.error("No odds to save")                                                                              
                                                                                                                        
    # Player selector                                                                                                    
    if comparison_df.empty:                                                                                              
        st.info("No odds data available.")                                                                               
        return                                                                                                           
                                                                                                                        
    players = comparison_df["player_name"].dropna().tolist()                                                             
    selected_player = st.selectbox("Select player to track:", players[:30], key="history_player")                        
                                                                                                                        
    if selected_player:                                                                                                  
        history_df = load_odds_history(selected_player)                                                                  
                                                                                                                        
        if history_df.empty:                                                                                             
            st.info(f"No history for {selected_player}. Click 'Save Snapshot' to start tracking.")                       
        else:                                                                                                            
            # Current vs first recorded                                                                                  
            current_poly = comparison_df[comparison_df["player_name"] == selected_player]["polymarket_odds"].iloc[0]     
            current_kalshi = comparison_df[comparison_df["player_name"] == selected_player]["kalshi_odds"].iloc[0]       
                                                                                                                        
            first_poly = history_df.iloc[0]["polymarket_odds"] if pd.notna(history_df.iloc[0]["polymarket_odds"]) else None                                                                                                                     
            first_kalshi = history_df.iloc[0]["kalshi_odds"] if pd.notna(history_df.iloc[0]["kalshi_odds"]) else None    
                                                                                                                        
            # Show movement                                                                                              
            col1, col2, col3 = st.columns(3)                                                                             
            with col1:                                                                                                   
                if pd.notna(current_poly) and first_poly:                                                                
                    delta = int(current_poly - first_poly)                                                               
                    delta_str = f"{'+' if delta > 0 else ''}{delta}"                                                     
                    st.metric("Polymarket", f"+{int(current_poly)}", delta_str)                                          
                else:                                                                                                    
                    st.metric("Polymarket", "—")                                                                         
            with col2:                                                                                                   
                if pd.notna(current_kalshi) and first_kalshi:                                                            
                    delta = int(current_kalshi - first_kalshi)                                                           
                    delta_str = f"{'+' if delta > 0 else ''}{delta}"                                                     
                    st.metric("Kalshi", f"+{int(current_kalshi)}", delta_str)                                            
                else:                                                                                                    
                    st.metric("Kalshi", "—")                                                                             
            with col3:                                                                                                   
                st.metric("Snapshots", len(history_df))                                                                  
                                                                                                                        
            # Chart                                                                                                      
            if len(history_df) > 1:                                                                                      
                chart_data = history_df.melt(                                                                            
                    id_vars=["timestamp"],                                                                               
                    value_vars=["polymarket_odds", "kalshi_odds"],                                                       
                    var_name="Source",                                                                                   
                    value_name="Odds"                                                                                    
                )                                                                                                        
                chart_data["Source"] = chart_data["Source"].replace({                                                    
                    "polymarket_odds": "Polymarket",                                                                     
                    "kalshi_odds": "Kalshi"                                                                              
                })                                                                                                       
                chart_data = chart_data.dropna()                                                                         
                                                                                                                        
                if not chart_data.empty:                                                                                 
                    fig = px.line(                                                                                       
                        chart_data, x="timestamp", y="Odds", color="Source",                                             
                        title=f"Odds Movement: {selected_player}",                                                       
                        markers=True                                                                                     
                    )                                                                                                    
                    fig.update_layout(                                                                                   
                        xaxis_title="Date",                                                                              
                        yaxis_title="American Odds",                                                                     
                        legend_title="Source",                                                                           
                        height=300                                                                                       
                    )                                                                                                    
                    st.plotly_chart(fig, use_container_width=True)                                                       
                                                                                                                        
            # History table                                                                                              
            with st.expander("View Raw History"):                                                                        
                display_hist = history_df.copy()                                                                         
                display_hist["timestamp"] = display_hist["timestamp"].dt.strftime("%m/%d %H:%M")                         
                st.dataframe(display_hist, hide_index=True, use_container_width=True)                                    
                            






def _parse_american_odds(v):
    """Parse American odds string/number to numeric."""
    if pd.isna(v):
        return np.nan
    s = str(v).strip().replace("+", "").replace(",", "")
    try:
        return float(s)
    except Exception:
        return np.nan


TID_PATTERN = re.compile(r"(R\d{7})", re.IGNORECASE)


def _extract_tournament_id(value) -> str:
    """Extract normalized tournament id (e.g., R2026007) from text-like input."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    m = TID_PATTERN.search(str(value))
    return m.group(1).upper() if m else ""


def _tournament_id_from_df(df: pd.DataFrame) -> str:
    """Read tournament_id from dataframe if present."""
    if df is None or df.empty or "tournament_id" not in df.columns:
        return ""
    vals = df["tournament_id"].dropna().astype(str).str.strip()
    if vals.empty:
        return ""
    return _extract_tournament_id(vals.iloc[0])


def _is_recent_file(path: Path | None, max_age_hours: float = 30.0) -> bool:
    """Check if file is recent enough to be considered active context."""
    if path is None or not Path(path).exists():
        return False
    age_hours = (datetime.now().timestamp() - Path(path).stat().st_mtime) / 3600.0
    return age_hours <= max_age_hours


def _latest_tournament_id_from_prop_lines(max_age_hours: float = 30.0) -> str:
    """Get tournament id from the newest recent prop lines file."""
    files = sorted(
        (DATA_DIR / "odds").glob("prop_lines_R*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files:
        if _is_recent_file(f, max_age_hours=max_age_hours):
            tid = _extract_tournament_id(f.stem)
            if tid:
                return tid
    return ""


def _latest_tournament_id_from_live(max_age_hours: float = 18.0) -> str:
    """Get tournament id from newest recent live leaderboard file."""
    files = sorted(
        (DATA_DIR / "live").glob("leaderboard_r*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files:
        if _is_recent_file(f, max_age_hours=max_age_hours):
            tid = _extract_tournament_id(f.stem)
            if tid:
                return tid
    return ""


def load_latest_fanduel_odds_df() -> tuple:
    """
    Load latest FanDuel winner odds dataset.

    Priority:
    1. data/odds/fanduel_odds_*.csv
    2. data/odds/pga_odds_*.csv (fallback)
    """
    fd_files = sorted(
        (DATA_DIR / "odds").glob("fanduel_odds_*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    source = "fanduel_odds"
    odds_file = fd_files[0] if fd_files else None

    if odds_file is None:
        pga_files = sorted(
            (DATA_DIR / "odds").glob("pga_odds_*.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        source = "pga_odds"
        odds_file = pga_files[0] if pga_files else None

    if odds_file is None:
        return pd.DataFrame(), None, ""

    df = pd.read_csv(odds_file)
    if df.empty:
        return pd.DataFrame(), odds_file, source

    if "player_name" not in df.columns and "name" in df.columns:
        df["player_name"] = df["name"]

    if "odds_to_win" not in df.columns and "fanduel_odds" in df.columns:
        df["odds_to_win"] = df["fanduel_odds"]

    if "implied_prob" not in df.columns and "fanduel_implied_prob" in df.columns:
        df["implied_prob"] = df["fanduel_implied_prob"]

    if "odds_direction" not in df.columns:
        if "odds_movement_direction" in df.columns:
            df["odds_direction"] = df["odds_movement_direction"]
        elif "odds_swing" in df.columns:
            df["odds_direction"] = df["odds_swing"]
        else:
            df["odds_direction"] = ""

    if "odds_swing" not in df.columns and "odds_movement_swing" in df.columns:
        df["odds_swing"] = df["odds_movement_swing"]

    if "odds_numeric" not in df.columns:
        src_col = "odds_to_win" if "odds_to_win" in df.columns else None
        df["odds_numeric"] = df[src_col].apply(_parse_american_odds) if src_col else np.nan
    else:
        df["odds_numeric"] = pd.to_numeric(df["odds_numeric"], errors="coerce")

    if "implied_prob" not in df.columns:
        df["implied_prob"] = np.where(
            df["odds_numeric"] > 0,
            100.0 / (df["odds_numeric"] + 100.0),
            np.nan,
        )
    else:
        df["implied_prob"] = pd.to_numeric(df["implied_prob"], errors="coerce")

    return df, odds_file, source


def render_longshots_view(min_odds: int = 5000, max_rows: int = 24):
    """Rich UI view for longshots from latest FanDuel/PGA odds file."""
    df, _, _ = load_latest_fanduel_odds_df()
    if df.empty:
        st.info("No odds file found. Run the odds fetch first.")
        return

    player_col = "player_name" if "player_name" in df.columns else "name"
    df = df[df[player_col].notna()].copy()
    df = df[df["odds_numeric"].notna()].copy()
    df = df[df["odds_numeric"] >= min_odds].copy()

    if df.empty:
        st.warning(f"No longshots found at +{min_odds} or longer.")
        return

    # Most likely longshots first (lower odds among longshots)
    df = df.sort_values("odds_numeric", ascending=True).head(max_rows).reset_index(drop=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Longshots", len(df))
    with c2:
        st.metric("Avg Implied %", f"{(df['implied_prob'].mean() * 100):.2f}%")
    with c3:
        st.metric("Cutoff", f"+{int(min_odds)}")

    st.markdown("#### Top Longshots")
    top3 = df.head(3)
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            edge_txt = ""
            if "edge_pct_points" in row and pd.notna(row.get("edge_pct_points")):
                edge_txt = f"  \nEdge: **{row['edge_pct_points']:+.2f} pts**"
            st.markdown(
                f"{medals[i]} **{row[player_col]}**\n\n"
                f"Odds: **+{int(row['odds_numeric'])}**  \n"
                f"Implied: **{row['implied_prob'] * 100:.2f}%**{edge_txt}"
            )

    view_df = pd.DataFrame(
        {
            "Rank": np.arange(1, len(df) + 1),
            "Player": df[player_col].astype(str),
            "Odds": df["odds_numeric"].round(0).astype("Int64").astype(str).radd("+"),
            "Implied %": (df["implied_prob"] * 100).round(2),
            "Model Win %": (
                (pd.to_numeric(df.get("model_win_prob"), errors="coerce") * 100).round(2)
                if "model_win_prob" in df.columns else np.nan
            ),
            "Edge (pts)": (
                pd.to_numeric(df.get("edge_pct_points"), errors="coerce").round(2)
                if "edge_pct_points" in df.columns else np.nan
            ),
        }
    )

    st.dataframe(
        view_df,
        hide_index=True,
        use_container_width=True,
        height=520,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="large"),
            "Odds": st.column_config.TextColumn(width="small"),
            "Implied %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Model Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Edge (pts)": st.column_config.NumberColumn(width="small", format="%.2f"),
        },
    )


def render_favorites_view(max_rows: int = 30):
    """Rich UI view for favorites from latest FanDuel/PGA odds file."""
    df, odds_file, _ = load_latest_fanduel_odds_df()
    if df.empty:
        st.info("No odds file found. Run the odds fetch first.")
        return

    player_col = "player_name" if "player_name" in df.columns else "name"
    df = df[df[player_col].notna()].copy()
    df = df[df["odds_numeric"].notna()].copy()

    if df.empty:
        st.warning("No odds data available.")
        return

    # Sort by shortest odds (favorites first)
    df = df.sort_values("odds_numeric", ascending=True).head(max_rows).reset_index(drop=True)

    # Summary metrics
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Favorites Listed", len(df))
    with c2:
        top_prob = df["implied_prob"].iloc[0] * 100 if not df.empty else 0
        st.metric("Top Favorite %", f"{top_prob:.1f}%")
    with c3:
        file_time = datetime.fromtimestamp(odds_file.stat().st_mtime) if odds_file else datetime.now()
        st.metric("Updated", file_time.strftime("%b %d %H:%M"))

    # Top 3 favorites as cards
    st.markdown("#### ⭐ Top Favorites")
    top3 = df.head(3)
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]
    for i, (_, row) in enumerate(top3.iterrows()):
        with cols[i]:
            with st.container():
                st.markdown(f"**{medals[i]} {row[player_col]}**")
                st.metric("Odds", f"+{int(row['odds_numeric'])}")
                st.caption(f"Win Prob: {row['implied_prob'] * 100:.1f}%")
                if "edge_pct_points" in row and pd.notna(row.get("edge_pct_points")):
                    st.caption(f"Model Edge: {row['edge_pct_points']:+.2f} pts")

    # Full table
    st.markdown("#### 📋 Full Favorites List")
    view_df = pd.DataFrame({
        "Rank": np.arange(1, len(df) + 1),
        "Player": df[player_col].astype(str),
        "Odds": df["odds_numeric"].round(0).astype("Int64").astype(str).radd("+"),
        "Win %": (df["implied_prob"] * 100).round(2),
        "Model Win %": (
            (pd.to_numeric(df.get("model_win_prob"), errors="coerce") * 100).round(2)
            if "model_win_prob" in df.columns else np.nan
        ),
        "Edge (pts)": (
            pd.to_numeric(df.get("edge_pct_points"), errors="coerce").round(2)
            if "edge_pct_points" in df.columns else np.nan
        ),
    })

    st.dataframe(
        view_df,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "Rank": st.column_config.NumberColumn(width="small"),
            "Player": st.column_config.TextColumn(width="large"),
            "Odds": st.column_config.TextColumn(width="small"),
            "Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Model Win %": st.column_config.NumberColumn(width="small", format="%.2f%%"),
            "Edge (pts)": st.column_config.NumberColumn(width="small", format="%.2f"),
        },
    )


# ============================================================================
# WEATHER HELPERS
# ============================================================================

COURSE_COORDINATES = {
    "pebble beach": (36.5675, -121.9486),
    "torrey pines": (32.9005, -117.2516),
    "augusta national": (33.5021, -82.0232),
    "tpc scottsdale": (33.6417, -111.9083),
    "riviera": (34.0489, -118.5003),
    "bay hill": (28.4603, -81.5053),
    "tpc sawgrass": (30.1975, -81.3964),
    "harbour town": (32.1363, -80.8090),
    "quail hollow": (35.1089, -80.8519),
    "southern hills": (36.0631, -95.9408),
    "bethpage black": (40.7445, -73.4533),
    "valhalla": (38.2527, -85.4938),
    "pinehurst": (35.1894, -79.4694),
    "royal troon": (55.5436, -4.8492),
    "st andrews": (56.3433, -2.8019),
    "muirfield": (56.0442, -2.8181),
    "kapalua": (21.0007, -156.6483),
    "waialae": (21.2769, -157.7559),
}


def get_course_coordinates(course_name: str) -> tuple:
    """Get lat/lon for a course, or default to Pebble Beach."""
    if not course_name:
        return COURSE_COORDINATES["pebble beach"]

    course_lower = course_name.lower()
    for key, coords in COURSE_COORDINATES.items():
        if key in course_lower:
            return coords

    return COURSE_COORDINATES["pebble beach"]


@st.cache_data(ttl=900)  # Cache for 15 minutes
def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo API (free, no key needed)."""
    import requests
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "temperature_unit": "fahrenheit",
            "windspeed_unit": "mph",
            "timezone": "America/Los_Angeles"
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        current = data.get("current_weather", {})

        weather_codes = {
            0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Foggy", 51: "Light Drizzle", 53: "Drizzle",
            55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 80: "Rain Showers",
            81: "Rain Showers", 82: "Heavy Showers", 95: "Thunderstorm"
        }

        code = current.get("weathercode", 0)

        return {
            "temp_f": round(current.get("temperature", 0)),
            "wind_mph": round(current.get("windspeed", 0)),
            "wind_dir": current.get("winddirection", 0),
            "conditions": weather_codes.get(code, "Unknown"),
            "code": code,
            "is_windy": current.get("windspeed", 0) > 15,
            "success": True
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def render_weather_widget(course_name: str):
    """Render a weather widget for the tournament course."""
    lat, lon = get_course_coordinates(course_name)
    weather = fetch_weather(lat, lon)

    if not weather.get("success"):
        st.warning(f"Could not fetch weather: {weather.get('error', 'Unknown error')}")
        return

    weather_icons = {
        "Clear": "☀️", "Mainly Clear": "🌤️", "Partly Cloudy": "⛅",
        "Overcast": "☁️", "Foggy": "🌫️", "Light Drizzle": "🌦️",
        "Drizzle": "🌧️", "Heavy Drizzle": "🌧️", "Light Rain": "🌧️",
        "Rain": "🌧️", "Heavy Rain": "⛈️", "Rain Showers": "🌦️",
        "Thunderstorm": "⛈️", "Light Snow": "🌨️", "Snow": "❄️"
    }
    icon = weather_icons.get(weather["conditions"], "🌡️")

    def wind_direction_to_compass(degrees):
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = round(degrees / 45) % 8
        return directions[idx]

    wind_compass = wind_direction_to_compass(weather.get("wind_dir", 0))

    st.markdown("#### 🌤️ Current Weather")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Temperature", f"{weather['temp_f']}°F")
    with col2:
        wind_label = f"{weather['wind_mph']} mph {wind_compass}"
        delta = "Windy! 💨" if weather["is_windy"] else None
        st.metric("Wind", wind_label, delta=delta)
    with col3:
        st.metric("Conditions", f"{icon} {weather['conditions']}")


                                                                                                                        
  # ============================================================================                                        
  # PREDICTION VISUALIZATION HELPERS                                                                                    
  # ============================================================================                                        
                                                                                                                        
def render_tier_list(predictions_df: pd.DataFrame):                                                                   
    """Render predictions as a tier list."""                                                                          
    st.markdown("#### 🏆 Player Tier List")                                                                           
                                                                                                                    
    if predictions_df.empty:                                                                                          
        st.info("No predictions available")                                                                           
        return                                                                                                        
                                                                                                                    
    rank_col = "expected_value" if "expected_value" in predictions_df.columns else "win_prob"                         
    df = predictions_df.sort_values(rank_col, ascending=False).reset_index(drop=True)                                 
                                                                                                                    
    tiers = {                                                                                                         
        "S": {"color": "#ffd700", "bg": "#fff9e6", "range": (0, 5)},                                                  
        "A": {"color": "#4caf50", "bg": "#e8f5e9", "range": (5, 15)},                                                 
        "B": {"color": "#2196f3", "bg": "#e3f2fd", "range": (15, 30)},                                                
        "C": {"color": "#9e9e9e", "bg": "#f5f5f5", "range": (30, 50)},                                                
    }                                                                                                                 
                                                                                                                    
    for tier, config in tiers.items():                                                                                
        start, end = config["range"]                                                                                  
        tier_players = df.iloc[start:end]                                                                             
                                                                                                                    
        if tier_players.empty:                                                                                        
            continue                                                                                                  
                                                                                                                    
        names = tier_players["player_name"].tolist()                                                                  
        chips = " ".join([f'<span style="background: white; padding: 0.25rem 0.5rem; border-radius: 15px; font-size:  0.85rem; margin: 2px;">{n}</span>' for n in names])                                                                   
                                                                                                                    
        st.markdown(f"""                                                                                              
        <div style="background: {config['bg']}; border-left: 4px solid {config['color']};                             
                    padding: 0.75rem; margin: 0.5rem 0; border-radius: 8px;">                                         
            <strong style="color: {config['color']}; font-size: 1.2rem;">{tier} Tier</strong>                         
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">                            
                {chips}                                                                                               
            </div>                                                                                                    
        </div>                                                                                                        
        """, unsafe_allow_html=True) 



def render_head_to_head(predictions_df: pd.DataFrame):                                                                
    """Compare two players head-to-head."""                                                                           
    st.markdown("#### ⚔️ Head-to-Head Comparison")                                                                    
                                                                                                                    
    players = predictions_df["player_name"].tolist()                                                                  
                                                                                                                    
    col1, col2 = st.columns(2)                                                                                        
    with col1:                                                                                                        
        player1 = st.selectbox("Player 1", players[:50], key="h2h_p1")                                                
    with col2:                                                                                                        
        player2 = st.selectbox("Player 2", players[:50], index=min(1, len(players)-1), key="h2h_p2")                  
                                                                                                                    
    if player1 and player2 and player1 != player2:                                                                    
        p1_row = predictions_df[predictions_df["player_name"] == player1]                                             
        p2_row = predictions_df[predictions_df["player_name"] == player2]                                             
                                                                                                                    
        if p1_row.empty or p2_row.empty:                                                                              
            return                                                                                                    
                                                                                                                    
        p1_data = p1_row.iloc[0]                                                                                      
        p2_data = p2_row.iloc[0]                                                                                      
                                                                                                                    
        st.markdown("---")                                                                                            
                                                                                                                    
        metrics = [                                                                                                   
            ("win_prob", "Win %"),                                                                                    
            ("top5_prob", "Top 5 %"),                                                                                 
            ("top10_prob", "Top 10 %"),                                                                               
            ("expected_value", "Exp. Value"),                                                                         
        ]                                                                                                             
                                                                                                                    
        cols = st.columns(len(metrics))                                                                               
        for col, (metric, label) in zip(cols, metrics):                                                               
            if metric in p1_data and metric in p2_data:                                                               
                v1 = p1_data[metric] * 100 if "prob" in metric else p1_data[metric]                                   
                v2 = p2_data[metric] * 100 if "prob" in metric else p2_data[metric]                                   
                                                                                                                    
                with col:                                                                                             
                    st.markdown(f"**{label}**")                                                                       
                    fmt = ".1f%" if "prob" in metric else ",.0f"                                                      
                    w1 = "✓" if v1 > v2 else ""                                                                       
                    w2 = "✓" if v2 > v1 else ""                                                                       
                    st.markdown(f"{player1.split()[-1]}: **{v1:{fmt}}** {w1}")                                        
                    st.markdown(f"{player2.split()[-1]}: **{v2:{fmt}}** {w2}")     
















def render_tier_list(predictions_df: pd.DataFrame):
    """Render predictions as a visual tier list."""
    st.markdown("#### Player Tiers by Expected Value")

    # Define tiers based on percentiles
    if predictions_df.empty:
        st.warning("No predictions data available")
        return

    df = predictions_df.copy()
    df = df.sort_values("expected_value", ascending=False)

    # Calculate tier boundaries
    tier_configs = [
        ("S", "#FFD700", "Elite - Top 5", 5),
        ("A", "#C0C0C0", "Strong Contenders - Top 10", 10),
        ("B", "#CD7F32", "Solid Plays - Top 20", 20),
        ("C", "#4A90D9", "Value Picks - Top 35", 35),
        ("D", "#808080", "Longshots - Rest", 100),
    ]

    # Assign tiers
    df["tier"] = "D"
    df["tier_color"] = "#808080"
    for i, (tier, color, _, cutoff) in enumerate(tier_configs):
        if i == 0:
            mask = df.index.isin(df.head(cutoff).index)
        else:
            prev_cutoff = tier_configs[i-1][3]
            mask = df.index.isin(df.head(cutoff).index) & ~df.index.isin(df.head(prev_cutoff).index)
        df.loc[mask, "tier"] = tier
        df.loc[mask, "tier_color"] = color

    # Render each tier
    for tier, color, label, cutoff in tier_configs:
        tier_players = df[df["tier"] == tier]
        if tier_players.empty:
            continue

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {color}22, {color}11);
                    border-left: 4px solid {color}; padding: 12px; margin: 10px 0; border-radius: 8px;">
            <span style="font-size: 1.5em; font-weight: bold; color: {color};">
                {tier} Tier
            </span>
            <span style="color: #888; margin-left: 12px;">{label}</span>
        </div>
        """, unsafe_allow_html=True)

        # Display players in this tier as cards
        cols = st.columns(min(5, len(tier_players)))
        for idx, (_, player) in enumerate(tier_players.iterrows()):
            with cols[idx % 5]:
                ev = player.get("expected_value", 0)
                win_prob = player.get("win_prob", 0) * 100
                st.markdown(f"""
                <div style="background: {color}15; padding: 8px; border-radius: 6px;
                            margin: 4px 0; text-align: center; border: 1px solid {color}33;">
                    <div style="font-weight: bold; font-size: 0.9em;">
                        {player.get('player_name', 'Unknown')[:18]}
                    </div>
                    <div style="font-size: 0.8em; color: #666;">
                        EV: ${ev:,.0f} | {win_prob:.1f}%
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("")  # Spacing


def render_head_to_head(predictions_df: pd.DataFrame):
    """Compare two players head-to-head."""
    st.markdown("#### Compare Players Head-to-Head")

    if predictions_df.empty:
        st.warning("No predictions data available")
        return

    player_list = predictions_df["player_name"].dropna().tolist()

    col1, col2 = st.columns(2)
    with col1:
        player1 = st.selectbox("Player 1", player_list, index=0, key="h2h_p1")
    with col2:
        default_idx = min(1, len(player_list) - 1)
        player2 = st.selectbox("Player 2", player_list, index=default_idx, key="h2h_p2")

    if player1 == player2:
        st.warning("Select two different players to compare")
        return

    p1_data = predictions_df[predictions_df["player_name"] == player1].iloc[0]
    p2_data = predictions_df[predictions_df["player_name"] == player2].iloc[0]

    st.markdown("---")

    # Side by side comparison
    col1, col_vs, col2 = st.columns([2, 1, 2])

    with col1:
        st.markdown(f"### {player1}")
        st.metric("Expected Value", f"${p1_data.get('expected_value', 0):,.0f}")
        st.metric("Win Probability", f"{p1_data.get('win_prob', 0)*100:.2f}%")
        st.metric("Top-5 %", f"{p1_data.get('top5_prob', 0)*100:.1f}%")
        st.metric("Top-10 %", f"{p1_data.get('top10_prob', 0)*100:.1f}%")
        st.metric("SG Total", f"{p1_data.get('sg_total', 0):+.3f}")
        plays1 = p1_data.get('hist_times_played', 0)
        st.metric("Course Plays", int(plays1) if pd.notna(plays1) else 0)

    with col_vs:
        st.markdown("<div style='text-align: center; padding-top: 80px;'><h1>VS</h1></div>", unsafe_allow_html=True)

    with col2:
        st.markdown(f"### {player2}")
        st.metric("Expected Value", f"${p2_data.get('expected_value', 0):,.0f}")
        st.metric("Win Probability", f"{p2_data.get('win_prob', 0)*100:.2f}%")
        st.metric("Top-5 %", f"{p2_data.get('top5_prob', 0)*100:.1f}%")
        st.metric("Top-10 %", f"{p2_data.get('top10_prob', 0)*100:.1f}%")
        st.metric("SG Total", f"{p2_data.get('sg_total', 0):+.3f}")
        plays2 = p2_data.get('hist_times_played', 0)
        st.metric("Course Plays", int(plays2) if pd.notna(plays2) else 0)

    # Winner verdict
    st.markdown("---")
    ev1 = p1_data.get('expected_value', 0)
    ev2 = p2_data.get('expected_value', 0)

    if ev1 > ev2:
        winner = player1
        margin = ev1 - ev2
        winner_color = "#00C853"
    else:
        winner = player2
        margin = ev2 - ev1
        winner_color = "#00C853"

    st.markdown(f"""
    <div style="background: {winner_color}22; padding: 16px; border-radius: 8px; text-align: center;">
        <h3 style="color: {winner_color};">Model Pick: {winner}</h3>
        <p>EV Advantage: ${margin:,.0f}</p>
    </div>
    """, unsafe_allow_html=True)


def get_prediction_files():
    """Get available prediction files."""
    if OUTPUTS_DIR.exists():
        return sorted(OUTPUTS_DIR.glob("*_predictions.csv"),
                     key=lambda x: x.stat().st_mtime, reverse=True)
    return []


@st.cache_data(ttl=300)
def load_betting_profiles(tournament_id: str = None):
    """Load betting profile articles for current tournament."""
    profiles_dir = DATA_DIR / "betting_profiles"

    if tournament_id:
        # Try tournament-specific file first
        specific_file = profiles_dir / f"articles_{tournament_id}.csv"
        if specific_file.exists():
            return pd.read_csv(specific_file)

    # Find most recent articles file
    article_files = sorted(profiles_dir.glob("articles_*.csv"),
                          key=lambda x: x.stat().st_mtime, reverse=True)
    if article_files:
        return pd.read_csv(article_files[0])

    return pd.DataFrame()


def get_player_profile(profiles_df: pd.DataFrame, player_name: str) -> dict:
    """Get betting profile for a specific player."""
    if profiles_df.empty:
        return None

    # Normalize player name for matching
    player_lower = player_name.lower().strip()

    for _, row in profiles_df.iterrows():
        profile_name = str(row.get('player_name', '')).lower().strip()
        if player_lower in profile_name or profile_name in player_lower:
            return row.to_dict()
        # Also check title
        title = str(row.get('title', '')).lower()
        if player_lower.split()[0] in title and player_lower.split()[-1] in title:
            return row.to_dict()

    return None


def format_bullets_as_list(bullets_str: str) -> list:
    """Convert pipe-separated bullets to list."""
    if not bullets_str or pd.isna(bullets_str):
        return []
    return [b.strip() for b in str(bullets_str).split('|') if b.strip()]


def clean_betting_profile_text(text: str) -> str:
    """Remove disclaimer and boilerplate from betting profile text."""
    import re

    if not text or pd.isna(text):
        return ""

    cleaned = str(text)

    # Remove the common disclaimer block that appears at end of summaries
    # This captures: "All stats in this article... HaveAGamePlan.org."
    disclaimer_block_pattern = r'All stats in this article are accurate for[^.]*\..*?HaveAGamePlan\.org\.?\s*'
    cleaned = re.sub(disclaimer_block_pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)

    # Also handle partial disclaimer patterns that might appear alone
    partial_disclaimers = [
        r'Responsible sports betting starts with a game plan[^.]*\.',
        r'Set a budget\. Keep it social\. Play with friends\.\s*',
        r'Learn the game and know the odds\.\s*',
        r'Play with trusted, licensed operators\.\s*',
        r'CLICK HERE to learn more at HaveAGamePlan\.org\.?\s*',
        r'Note: Using player performance data from ShotLink powered by CDW[^.]*\.',
        r'[^.]*PGA TOUR has created this story using AWS Gen AI technology[^.]*\.',
        r'While we strive for accuracy and quality[^.]*error-free[^.]*\.',
    ]

    for pattern in partial_disclaimers:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip()

    return cleaned

def parse_strokes_gained_from_bullets(bullets: list) -> dict:                                                         
    """Extract strokes gained stats from bullet points."""                                                            
    sg_stats = {                                                                                                      
        'sg_ott': None,  # Off the Tee                                                                                
        'sg_app': None,  # Approach                                                                                   
        'sg_atg': None,  # Around the Green                                                                           
        'sg_putt': None, # Putting                                                                                    
        'sg_total': None,                                                                                             
        'driving_dist': None,                                                                                         
        'gir': None,  # Greens in Regulation                                                                          
    }                                                                                                                 
                                                                                                                    
    for bullet in bullets:                                                                                            
        b_lower = bullet.lower()                                                                                      
                                                                                                                    
        # SG: Off-the-Tee                                                                                             
        if 'off-the-tee' in b_lower or 'off the tee' in b_lower:                                                      
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if match:                                                                                                 
                sg_stats['sg_ott'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Approach                                                                                                
        if 'approach' in b_lower and 'green' in b_lower:                                                              
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'sports a\s*(-?\d+\.?\d*)', b_lower)                                               
            if match:                                                                                                 
                sg_stats['sg_app'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Around the Green                                                                                        
        if 'around-the-green' in b_lower or 'around the green' in b_lower:                                            
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if match:                                                                                                 
                sg_stats['sg_atg'] = float(match.group(1))                                                            
                                                                                                                    
        # SG: Putting                                                                                                 
        if 'putting' in b_lower and 'strokes gained' in b_lower:                                                      
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'average of\s*(-?\d+\.?\d*)', b_lower)                                             
            if not match:                                                                                             
                match = re.search(r'delivered a\s*(-?\d+\.?\d*)', b_lower)                                            
            if match:                                                                                                 
                sg_stats['sg_putt'] = float(match.group(1))                                                           
                                                                                                                    
        # SG: Total                                                                                                   
        if 'total' in b_lower and 'strokes gained' in b_lower:                                                        
            import re                                                                                                 
            match = re.search(r'(-?\d+\.?\d*)\s*strokes gained: total', b_lower)                                      
            if not match:                                                                                             
                match = re.search(r'averaged\s*(-?\d+\.?\d*)\s*strokes gained: total', b_lower)                       
            if match:                                                                                                 
                sg_stats['sg_total'] = float(match.group(1))                                                          
                                                                                                                    
        # Driving Distance                                                                                            
        if 'driving distance' in b_lower:                                                                             
            import re                                                                                                 
            match = re.search(r'(\d+\.?\d*)\s*yards', b_lower)                                                        
            if match:                                                                                                 
                sg_stats['driving_dist'] = float(match.group(1))                                                      
                                                                                                                    
        # GIR                                                                                                         
        if 'greens in regulation' in b_lower:                                                                         
            import re                                                                                                 
            match = re.search(r'(\d+\.?\d*)%', b_lower)                                                               
            if match:                                                                                                 
                sg_stats['gir'] = float(match.group(1))                                                               
                                                                                                                    
    return sg_stats   




def render_player_profile_card(profile: dict, show_full: bool = True):                                                
    """Render an improved player profile card with stats table and formatted sections."""                             
    import re                                                                                                         
                                                                                                                    
    bullets = format_bullets_as_list(profile.get('bullets', ''))                                                      
    sg_stats = parse_strokes_gained_from_bullets(bullets)                                                             
                                                                                                                    
    # === SUMMARY CARD ===                                                                                            
    st.markdown(f"### {profile.get('player_name', 'Player')}")                                                        
                                                                                                                    
    if profile.get('published_at'):                                                                                   
        pub_date = str(profile.get('published_at', ''))[:10]                                                          
        st.caption(f"📅 {pub_date} • {profile.get('tournament_slug', '').replace('-', ' ').title()}")                 
                                                                                                                    
    # Key metrics row                                                                                                 
    col1, col2, col3, col4 = st.columns(4)                                                                            
                                                                                                                    
    with col1:                                                                                                        
        sg_total = sg_stats.get('sg_total')                                                                           
        if sg_total is not None:                                                                                      
            color = "green" if sg_total > 0 else "red" if sg_total < 0 else "gray"                                    
            st.metric("SG: Total", f"{sg_total:+.2f}", delta_color="off")                                             
        else:                                                                                                         
            st.metric("SG: Total", "—")                                                                               
                                                                                                                    
    with col2:                                                                                                        
        gir = sg_stats.get('gir')                                                                                     
        if gir:                                                                                                       
            st.metric("GIR %", f"{gir:.1f}%")                                                                         
        else:                                                                                                         
            st.metric("GIR %", "—")                                                                                   
                                                                                                                    
    with col3:                                                                                                        
        dist = sg_stats.get('driving_dist')                                                                           
        if dist:                                                                                                      
            st.metric("Driving", f"{dist:.0f} yds")                                                                   
        else:                                                                                                         
            st.metric("Driving", "—")                                                                                 
                                                                                                                    
    with col4:                                                                                                        
        # Extract best recent finish                                                                                  
        best_finish = "—"                                                                                             
        for b in bullets:                                                                                             
            if 'best finish' in b.lower():                                                                            
                match = re.search(r'(tied for \d+|\d+)(?:st|nd|rd|th)?', b.lower())                                   
                if match:                                                                                             
                    best_finish = match.group(1).replace('tied for ', 'T')                                            
                    break                                                                                             
        st.metric("Best Recent", best_finish)                                                                         
                                                                                                                    
    # === STROKES GAINED TABLE ===                                                                                    
    if any(v is not None for v in [sg_stats['sg_ott'], sg_stats['sg_app'], sg_stats['sg_atg'], sg_stats['sg_putt']]): 
        st.markdown("#### 📊 Strokes Gained Breakdown")                                                               
                                                                                                                    
        sg_data = {                                                                                                   
            "Category": ["Off-the-Tee", "Approach", "Around Green", "Putting"],                                       
            "Value": [                                                                                                
                f"{sg_stats['sg_ott']:+.3f}" if sg_stats['sg_ott'] is not None else "—",                              
                f"{sg_stats['sg_app']:+.3f}" if sg_stats['sg_app'] is not None else "—",                              
                f"{sg_stats['sg_atg']:+.3f}" if sg_stats['sg_atg'] is not None else "—",                              
                f"{sg_stats['sg_putt']:+.3f}" if sg_stats['sg_putt'] is not None else "—",                            
            ],                                                                                                        
            "Rating": [                                                                                               
                "🟢" if sg_stats['sg_ott'] and sg_stats['sg_ott'] > 0.3 else "🟡" if sg_stats['sg_ott'] and           
sg_stats['sg_ott'] > 0 else "🔴" if sg_stats['sg_ott'] else "⚪",                                                     
                "🟢" if sg_stats['sg_app'] and sg_stats['sg_app'] > 0.3 else "🟡" if sg_stats['sg_app'] and           
sg_stats['sg_app'] > 0 else "🔴" if sg_stats['sg_app'] else "⚪",                                                     
                "🟢" if sg_stats['sg_atg'] and sg_stats['sg_atg'] > 0.3 else "🟡" if sg_stats['sg_atg'] and           
sg_stats['sg_atg'] > 0 else "🔴" if sg_stats['sg_atg'] else "⚪",                                                     
                "🟢" if sg_stats['sg_putt'] and sg_stats['sg_putt'] > 0.3 else "🟡" if sg_stats['sg_putt'] and        
sg_stats['sg_putt'] > 0 else "🔴" if sg_stats['sg_putt'] else "⚪",                                                   
            ]                                                                                                         
        }                                                                                                             
                                                                                                                    
        st.dataframe(                                                                                                 
            pd.DataFrame(sg_data),                                                                                    
            hide_index=True,                                                                                          
            use_container_width=True,                                                                                 
            column_config={                                                                                           
                "Category": st.column_config.TextColumn(width="medium"),                                              
                "Value": st.column_config.TextColumn(width="small"),                                                  
                "Rating": st.column_config.TextColumn(width="small"),                                                 
            }                                                                                                         
        )                                                                                                             
                                                                                                                    
    if not show_full:                                                                                                 
        return                                                                                                        
                                                                                                                    
    # === CATEGORIZED INSIGHTS ===                                                                                    
    st.markdown("#### 🎯 Key Insights")                                                                               
                                                                                                                    
    # Categorize bullets                                                                                              
    course_bullets = []                                                                                               
    form_bullets = []                                                                                                 
    ranking_bullets = []                                                                                              
                                                                                                                    
    for b in bullets:                                                                                                 
        b_lower = b.lower()                                                                                           
        # Skip SG bullets (already shown in table)                                                                    
        if 'strokes gained' in b_lower:                                                                               
            continue                                                                                                  
        if 'first time' in b_lower or 'competing' in b_lower or 'at the' in b_lower or 'won this' in b_lower:         
            course_bullets.append(b)                                                                                  
        elif 'finish' in b_lower or 'appearance' in b_lower or 'last ten' in b_lower:                                 
            form_bullets.append(b)                                                                                    
        elif 'ranks' in b_lower or 'ranking' in b_lower or 'fedex' in b_lower:                                        
            ranking_bullets.append(b)                                                                                 
                                                                                                                    
    col1, col2 = st.columns(2)                                                                                        
                                                                                                                    
    with col1:                                                                                                        
        if course_bullets:                                                                                            
            st.markdown("**🏟️ At This Tournament**")                                                                  
            for b in course_bullets[:3]:                                                                              
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
        if form_bullets:                                                                                              
            st.markdown("**📈 Recent Form**")                                                                         
            for b in form_bullets[:3]:                                                                                
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
    with col2:                                                                                                        
        if ranking_bullets:                                                                                           
            st.markdown("**🏆 Rankings & Stats**")                                                                    
            for b in ranking_bullets[:4]:                                                                             
                st.markdown(f"- {b}")                                                                                 
                                                                                                                    
    # === OVERVIEW (collapsible) ===
    if profile.get('summary'):
        cleaned_summary = clean_betting_profile_text(profile.get('summary', ''))
        if cleaned_summary:
            with st.expander("📖 Full Overview"):
                st.markdown(cleaned_summary)







def get_quick_insight(player_name: str, profiles_df: pd.DataFrame, score=None) -> str:
    """Generate a quick insight for a player from betting profiles and score data."""
    insights = []
    profile = get_player_profile(profiles_df, player_name) if not profiles_df.empty else None 
    
    if profile:
        bullets = format_bullets_as_list(profile.get('bullets', ''))
        for bullet in bullets[:5]:
            bullet_lower = bullet.lower()
            if 'strokes gained: total' in bullet_lower and 'average' in bullet_lower:                                 
                  # Extract SG:Total - e.g., "averaged 1.5 Strokes Gained: Total"                                       
                if 'averaged' in bullet_lower:                                                                        
                    insights.append(bullet.split('averaged')[1].split('Strokes')[0].strip() + " SG:T avg")            
                    break                                                                                             
                elif 'best finish' in bullet_lower:                                                                       
                    # Extract recent best finish                                                                          
                    insights.append(bullet[:50])                                                                          
                    break                                                                                                 
                elif 'wins' in bullet_lower or 'won' in bullet_lower:                                                     
                    insights.append(bullet[:50])                                                                          
                    break                                                                                                 
                                                                                                                        
            # Add course history from score if available                                                                      
            if score and score.course_history_note:                                                                           
                note = score.course_history_note                                                                              
                # Shorten common patterns                                                                                     
                note = note.replace(" plays", "p").replace(" play", "p")                                                      
                if note and note not in insights:                                                                             
                    insights.append(note[:30])                                                                                
                                                                                                                            
                # Add form indicator from score                                                                                   
                if score:                                                                                                         
                    if score.current_form >= 75:                                                                                  
                        insights.append("🔥 Hot")                                                                                 
                    elif score.current_form >= 60:                                                                                
                        insights.append("📈 Good form")                                                                           
                    elif score.current_form <= 30:                                                                                
                        insights.append("📉 Cold")                                                                                
                                                                                                                            
                return " | ".join(insights[:2]) if insights else "—"


# ============================================================================
# LIVE TOURNAMENT HELPERS
# ============================================================================

LIVE_DIR = DATA_DIR / "live"
PERFORMANCE_DIR = DATA_DIR / "performance"
ODDS_DIR = DATA_DIR / "odds"


def leaderboard_meta_path(csv_path: Path) -> Path:
    return csv_path.parent / f"{csv_path.stem}_meta.json"


def load_leaderboard_meta(meta_path: Path) -> dict:
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@st.cache_data(ttl=120)  # Cache for 2 minutes for live data
def fetch_live_leaderboard(tournament_id: str = None) -> tuple:
    """Fetch live leaderboard data."""
    import subprocess

    # Run the scraper
    cmd = ["python3", str(PROJECT_ROOT / "scripts" / "scrapers" / "fetch_live_leaderboard.py")]
    if tournament_id:
        cmd.extend(["--tournament-id", tournament_id])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=PROJECT_ROOT)
    except Exception as e:
        return None, None, str(e)

    # Load the resulting CSV and metadata
    if tournament_id:
        csv_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}.csv"
        meta_path = LIVE_DIR / f"leaderboard_{tournament_id.lower()}_meta.json"
    else:
        # Find most recent
        csv_files = sorted(LIVE_DIR.glob("leaderboard_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
        if csv_files:
            csv_path = csv_files[0]
            meta_path = leaderboard_meta_path(csv_path)
        else:
            return None, None, "No leaderboard data found"

    if not csv_path.exists():
        return None, None, "Leaderboard file not found"

    df = pd.read_csv(csv_path)
    meta = load_leaderboard_meta(meta_path)

    return df, meta, None


def render_live_leaderboard(df: pd.DataFrame, meta: dict):
    """Render the live leaderboard."""
    if df is None or df.empty:
        st.warning("No leaderboard data available")
        return

    # Tournament info header
    tournament_name = meta.get("tournament_name", "Tournament")
    current_round = meta.get("current_round", 1)
    round_status = meta.get("round_status", "")
    cut_line = meta.get("cut_line", {})
    cut_projection = meta.get("cut_projection", {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Round", current_round)
    with col2:
        st.metric("Status", round_status or "In Progress")
    with col3:
        cut_score = cut_line.get("cutScore", "TBD") if cut_line else "TBD"
        st.metric("Cut Line", cut_score)
    with col4:
        st.metric("Players", len(df))

    st.markdown("---")

    # --- Visual Leader Cards for Top 3 ---
    st.markdown("### 🏆 Leaders")
    top3 = df.head(3)

    leader_cols = st.columns(3)
    position_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]  # Gold, Silver, Bronze
    position_emojis = ["🥇", "🥈", "🥉"]

    for i, (_, player) in enumerate(top3.iterrows()):
        with leader_cols[i]:
            pos = player.get("position", f"{i+1}")
            name = str(player.get("player_name", "Unknown"))[:16]
            total = player.get("total", "E")
            thru = player.get("thru", "-")
            r1 = player.get("R1", "-")
            r2 = player.get("R2", "-")
            r3 = player.get("R3", "-")
            odds = player.get("odds_to_win", "")
            country = player.get("country", "")

            # Position change indicator
            change = player.get("position_change", 0)
            if pd.notna(change) and change != 0:
                change_str = f"↑{abs(int(change))}" if change > 0 else f"↓{abs(int(change))}"
                change_color = "#00C853" if change > 0 else "#F44336"
            else:
                change_str = ""
                change_color = "#888"

            change_html = (
                f'<div style="color: {change_color}; font-size: 0.85em; margin-top: 4px;">{change_str}</div>'
                if change_str else
                '<div style="margin-top: 4px;"></div>'
            )
            odds_html = (
                f'<div style="color: #4CAF50; font-size: 0.9em; font-weight: bold; margin-top: 8px;">{odds}</div>'
                if odds else ""
            )

            card_html = textwrap.dedent(f"""
                <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px; padding: 16px; margin: 4px 0;
                            border: 2px solid {position_colors[i]}; text-align: center;
                            min-height: 330px; height: 330px;
                            display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="font-size: 2em;">{position_emojis[i]}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1.1em; margin: 8px 0;">{name}</div>
                    <div style="color: #888; font-size: 0.8em;">{country}</div>
                    <div style="color: #00C853; font-size: 1.8em; font-weight: bold; margin: 8px 0;">{total}</div>
                    <div style="color: #aaa; font-size: 0.85em;">Thru {thru}</div>{change_html}
                    <div style="display: flex; justify-content: center; gap: 8px; margin-top: 10px;
                                padding-top: 10px; border-top: 1px solid #2a2a4a;">
                        <span style="color: #888; font-size: 0.75em;">R1: {r1}</span>
                        <span style="color: #888; font-size: 0.75em;">R2: {r2}</span>
                        <span style="color: #888; font-size: 0.75em;">R3: {r3}</span>
                    </div>{odds_html}
                </div>
            """).strip()
            st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("---")

    # Leaderboard table with styling
    display_df = df.head(50).copy()

    # Format columns
    cols_to_show = ["position", "player_name", "total", "thru", "R1", "R2", "R3", "R4"]
    if "odds_to_win" in display_df.columns:
        cols_to_show.append("odds_to_win")

    display_df = display_df[[c for c in cols_to_show if c in display_df.columns]]

    # Add position change indicator
    if "position_change" in df.columns:
        def format_change(row):
            change = row.get("position_change", 0)
            if pd.isna(change) or change == 0:
                return ""
            return f"↑{abs(int(change))}" if change > 0 else f"↓{abs(int(change))}"
        display_df["Move"] = df.head(50).apply(format_change, axis=1)

    # Rename columns for display
    display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]

    st.dataframe(display_df, hide_index=True, use_container_width=True, height=600)

    # Cut line projection
    if cut_projection:
        st.markdown("### Cut Line Projection")
        col1, col2, col3 = st.columns(3)
        with col1:
            projected = cut_projection.get("projected_cut_score", "E")
            if projected == 0:
                projected = "E"
            elif projected > 0:
                projected = f"+{projected}"
            st.metric("Projected Cut", projected)
        with col2:
            st.metric("On the Bubble", cut_projection.get("bubble_count", 0))
        with col3:
            st.metric("Safely In", cut_projection.get("safely_in", 0))


def compare_live_vs_predictions(live_df: pd.DataFrame, tournament_id: str = None) -> pd.DataFrame:
    """Compare live leaderboard positions with pre-tournament model predictions."""
    # Find matching predictions file
    predictions_df = None
    if tournament_id:
        patterns = [
            OUTPUTS_DIR / f"{tournament_id}_predictions.csv",
            OUTPUTS_DIR / f"{tournament_id.lower()}_predictions.csv",
        ]
        for p in patterns:
            if p.exists():
                predictions_df = pd.read_csv(p)
                break

    # If not found, try most recent predictions
    if predictions_df is None:
        pred_files = get_prediction_files()
        if pred_files:
            predictions_df = pd.read_csv(pred_files[0])

    if predictions_df is None or predictions_df.empty:
        return pd.DataFrame()

    # Normalize names for matching
    live_df = ensure_player_name_column(live_df)
    predictions_df = ensure_player_name_column(predictions_df)

    live_df["name_key"] = live_df["player_name"].apply(_name_key)
    predictions_df["name_key"] = predictions_df["player_name"].apply(_name_key)
    live_df = live_df[live_df["name_key"] != ""].copy()
    predictions_df = predictions_df[predictions_df["name_key"] != ""].copy()

    if live_df.empty or predictions_df.empty:
        return pd.DataFrame()

    for col in ["expected_value", "win_prob", "top5_prob", "top10_prob"]:
        if col not in predictions_df.columns:
            predictions_df[col] = np.nan

    # Add model rank
    rank_col = "expected_value"
    if rank_col not in predictions_df.columns or predictions_df[rank_col].isna().all():
        rank_col = "win_prob" if "win_prob" in predictions_df.columns else None
    if rank_col:
        predictions_df = predictions_df.sort_values(rank_col, ascending=False, na_position="last")
    predictions_df["model_rank"] = range(1, len(predictions_df) + 1)

    # Parse live position to numeric
    def parse_pos(pos):
        if pd.isna(pos):
            return 999
        pos_str = str(pos).upper().replace("T", "")
        try:
            return int(pos_str)
        except ValueError:
            return 999

    if "position" in live_df.columns:
        live_df["live_pos_numeric"] = live_df["position"].apply(parse_pos)
    else:
        live_df["live_pos_numeric"] = 999

    # Merge
    merged = live_df.merge(
        predictions_df[["name_key", "model_rank", "expected_value", "win_prob", "top5_prob", "top10_prob"]],
        on="name_key",
        how="left"
    )

    # Calculate performance vs prediction
    merged["rank_diff"] = merged["model_rank"] - merged["live_pos_numeric"]
    merged["outperforming"] = merged["rank_diff"] > 0  # Positive = doing better than predicted

    # Sort by live position
    merged = merged.sort_values("live_pos_numeric")

    return merged


def compare_live_vs_market_odds(live_df: pd.DataFrame) -> pd.DataFrame:
    """Compare live FanDuel odds with pre-tournament Polymarket/Kalshi odds."""
    # Load pre-tournament odds
    polymarket_files = sorted(ODDS_DIR.glob("polymarket_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
    kalshi_files = sorted(ODDS_DIR.glob("kalshi_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)

    poly_df = pd.read_csv(polymarket_files[0]) if polymarket_files else pd.DataFrame()
    kalshi_df = pd.read_csv(kalshi_files[0]) if kalshi_files else pd.DataFrame()

    if poly_df.empty and kalshi_df.empty:
        return pd.DataFrame()

    live_df = ensure_player_name_column(live_df)
    live_df["name_key"] = live_df["player_name"].apply(_name_key)
    live_df = live_df[live_df["name_key"] != ""].copy()
    if live_df.empty:
        return pd.DataFrame()

    # Parse live odds to numeric
    def parse_odds(odds_str):
        if pd.isna(odds_str) or odds_str == "" or odds_str == "-":
            return None
        try:
            return int(str(odds_str).replace("+", ""))
        except ValueError:
            return None

    if "odds_to_win" not in live_df.columns:
        live_df["odds_to_win"] = ""
    live_df["live_odds_numeric"] = live_df["odds_to_win"].apply(parse_odds)
    if "position" not in live_df.columns:
        live_df["position"] = ""
    if "total" not in live_df.columns:
        live_df["total"] = ""

    # Get pre-tournament odds
    result_df = live_df[["position", "player_name", "name_key", "total", "odds_to_win", "live_odds_numeric"]].copy()

    if not poly_df.empty:
        poly_df = ensure_player_name_column(poly_df)
        poly_df["name_key"] = poly_df["player_name"].apply(_name_key)
        odds_col = "odds_polymarket" if "odds_polymarket" in poly_df.columns else "odds_consensus"
        if odds_col in poly_df.columns:
            result_df = result_df.merge(
                poly_df[["name_key", odds_col]].rename(columns={odds_col: "pre_polymarket"}),
                on="name_key",
                how="left"
            )

    if not kalshi_df.empty:
        kalshi_df = ensure_player_name_column(kalshi_df)
        kalshi_df["name_key"] = kalshi_df["player_name"].apply(_name_key)
        odds_col = "odds_kalshi" if "odds_kalshi" in kalshi_df.columns else "odds_consensus"
        if odds_col in kalshi_df.columns:
            result_df = result_df.merge(
                kalshi_df[["name_key", odds_col]].rename(columns={odds_col: "pre_kalshi"}),
                on="name_key",
                how="left"
            )

    # Calculate odds movement
    if "pre_polymarket" in result_df.columns:
        result_df["poly_movement"] = result_df.apply(
            lambda r: r["pre_polymarket"] - r["live_odds_numeric"]
            if pd.notna(r["pre_polymarket"]) and pd.notna(r["live_odds_numeric"])
            else None,
            axis=1
        )

    if "pre_kalshi" in result_df.columns:
        result_df["kalshi_movement"] = result_df.apply(
            lambda r: r["pre_kalshi"] - r["live_odds_numeric"]
            if pd.notna(r["pre_kalshi"]) and pd.notna(r["live_odds_numeric"])
            else None,
            axis=1
        )

    return result_df


def render_live_vs_predictions(live_df: pd.DataFrame, meta: dict):
    """Render comparison of live results vs model predictions."""
    tournament_id = meta.get("tournament_id", "")
    comparison = compare_live_vs_predictions(live_df, tournament_id)

    if comparison.empty:
        st.warning("No predictions found to compare")
        return

    st.markdown("### Model vs Reality")

    # Summary stats
    with_predictions = comparison[comparison["model_rank"].notna()]

    if with_predictions.empty:
        st.warning("No matching players found between predictions and leaderboard")
        return

    outperforming = with_predictions[with_predictions["rank_diff"] > 5]
    underperforming = with_predictions[with_predictions["rank_diff"] < -5]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Matched Players", len(with_predictions))
    with col2:
        st.metric("Outperforming Model", len(outperforming), help="Finishing better than predicted")
    with col3:
        st.metric("Underperforming", len(underperforming), help="Finishing worse than predicted")

    st.markdown("---")

    # Top overperformers
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🚀 Exceeding Expectations")
        top_outperform = with_predictions.nlargest(10, "rank_diff")
        for _, row in top_outperform.iterrows():
            diff = int(row["rank_diff"])
            if diff > 0:
                st.markdown(f"""
                <div style="background: #00C85322; padding: 8px; border-radius: 6px; margin: 4px 0;">
                    <strong>{row['player_name']}</strong><br>
                    <span style="color: #00C853;">Live: {row['position']}</span> vs
                    <span style="color: #888;">Predicted: #{int(row['model_rank'])}</span>
                    <span style="color: #00C853; font-weight: bold;"> (+{diff} spots)</span>
                </div>
                """, unsafe_allow_html=True)

    with col2:
        st.markdown("#### 📉 Underperforming")
        top_underperform = with_predictions.nsmallest(10, "rank_diff")
        for _, row in top_underperform.iterrows():
            diff = int(row["rank_diff"])
            if diff < 0:
                st.markdown(f"""
                <div style="background: #FF525222; padding: 8px; border-radius: 6px; margin: 4px 0;">
                    <strong>{row['player_name']}</strong><br>
                    <span style="color: #FF5252;">Live: {row['position']}</span> vs
                    <span style="color: #888;">Predicted: #{int(row['model_rank'])}</span>
                    <span style="color: #FF5252; font-weight: bold;"> ({diff} spots)</span>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # Full comparison table
    st.markdown("#### Full Comparison")
    display_df = with_predictions[[
        "position", "player_name", "total", "model_rank", "rank_diff", "expected_value", "win_prob"
    ]].copy()

    display_df["model_rank"] = display_df["model_rank"].fillna(999).astype(int)
    display_df["rank_diff"] = display_df["rank_diff"].fillna(0).astype(int)
    display_df["expected_value"] = display_df["expected_value"].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "-")
    display_df["win_prob"] = display_df["win_prob"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "-")

    display_df.columns = ["Live Pos", "Player", "Score", "Model Rank", "Diff", "Pre-Tourn EV", "Win %"]

    st.dataframe(display_df.head(30), hide_index=True, use_container_width=True)


def render_live_odds_comparison(live_df: pd.DataFrame):
    """Render comparison of live odds vs pre-tournament market odds."""
    comparison = compare_live_vs_market_odds(live_df)

    if comparison.empty:
        st.warning("No pre-tournament odds data found")
        return

    st.markdown("### Live Odds vs Pre-Tournament Markets")

    # Show biggest movers
    has_poly = "poly_movement" in comparison.columns
    has_kalshi = "kalshi_movement" in comparison.columns

    if has_poly or has_kalshi:
        movement_col = "poly_movement" if has_poly else "kalshi_movement"
        with_movement = comparison[comparison[movement_col].notna()].copy()

        if not with_movement.empty:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 📈 Odds Shortened (Now Favored)")
                st.caption("Pre-tournament odds were longer than current live odds")
                shortened = with_movement[with_movement[movement_col] > 100].nlargest(10, movement_col)
                for _, row in shortened.iterrows():
                    pre = row.get("pre_polymarket") or row.get("pre_kalshi", 0)
                    live = row["live_odds_numeric"]
                    if pd.notna(pre) and pd.notna(live):
                        st.markdown(f"""
                        <div style="background: #00C85322; padding: 8px; border-radius: 6px; margin: 4px 0;">
                            <strong>{row['player_name']}</strong> ({row['position']})<br>
                            Pre: +{int(pre)} → Live: +{int(live)}
                            <span style="color: #00C853;"> (Shortened {int(pre - live)} pts)</span>
                        </div>
                        """, unsafe_allow_html=True)

            with col2:
                st.markdown("#### 📉 Odds Drifted (Less Favored)")
                st.caption("Live odds are longer than pre-tournament")
                drifted = with_movement[with_movement[movement_col] < -100].nsmallest(10, movement_col)
                for _, row in drifted.iterrows():
                    pre = row.get("pre_polymarket") or row.get("pre_kalshi", 0)
                    live = row["live_odds_numeric"]
                    if pd.notna(pre) and pd.notna(live):
                        st.markdown(f"""
                        <div style="background: #FF525222; padding: 8px; border-radius: 6px; margin: 4px 0;">
                            <strong>{row['player_name']}</strong> ({row['position']})<br>
                            Pre: +{int(pre)} → Live: +{int(live)}
                            <span style="color: #FF5252;"> (Drifted {int(live - pre)} pts)</span>
                        </div>
                        """, unsafe_allow_html=True)

    st.markdown("---")

    # Full odds table
    st.markdown("#### All Odds Comparison")
    display_cols = ["position", "player_name", "total", "odds_to_win"]
    if has_poly:
        display_cols.append("pre_polymarket")
    if has_kalshi:
        display_cols.append("pre_kalshi")

    display_df = comparison[[c for c in display_cols if c in comparison.columns]].head(30).copy()

    # Format odds columns
    for col in ["pre_polymarket", "pre_kalshi"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"+{int(x)}" if pd.notna(x) else "-")

    display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
    st.dataframe(display_df, hide_index=True, use_container_width=True)


def render_fantasy_lineup_tracker(live_df: pd.DataFrame):
    """Track fantasy lineup performance in real-time."""
    live_df = ensure_player_name_column(live_df)
    live_df["name_key"] = live_df["player_name"].apply(_name_key)

    usage_data = load_usage_data()
    picks = usage_data.get("picks", {})
    lineups = usage_data.get("weekly_lineups", {})

    if not picks and not lineups:
        st.info("No fantasy lineup data found. Add your picks to track them live.")
        return

    st.markdown("### Your Fantasy Lineup - Live Tracking")

    # Find current week's lineup
    current_lineup = None
    for week_key in sorted(lineups.keys(), key=lambda x: int(x.split("_")[1]), reverse=True):
        lineup = lineups[week_key]
        current_lineup = lineup
        break

    if current_lineup:
        st.markdown(f"**Week {current_lineup.get('week', '?')}:** {current_lineup.get('tournament', 'Tournament')}")

        lineup_players = current_lineup.get("lineup", [])
        bench_players = current_lineup.get("bench", [])

        if lineup_players:
            st.markdown("#### Active Lineup")

            total_score = 0
            lineup_data = []

            for player in lineup_players:
                player_key = _name_key(player)
                match = live_df[live_df["name_key"] == player_key]

                if not match.empty:
                    row = match.iloc[0]
                    pos = row.get("position", "")
                    total = row.get("total", "")
                    thru = row.get("thru", "")

                    # Calculate fantasy points (simplified)
                    pos_numeric = int(str(pos).replace("T", "")) if pos and str(pos).replace("T", "").isdigit() else 999
                    if pos_numeric == 1:
                        pts = 30
                    elif pos_numeric <= 5:
                        pts = 20
                    elif pos_numeric <= 10:
                        pts = 15
                    elif pos_numeric <= 20:
                        pts = 10
                    elif pos_numeric <= 40:
                        pts = 5
                    else:
                        pts = 0

                    total_score += pts
                    status = "🟢" if pos_numeric <= 20 else "🟡" if pos_numeric <= 40 else "🔴"

                    lineup_data.append({
                        "Status": status,
                        "Player": player,
                        "Position": pos,
                        "Score": total,
                        "Thru": thru,
                        "Est Points": pts
                    })
                else:
                    lineup_data.append({
                        "Status": "⚪",
                        "Player": player,
                        "Position": "-",
                        "Score": "-",
                        "Thru": "-",
                        "Est Points": 0
                    })

            st.dataframe(pd.DataFrame(lineup_data), hide_index=True, use_container_width=True)
            st.metric("Estimated Total Points", total_score)

        if bench_players:
            st.markdown("#### Bench")
            bench_data = []
            for player in bench_players:
                player_key = _name_key(player)
                match = live_df[live_df["name_key"] == player_key]
                if not match.empty:
                    row = match.iloc[0]
                    bench_data.append({
                        "Player": player,
                        "Position": row["position"],
                        "Score": row["total"]
                    })
                else:
                    bench_data.append({"Player": player, "Position": "-", "Score": "-"})

            st.dataframe(pd.DataFrame(bench_data), hide_index=True, use_container_width=True)
    else:
        # Show all tracked players
        st.markdown("#### All Tracked Players")

        tracked_data = []
        for player_name in picks.keys():
            player_key = _name_key(player_name)
            match = live_df[live_df["name_key"] == player_key]

            if not match.empty:
                row = match.iloc[0]
                uses = picks[player_name].get("times_used", 0)
                tracked_data.append({
                    "Player": player_name,
                    "Position": row["position"],
                    "Score": row["total"],
                    "Uses": f"{uses}/3"
                })

        if tracked_data:
            st.dataframe(pd.DataFrame(tracked_data), hide_index=True, use_container_width=True)


def load_performance_history() -> dict:
    """Load performance tracking history."""
    history_path = PERFORMANCE_DIR / "performance_history.json"
    if not history_path.exists():
        return {"tournaments": []}
    with open(history_path) as f:
        return json.load(f)


def render_performance_dashboard():
    """Render the performance tracking dashboard."""
    history = load_performance_history()
    tournaments = history.get("tournaments", [])

    if not tournaments:
        st.info("No performance data recorded yet. Complete a tournament and record results to see stats.")
        st.code("python3 scripts/analysis/track_performance.py --record R2026005 --name 'Tournament Name'")
        return

    # Aggregate metrics
    st.markdown("### Overall Performance")

    winner_correct = sum(1 for t in tournaments if t.get("metrics", {}).get("winner_correct"))
    top5_total = sum(t.get("metrics", {}).get("top5_hits", 0) for t in tournaments)
    top10_total = sum(t.get("metrics", {}).get("top10_hits", 0) for t in tournaments)
    top20_total = sum(t.get("metrics", {}).get("top20_hits", 0) for t in tournaments)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Tournaments", len(tournaments))
    with col2:
        pct = (winner_correct / len(tournaments) * 100) if tournaments else 0
        st.metric("Winner Correct", f"{winner_correct}/{len(tournaments)}", f"{pct:.0f}%")
    with col3:
        pct = (top5_total / (len(tournaments) * 5) * 100) if tournaments else 0
        st.metric("Top-5 Hits", f"{top5_total}/{len(tournaments)*5}", f"{pct:.0f}%")
    with col4:
        pct = (top10_total / (len(tournaments) * 10) * 100) if tournaments else 0
        st.metric("Top-10 Hits", f"{top10_total}/{len(tournaments)*10}", f"{pct:.0f}%")
    with col5:
        pct = (top20_total / (len(tournaments) * 20) * 100) if tournaments else 0
        st.metric("Top-20 Hits", f"{top20_total}/{len(tournaments)*20}", f"{pct:.0f}%")

    st.markdown("---")

    # ROI section
    st.markdown("### ROI Analysis")

    total_profit = 0
    total_bet = 0
    for t in tournaments:
        roi = t.get("roi", {})
        if "top10_finish_strategy" in roi:
            total_profit += roi["top10_finish_strategy"].get("profit", 0)
            total_bet += roi["top10_finish_strategy"].get("total_bet", 0)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Wagered", f"${total_bet:,.0f}")
    with col2:
        st.metric("Total Profit", f"${total_profit:,.0f}")
    with col3:
        roi_pct = (total_profit / total_bet * 100) if total_bet > 0 else 0
        st.metric("Overall ROI", f"{roi_pct:+.1f}%")

    st.markdown("---")

    # Per-tournament breakdown
    st.markdown("### Tournament Breakdown")

    table_data = []
    for t in tournaments:
        metrics = t.get("metrics", {})
        roi = t.get("roi", {}).get("top10_finish_strategy", {})

        table_data.append({
            "Tournament": t.get("tournament_name", t.get("tournament_id", "Unknown"))[:30],
            "Winner?": "Yes" if metrics.get("winner_correct") else "No",
            "Top-5": f"{metrics.get('top5_hits', 0)}/5",
            "Top-10": f"{metrics.get('top10_hits', 0)}/10",
            "Correlation": f"{metrics.get('rank_correlation', 0):.2f}" if metrics.get("rank_correlation") else "-",
            "ROI": f"{roi.get('roi_pct', 0):+.1f}%" if roi else "-",
        })

    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

    # Correlation chart
    correlations = [
        (t.get("tournament_name", "")[:15], t.get("metrics", {}).get("rank_correlation", 0))
        for t in tournaments
        if t.get("metrics", {}).get("rank_correlation") is not None
    ]

    if correlations:
        st.markdown("### Rank Correlation by Tournament")
        corr_df = pd.DataFrame(correlations, columns=["Tournament", "Correlation"])
        fig = px.bar(corr_df, x="Tournament", y="Correlation", title="Prediction Accuracy (higher = better)")
        fig.add_hline(y=0.5, line_dash="dash", line_color="green", annotation_text="Good")
        fig.add_hline(y=0.3, line_dash="dash", line_color="orange", annotation_text="Fair")
        st.plotly_chart(fig, use_container_width=True)


def render_course_fit_analysis():
    """Render enhanced course fit analysis."""
    st.markdown("### Course Fit Analysis")

    # Load predictions if available
    prediction_files = get_prediction_files()
    if not prediction_files:
        st.warning("No prediction files found")
        return

    file_options = {f.stem.replace('_predictions', '').replace('_', ' ').title(): f
                   for f in prediction_files[:10]}
    selected = st.selectbox("Select Tournament:", list(file_options.keys()), key="course_fit_select")
    df = pd.read_csv(file_options[selected])

    # SG Breakdown Analysis
    st.markdown("#### Strokes Gained Breakdown")

    sg_cols = [c for c in df.columns if c.startswith("sg_")]
    if sg_cols:
        # Top 20 players SG breakdown
        top20 = df.nlargest(20, "expected_value").copy()

        sg_data = []
        for _, row in top20.iterrows():
            for sg_col in sg_cols:
                sg_data.append({
                    "Player": row["player_name"][:20],
                    "Category": sg_col.replace("sg_", "").replace("_", " ").title(),
                    "Value": row.get(sg_col, 0)
                })

        if sg_data:
            sg_df = pd.DataFrame(sg_data)
            fig = px.bar(sg_df, x="Player", y="Value", color="Category", barmode="group",
                        title="Strokes Gained Breakdown - Top 20 Players")
            fig.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

    # Course History
    st.markdown("#### Course History")

    if "hist_times_played" in df.columns and "hist_avg_finish" in df.columns:
        with_history = df[df["hist_times_played"] > 0].copy()

        if not with_history.empty:
            # Sort by times played
            with_history = with_history.sort_values("hist_times_played", ascending=False).head(25)

            fig = px.scatter(
                with_history,
                x="hist_times_played",
                y="hist_avg_finish",
                size="expected_value",
                hover_data=["player_name"],
                title="Course Experience vs Average Finish"
            )
            fig.update_yaxes(autorange="reversed")  # Lower finish = better
            st.plotly_chart(fig, use_container_width=True)

            # Table
            history_df = with_history[["player_name", "hist_times_played", "hist_avg_finish", "expected_value"]].copy()
            history_df.columns = ["Player", "Times Played", "Avg Finish", "Expected Value"]
            history_df["Avg Finish"] = history_df["Avg Finish"].round(1)
            history_df["Expected Value"] = history_df["Expected Value"].apply(lambda x: f"${x:,.0f}")
            st.dataframe(history_df, hide_index=True, use_container_width=True)
    else:
        st.info("No course history data in predictions")

    # Player Radar Chart
    st.markdown("#### Player Comparison Radar")

    player_list = df["player_name"].tolist()
    selected_players = st.multiselect("Select players to compare (max 5):", player_list[:50], max_selections=5)

    if selected_players:
        radar_data = []
        categories = ["win_prob", "top5_prob", "top10_prob", "sg_total"]
        cat_labels = ["Win %", "Top-5 %", "Top-10 %", "SG Total"]

        for player in selected_players:
            player_row = df[df["player_name"] == player].iloc[0]
            values = []
            for cat in categories:
                val = player_row.get(cat, 0)
                if "prob" in cat:
                    val = val * 100  # Convert to percentage
                values.append(val)

            for i, (cat, val) in enumerate(zip(cat_labels, values)):
                radar_data.append({
                    "Player": player[:20],
                    "Category": cat,
                    "Value": val
                })

        if radar_data:
            radar_df = pd.DataFrame(radar_data)
            fig = px.line_polar(radar_df, r="Value", theta="Category", color="Player",
                               line_close=True, title="Player Comparison")
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# STATS ANALYSIS HELPERS
# ============================================================================

# --- Enhanced UI Components ---

def create_progress_bar(value: float, max_val: float = 100, color: str = "#4CAF50") -> str:
    """
    Create an HTML progress bar.

    Args:
        value: Current value (0-100 scale works best)
        max_val: Maximum value for scaling
        color: Bar color (hex or CSS color name)

    Returns:
        HTML string for the progress bar
    """
    # Normalize to 0-100 percentage
    pct = min(100, max(0, (value / max_val) * 100)) if max_val > 0 else 0

    return (
        f'<div style="background: #e0e0e0; border-radius: 4px; height: 8px; width: 100%; overflow: hidden;">'
        f'<div style="background: {color}; height: 100%; width: {pct}%; border-radius: 4px;"></div>'
        f'</div>'
    )


def create_sg_bar(value: float, label: str) -> str:
    """
    Create a strokes gained bar that shows positive (green) or negative (red).

    SG typically ranges from -2 to +2, with 0 being average.
    """
    # Normalize: -2 to +2 range → 0 to 100 for display
    # 0 SG = 50% (middle), +2 = 100%, -2 = 0%
    normalized = ((value + 2) / 4) * 100
    normalized = min(100, max(0, normalized))

    # Color based on value
    if value >= 0.5:
        color = "#00C853"  # Strong green
    elif value >= 0:
        color = "#4CAF50"  # Light green
    elif value >= -0.5:
        color = "#FF9800"  # Orange
    else:
        color = "#F44336"  # Red

    # Format value with sign
    val_str = f"+{value:.2f}" if value >= 0 else f"{value:.2f}"

    return (
        f'<div style="display: flex; align-items: center; margin: 4px 0;">'
        f'<span style="width: 45px; font-size: 0.85em; color: #666;">{label}</span>'
        f'<div style="flex: 1; background: #e0e0e0; border-radius: 4px; height: 12px; margin: 0 8px; overflow: hidden;">'
        f'<div style="background: {color}; height: 100%; width: {normalized}%; border-radius: 4px;"></div>'
        f'</div>'
        f'<span style="width: 50px; font-size: 0.85em; font-weight: bold; color: {color};">{val_str}</span>'
        f'</div>'
    )


def get_trend_indicator(value: float, thresholds: tuple = (0.3, -0.3)) -> str:
    """
    Return a trend indicator emoji based on value.

    Args:
        value: The metric value
        thresholds: (positive_threshold, negative_threshold)
    """
    pos_thresh, neg_thresh = thresholds
    if value >= pos_thresh:
        return "🔥"  # Hot
    elif value <= neg_thresh:
        return "❄️"  # Cold
    else:
        return "➖"  # Neutral


def get_form_badge(form_trend: float, recent_top10s: int = 0) -> str:
    """
    Generate a form badge based on recent performance.
    """
    if form_trend >= 0.5 or recent_top10s >= 3:
        return '<span style="background: #00C853; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: bold;">HOT 🔥</span>'
    elif form_trend >= 0.2:
        return '<span style="background: #4CAF50; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">WARM</span>'
    elif form_trend <= -0.5:
        return '<span style="background: #F44336; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: bold;">COLD ❄️</span>'
    elif form_trend <= -0.2:
        return '<span style="background: #FF9800; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">COOL</span>'
    else:
        return '<span style="background: #9E9E9E; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.75em;">NEUTRAL</span>'


def render_player_stat_card(player_data: dict) -> str:
    """
    Render a visual player stat card with all key metrics.

    This creates a card-style display with:
    - Player name and form badge
    - Form score with progress bar
    - SG breakdown bars
    - Recent results
    - Key stats
    """
    name = player_data.get("player_name", "Unknown")

    # Form metrics
    form_trend = player_data.get("form_trend", 0) or 0
    recent_top10s = int(player_data.get("recent_top10s", 0) or 0)
    recent_top5s = int(player_data.get("recent_top5s", 0) or 0)
    cuts_pct = (player_data.get("recent_cuts_pct", 0) or 0) * 100

    # SG metrics
    sg_total = player_data.get("sg_total", 0) or 0
    sg_ott = player_data.get("sg_ott", 0) or 0
    sg_app = player_data.get("sg_app", 0) or 0
    sg_arg = player_data.get("sg_arg", 0) or 0
    sg_putt = player_data.get("sg_putt", 0) or 0

    # World rank
    world_rank = int(player_data.get("world_rank", 999) or 999)
    rank_display = f"#{world_rank}" if world_rank < 999 else "NR"

    # Form badge
    form_badge = get_form_badge(form_trend, recent_top10s)

    # SG Total formatted
    sg_total_str = f"+{sg_total:.2f}" if sg_total >= 0 else f"{sg_total:.2f}"
    sg_color = "#00C853" if sg_total >= 0.5 else "#4CAF50" if sg_total >= 0 else "#F44336"

    # Keep this as compact HTML (no leading indentation/blank blocks), otherwise
    # Streamlit markdown can interpret chunks as code blocks and show raw tags.
    card_html = (
        f'<div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);'
        f' border-radius: 12px; padding: 16px; margin: 8px 0;'
        f' border: 1px solid #2a2a4a; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">'
        f'<div>'
        f'<span style="font-size: 1.2em; font-weight: bold; color: #fff;">{name}</span>'
        f'<span style="color: #888; margin-left: 8px;">{rank_display}</span>'
        f'</div>'
        f'{form_badge}'
        f'</div>'
        f'<div style="display: flex; justify-content: space-between; margin-bottom: 12px;'
        f' padding: 8px; background: #2a2a4a; border-radius: 8px;">'
        f'<div style="text-align: center;"><div style="color: {sg_color}; font-weight: bold; font-size: 1.1em;">{sg_total_str}</div><div style="color: #888; font-size: 0.75em;">SG Total</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{recent_top10s}</div><div style="color: #888; font-size: 0.75em;">Top-10s</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{recent_top5s}</div><div style="color: #888; font-size: 0.75em;">Top-5s</div></div>'
        f'<div style="text-align: center;"><div style="color: #fff; font-weight: bold; font-size: 1.1em;">{cuts_pct:.0f}%</div><div style="color: #888; font-size: 0.75em;">Cuts</div></div>'
        f'</div>'
        f'<div style="color: #aaa; font-size: 0.85em; margin-bottom: 6px;">Strokes Gained Breakdown</div>'
        f'<div style="background: #2a2a4a; border-radius: 8px; padding: 10px;">'
        f'{create_sg_bar(sg_ott, "OTT")}'
        f'{create_sg_bar(sg_app, "APP")}'
        f'{create_sg_bar(sg_arg, "ARG")}'
        f'{create_sg_bar(sg_putt, "PUTT")}'
        f'</div>'
        f'</div>'
    )

    return card_html


def render_mini_player_card(player_data: dict, rank: int = 0) -> str:
    """
    Render a compact player card for list views.
    """
    name = player_data.get("player_name", "Unknown")[:20]
    form_trend = player_data.get("form_trend", 0) or 0
    sg_total = player_data.get("sg_total", 0) or 0
    recent_top10s = int(player_data.get("recent_top10s", 0) or 0)

    # Trend indicator
    trend = "🔥" if form_trend >= 0.3 else "❄️" if form_trend <= -0.3 else ""

    # SG color
    sg_color = "#00C853" if sg_total >= 0.5 else "#4CAF50" if sg_total >= 0 else "#FF9800" if sg_total >= -0.5 else "#F44336"
    sg_str = f"+{sg_total:.2f}" if sg_total >= 0 else f"{sg_total:.2f}"

    # Form bar width
    form_width = int(min(100, max(0, (form_trend + 1) * 50)))

    return (
        f'<div style="display: flex; align-items: center; padding: 8px 12px; margin: 4px 0;'
        f' background: #1a1a2e; border-radius: 8px; border: 1px solid #2a2a4a;">'
        f'<span style="color: #666; width: 25px; font-size: 0.85em;">#{rank}</span>'
        f'<span style="flex: 1; color: #fff; font-weight: 500;">{name} {trend}</span>'
        f'<div style="width: 60px; background: #2a2a4a; border-radius: 4px; height: 6px; margin: 0 10px;">'
        f'<div style="background: {"#00C853" if form_trend > 0 else "#F44336"}; height: 100%; width: {form_width}%; border-radius: 4px;"></div>'
        f'</div>'
        f'<span style="color: {sg_color}; font-weight: bold; width: 50px; text-align: right;">{sg_str}</span>'
        f'<span style="color: #888; width: 40px; text-align: right; font-size: 0.85em;">{recent_top10s} T10</span>'
        f'</div>'
    )


def render_form_stats_section(df: pd.DataFrame):
    """
    Render enhanced form statistics with visual cards.
    """
    st.markdown("### 🔥 Player Form Analysis")

    # Quick filters
    col1, col2, col3 = st.columns(3)
    with col1:
        show_filter = st.selectbox("Show:", ["All", "Hot Players", "Cold Players", "Most Consistent"], key="form_filter")
    with col2:
        sort_by = st.selectbox("Sort by:", ["Form Trend", "SG Total", "Recent Top-10s", "World Rank"], key="form_sort")
    with col3:
        limit = st.slider("Players to show:", 5, 30, 15, key="form_limit")

    # Apply filters
    filtered_df = df.copy()

    if show_filter == "Hot Players":
        filtered_df = filtered_df[filtered_df["form_trend"] >= 0.2] if "form_trend" in filtered_df.columns else filtered_df
    elif show_filter == "Cold Players":
        filtered_df = filtered_df[filtered_df["form_trend"] <= -0.2] if "form_trend" in filtered_df.columns else filtered_df
    elif show_filter == "Most Consistent":
        if "finish_consistency" in filtered_df.columns:
            filtered_df = filtered_df.nsmallest(limit * 2, "finish_consistency")

    # Apply sorting
    sort_map = {
        "Form Trend": ("form_trend", False),
        "SG Total": ("sg_total", False),
        "Recent Top-10s": ("recent_top10s", False),
        "World Rank": ("world_rank", True)
    }
    sort_col, ascending = sort_map.get(sort_by, ("form_trend", False))
    if sort_col in filtered_df.columns:
        filtered_df = filtered_df.sort_values(sort_col, ascending=ascending)

    # Limit results
    filtered_df = filtered_df.head(limit)

    if filtered_df.empty:
        st.warning("No players match the current filter")
        return

    # Display mode toggle
    display_mode = st.radio("Display:", ["Cards", "List", "Table"], horizontal=True, key="form_display")

    if display_mode == "Cards":
        # Show detailed cards (2 per row)
        cols = st.columns(2)
        for idx, (_, row) in enumerate(filtered_df.iterrows()):
            with cols[idx % 2]:
                st.markdown(render_player_stat_card(row.to_dict()), unsafe_allow_html=True)

    elif display_mode == "List":
        # Compact list view
        st.markdown('<div style="background: #0e0e1a; border-radius: 12px; padding: 12px;">', unsafe_allow_html=True)
        for idx, (_, row) in enumerate(filtered_df.iterrows(), 1):
            st.markdown(render_mini_player_card(row.to_dict(), idx), unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        # Traditional table
        display_cols = ["player_name", "form_trend", "sg_total", "recent_top10s", "recent_top5s", "recent_cuts_pct"]
        display_df = filtered_df[[c for c in display_cols if c in filtered_df.columns]].copy()

        # Format columns
        if "form_trend" in display_df.columns:
            display_df["form_trend"] = display_df["form_trend"].round(2)
        if "sg_total" in display_df.columns:
            display_df["sg_total"] = display_df["sg_total"].round(2)
        if "recent_cuts_pct" in display_df.columns:
            display_df["recent_cuts_pct"] = (display_df["recent_cuts_pct"] * 100).round(0).astype(str) + "%"

        display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
        st.dataframe(display_df, hide_index=True, use_container_width=True)

    # Summary stats
    st.markdown("---")
    st.markdown("#### Field Summary")

    col1, col2, col3, col4 = st.columns(4)

    if "form_trend" in df.columns:
        hot_count = len(df[df["form_trend"] >= 0.3])
        cold_count = len(df[df["form_trend"] <= -0.3])
        with col1:
            st.metric("🔥 Hot Players", hot_count)
        with col2:
            st.metric("❄️ Cold Players", cold_count)

    if "sg_total" in df.columns:
        avg_sg = df["sg_total"].mean()
        with col3:
            st.metric("Field Avg SG", f"{avg_sg:+.2f}")

    if "recent_cuts_pct" in df.columns:
        avg_cuts = df["recent_cuts_pct"].mean() * 100
        with col4:
            st.metric("Avg Cut Rate", f"{avg_cuts:.0f}%")


def load_player_stats() -> pd.DataFrame:
    """
    Load compiled player stats from the latest predictions file.

    WHY: The predictions file contains pre-calculated stats for all players
    in the current tournament field, making it a convenient source for analysis.
    """
    pred_files = get_prediction_files()
    if not pred_files:
        return pd.DataFrame()

    # Load the most recent predictions file
    df = pd.read_csv(pred_files[0])
    return df


def render_strokes_gained_analysis(df: pd.DataFrame):
    """
    Render Strokes Gained deep dive analysis.

    WHAT IT SHOWS:
    - SG breakdown by category (OTT, APP, ARG, PUTT)
    - Comparison between recent form and season averages
    - Player rankings in each SG category
    - Visual breakdown charts
    """
    st.markdown("### Strokes Gained Breakdown")

    # Define the SG categories we want to analyze
    # These are the 4 main components that make up SG:Total
    sg_categories = {
        "sg_ott": "Off-the-Tee",      # Driving
        "sg_app": "Approach",          # Iron play
        "sg_arg": "Around Green",      # Short game
        "sg_putt": "Putting"           # Putting
    }

    # Check which columns exist in our data
    available_sg = [col for col in sg_categories.keys() if col in df.columns]

    if not available_sg:
        st.warning("No Strokes Gained data available")
        return

    # --- Section 0: Visual Top Performers Cards ---
    if "sg_total" in df.columns:
        st.markdown("#### 🏆 Top SG Performers")
        st.caption("Visual breakdown of the top strokes gained performers")

        # Get top 3 by SG Total for visual cards
        top3_sg = df.nlargest(3, "sg_total")

        cols = st.columns(3)
        for i, (_, player) in enumerate(top3_sg.iterrows()):
            with cols[i]:
                # Create visual card for each top performer
                card_html = render_player_stat_card(player.to_dict())
                st.markdown(card_html, unsafe_allow_html=True)

        st.markdown("---")

    # --- Section 1: Top 10 by SG Total ---
    st.markdown("#### Top 10 by SG: Total")

    if "sg_total" in df.columns:
        # Get top 10 players by SG Total
        top10_sg = df.nlargest(10, "sg_total")[["player_name", "sg_total"] + available_sg].copy()

        # Round for display
        for col in ["sg_total"] + available_sg:
            if col in top10_sg.columns:
                top10_sg[col] = top10_sg[col].round(2)

        # Rename columns for display
        display_cols = {"player_name": "Player", "sg_total": "SG Total"}
        display_cols.update({k: v for k, v in sg_categories.items() if k in available_sg})
        top10_sg = top10_sg.rename(columns=display_cols)

        st.dataframe(top10_sg, hide_index=True, use_container_width=True)

    # --- Section 2: SG Breakdown Chart ---
    st.markdown("#### SG Category Breakdown - Top 20 Players")

    # Get top 20 players for the chart
    if "sg_total" in df.columns:
        top20 = df.nlargest(20, "sg_total").copy()
    else:
        top20 = df.head(20).copy()

    # Prepare data for stacked bar chart
    # We'll show each SG component stacked for each player
    chart_data = []
    for _, row in top20.iterrows():
        player = row["player_name"][:15]  # Truncate long names
        for sg_col, sg_name in sg_categories.items():
            if sg_col in df.columns:
                chart_data.append({
                    "Player": player,
                    "Category": sg_name,
                    "Value": row.get(sg_col, 0) or 0
                })

    if chart_data:
        chart_df = pd.DataFrame(chart_data)

        # Create grouped bar chart using Plotly
        fig = px.bar(
            chart_df,
            x="Player",
            y="Value",
            color="Category",
            barmode="group",  # Side-by-side bars
            title="SG Breakdown by Player",
            color_discrete_map={
                "Off-the-Tee": "#2196F3",   # Blue for driving
                "Approach": "#4CAF50",       # Green for approach
                "Around Green": "#FF9800",   # Orange for short game
                "Putting": "#9C27B0"         # Purple for putting
            }
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # --- Section 2.5: Category Leaders ---
    st.markdown("#### 🥇 Category Leaders")
    st.caption("Top performer in each strokes gained category")

    cat_cols = st.columns(4)
    cat_colors = {
        "sg_ott": ("#2196F3", "🎯", "Off-the-Tee"),
        "sg_app": ("#4CAF50", "⛳", "Approach"),
        "sg_arg": ("#FF9800", "🏌️", "Around Green"),
        "sg_putt": ("#9C27B0", "🕳️", "Putting")
    }

    for i, (sg_col, (color, emoji, label)) in enumerate(cat_colors.items()):
        if sg_col in df.columns:
            with cat_cols[i]:
                # Get top player in this category
                top_player = df.nlargest(1, sg_col).iloc[0]
                player_name = top_player["player_name"][:15]
                sg_value = top_player[sg_col]
                sg_str = f"+{sg_value:.2f}" if sg_value >= 0 else f"{sg_value:.2f}"

                # Create visual card for category leader
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, {color}22, {color}11);
                            border: 2px solid {color}; border-radius: 12px;
                            padding: 12px; text-align: center;">
                    <div style="font-size: 1.5em;">{emoji}</div>
                    <div style="color: #888; font-size: 0.8em; margin: 4px 0;">{label}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1em;">{player_name}</div>
                    <div style="color: {color}; font-weight: bold; font-size: 1.2em;">{sg_str}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # --- Section 3: Season vs Recent Form Comparison ---
    st.markdown("#### Season Average vs Recent Form")
    st.caption("Compare a player's season-long stats with their recent tournament form")

    # Check if we have both season and recent SG stats
    season_cols = ["season_sg_ott", "season_sg_app", "season_sg_arg", "season_sg_putt"]
    recent_cols = ["sg_ott", "sg_app", "sg_arg", "sg_putt"]

    has_season = any(col in df.columns for col in season_cols)
    has_recent = any(col in df.columns for col in recent_cols)

    if has_season and has_recent:
        # Let user select a player to analyze
        player_list = df["player_name"].dropna().tolist()
        selected_player = st.selectbox("Select Player:", player_list[:50], key="sg_player_select")

        if selected_player:
            player_row = df[df["player_name"] == selected_player].iloc[0]

            # Build comparison data
            comparison_data = []
            for i, (season_col, recent_col) in enumerate(zip(season_cols, recent_cols)):
                category = list(sg_categories.values())[i]
                season_val = player_row.get(season_col, 0) or 0
                recent_val = player_row.get(recent_col, 0) or 0

                comparison_data.append({"Category": category, "Type": "Season Avg", "Value": season_val})
                comparison_data.append({"Category": category, "Type": "Recent Form", "Value": recent_val})

            comp_df = pd.DataFrame(comparison_data)

            # Create comparison chart
            fig = px.bar(
                comp_df,
                x="Category",
                y="Value",
                color="Type",
                barmode="group",
                title=f"{selected_player} - Season vs Recent Form",
                color_discrete_map={"Season Avg": "#78909C", "Recent Form": "#00BCD4"}
            )
            st.plotly_chart(fig, use_container_width=True)

            # Show insight
            for i, (season_col, recent_col) in enumerate(zip(season_cols, recent_cols)):
                category = list(sg_categories.values())[i]
                season_val = player_row.get(season_col, 0) or 0
                recent_val = player_row.get(recent_col, 0) or 0
                diff = recent_val - season_val

                if abs(diff) > 0.3:  # Significant difference threshold
                    if diff > 0:
                        st.success(f"🔥 **{category}**: Recent form is {diff:.2f} strokes better than season average")
                    else:
                        st.warning(f"📉 **{category}**: Recent form is {abs(diff):.2f} strokes worse than season average")


def render_form_analysis(df: pd.DataFrame):
    """
    Render player form analysis.

    WHAT IT SHOWS:
    - Recent results (last 5-10 tournaments)
    - Form trends (hot/cold streaks)
    - Consistency metrics
    - Cut-making percentages
    """
    st.markdown("### Form Analysis")

    # --- Section 1: Form Metrics Overview ---
    form_cols = ["form_trend", "recent_top10s", "recent_top5s", "recent_cuts_pct", "finish_consistency"]
    available_form = [col for col in form_cols if col in df.columns]

    if not available_form:
        st.warning("No form data available")
        return

    # Hot players (high form trend)
    if "form_trend" in df.columns:
        st.markdown("#### 🔥 Hottest Players (Form Trend)")
        st.caption("Form trend measures recent performance vs expected - higher = playing above expectations")

        hot_players = df.nlargest(10, "form_trend")[["player_name", "form_trend", "recent_top10s", "recent_cuts_pct"]].copy()

        # Format for display
        hot_players["form_trend"] = hot_players["form_trend"].round(2)
        if "recent_top10s" in hot_players.columns:
            hot_players["recent_top10s"] = hot_players["recent_top10s"].fillna(0).astype(int)
        if "recent_cuts_pct" in hot_players.columns:
            hot_players["recent_cuts_pct"] = (hot_players["recent_cuts_pct"] * 100).round(0).astype(str) + "%"

        hot_players.columns = ["Player", "Form Trend", "Recent Top-10s", "Cut %"]
        st.dataframe(hot_players, hide_index=True, use_container_width=True)

    # Cold players
    if "form_trend" in df.columns:
        st.markdown("#### ❄️ Coldest Players")
        cold_players = df.nsmallest(10, "form_trend")[["player_name", "form_trend", "recent_top10s", "recent_cuts_pct"]].copy()

        cold_players["form_trend"] = cold_players["form_trend"].round(2)
        if "recent_top10s" in cold_players.columns:
            cold_players["recent_top10s"] = cold_players["recent_top10s"].fillna(0).astype(int)
        if "recent_cuts_pct" in cold_players.columns:
            cold_players["recent_cuts_pct"] = (cold_players["recent_cuts_pct"] * 100).round(0).astype(str) + "%"

        cold_players.columns = ["Player", "Form Trend", "Recent Top-10s", "Cut %"]
        st.dataframe(cold_players, hide_index=True, use_container_width=True)

    # --- Section 2: Form Distribution ---
    st.markdown("#### Form Distribution")

    if "form_trend" in df.columns:
        fig = px.histogram(
            df,
            x="form_trend",
            nbins=30,
            title="Field Form Trend Distribution",
            labels={"form_trend": "Form Trend"}
        )
        fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Average")
        st.plotly_chart(fig, use_container_width=True)

    # --- Section 3: Consistency Analysis ---
    st.markdown("#### Consistency vs Upside")
    st.caption("X-axis = consistency (lower = more consistent), Y-axis = recent form")

    if "finish_consistency" in df.columns and "form_trend" in df.columns:
        # Scatter plot of consistency vs form
        fig = px.scatter(
            df.head(50),  # Top 50 players
            x="finish_consistency",
            y="form_trend",
            hover_data=["player_name"],
            title="Consistency vs Form Trend",
            labels={
                "finish_consistency": "Finish Consistency (lower = more consistent)",
                "form_trend": "Form Trend (higher = hotter)"
            }
        )

        # Add quadrant labels
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_vline(x=df["finish_consistency"].median(), line_dash="dash", line_color="gray")

        st.plotly_chart(fig, use_container_width=True)

        st.info("""
        **How to read this chart:**
        - **Top-Left**: Hot AND consistent (ideal!)
        - **Top-Right**: Hot but inconsistent (boom-or-bust)
        - **Bottom-Left**: Cold but consistent (steady decline)
        - **Bottom-Right**: Cold and inconsistent (avoid)
        """)


def render_course_specific_stats(df: pd.DataFrame):
    """
    Render course-specific statistics.

    WHAT IT SHOWS:
    - Historical performance at the current course
    - Similar courses analysis
    - Course fit metrics (how well player's game fits the course)
    """
    st.markdown("### Course-Specific Analysis")

    # --- Section 0: Top Course Fits Visual Cards ---
    fit_cols = ["dg_fit_total", "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt"]
    if "dg_fit_total" in df.columns:
        st.markdown("#### 🎯 Best Course Fits")
        st.caption("Players whose game best matches this course")

        top3_fits = df.nlargest(3, "dg_fit_total")
        fit_cols = st.columns(3)

        for i, (_, player) in enumerate(top3_fits.iterrows()):
            with fit_cols[i]:
                name = player.get("player_name", "Unknown")[:18]
                fit_total = player.get("dg_fit_total", 0) or 0
                fit_str = f"+{fit_total:.2f}" if fit_total >= 0 else f"{fit_total:.2f}"

                # Get individual fits
                ott_fit = player.get("dg_fit_ott", 0) or 0
                app_fit = player.get("dg_fit_app", 0) or 0
                arg_fit = player.get("dg_fit_arg", 0) or 0
                putt_fit = player.get("dg_fit_putt", 0) or 0

                # Ranking badge
                rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
                rank_labels = ["1st", "2nd", "3rd"]

                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                            border-radius: 12px; padding: 16px; margin: 4px 0;
                            border: 2px solid {rank_colors[i]}; text-align: center;">
                    <div style="display: inline-block; background: {rank_colors[i]}; color: #000;
                                padding: 2px 10px; border-radius: 12px; font-size: 0.8em;
                                font-weight: bold; margin-bottom: 8px;">{rank_labels[i]}</div>
                    <div style="font-weight: bold; color: #fff; font-size: 1.1em; margin: 8px 0;">{name}</div>
                    <div style="color: #00C853; font-size: 1.4em; font-weight: bold;">{fit_str}</div>
                    <div style="color: #888; font-size: 0.75em; margin-top: 4px;">Course Fit Score</div>
                    <div style="display: flex; justify-content: space-around; margin-top: 10px;
                                padding-top: 10px; border-top: 1px solid #2a2a4a;">
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if ott_fit >= 0 else "#F44336"}; font-size: 0.9em;">{ott_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">OTT</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if app_fit >= 0 else "#F44336"}; font-size: 0.9em;">{app_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">APP</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if arg_fit >= 0 else "#F44336"}; font-size: 0.9em;">{arg_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">ARG</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="color: {"#4CAF50" if putt_fit >= 0 else "#F44336"}; font-size: 0.9em;">{putt_fit:+.1f}</div>
                            <div style="color: #666; font-size: 0.65em;">PUTT</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

    # --- Section 1: Course History ---
    st.markdown("#### Course History")

    history_cols = ["hist_times_played", "hist_avg_finish", "hist_best_finish", "hist_wins", "hist_top10s"]
    available_hist = [col for col in history_cols if col in df.columns]

    if available_hist and "hist_times_played" in df.columns:
        # Players with course history
        with_history = df[df["hist_times_played"] > 0].copy()

        if not with_history.empty:
            st.caption(f"Players with course experience: {len(with_history)}")

            # Sort by times played (experience matters)
            course_vets = with_history.nlargest(15, "hist_times_played")[
                ["player_name"] + available_hist
            ].copy()

            # Format columns
            if "hist_avg_finish" in course_vets.columns:
                course_vets["hist_avg_finish"] = course_vets["hist_avg_finish"].round(1)

            # Rename for display
            col_names = {
                "player_name": "Player",
                "hist_times_played": "Times Played",
                "hist_avg_finish": "Avg Finish",
                "hist_best_finish": "Best Finish",
                "hist_wins": "Wins",
                "hist_top10s": "Top-10s"
            }
            course_vets = course_vets.rename(columns={k: v for k, v in col_names.items() if k in course_vets.columns})

            st.dataframe(course_vets, hide_index=True, use_container_width=True)
        else:
            st.info("No players have course history data")

    # --- Section 2: Course Fit Analysis ---
    st.markdown("#### Course Fit Score")
    st.caption("How well does each player's game fit this course?")

    fit_cols = ["dg_fit_total", "dg_fit_ott", "dg_fit_app", "dg_fit_arg", "dg_fit_putt"]
    available_fit = [col for col in fit_cols if col in df.columns]

    if available_fit and "dg_fit_total" in df.columns:
        # Top course fits
        top_fits = df.nlargest(15, "dg_fit_total")[["player_name"] + available_fit].copy()

        # Round values
        for col in available_fit:
            if col in top_fits.columns:
                top_fits[col] = top_fits[col].round(2)

        # Rename columns
        fit_names = {
            "player_name": "Player",
            "dg_fit_total": "Total Fit",
            "dg_fit_ott": "OTT Fit",
            "dg_fit_app": "APP Fit",
            "dg_fit_arg": "ARG Fit",
            "dg_fit_putt": "Putt Fit"
        }
        top_fits = top_fits.rename(columns={k: v for k, v in fit_names.items() if k in top_fits.columns})

        st.dataframe(top_fits, hide_index=True, use_container_width=True)

        # Explain course fit
        st.info("""
        **Course Fit Score** predicts how well a player's strengths match this course:
        - **Positive** = Player's game suits this course
        - **Negative** = Course exposes player's weaknesses
        - Based on historical correlations between SG categories and performance at this venue
        """)

    # --- Section 3: Course History vs Current Form ---
    st.markdown("#### Experience + Form Combo")
    st.caption("Best combination of course experience AND current form")

    if "hist_times_played" in df.columns and "form_trend" in df.columns:
        # Create combo score
        combo_df = df.copy()
        combo_df["has_history"] = combo_df["hist_times_played"] > 0

        # Filter to players with history
        experienced = combo_df[combo_df["has_history"]].copy()

        if not experienced.empty:
            # Scatter: experience vs form
            fig = px.scatter(
                experienced,
                x="hist_times_played",
                y="form_trend",
                size="hist_top10s" if "hist_top10s" in experienced.columns else None,
                hover_data=["player_name", "hist_avg_finish"],
                title="Course Experience vs Current Form",
                labels={
                    "hist_times_played": "Times Played at Course",
                    "form_trend": "Current Form Trend"
                }
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================================
# SIDEBAR
# ============================================================================

# Sidebar header
st.sidebar.markdown("## ⛳ Golf Fantasy")
st.sidebar.markdown("---")

# Navigation (consolidated)
page = st.sidebar.radio(
    "📍 Navigation",
    ["🏆 This Week", "🎯 Scoring Engine", "🎰 Betting", "👤 Players", "📊 Predictions", "🔴 Live", "📋 My Picks", "⚙️ Pipeline"],
    label_visibility="collapsed"
)

# Quick stats in sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Quick Stats")

usage_data = load_usage_data()
picks = usage_data.get("picks", {})
total_picks = sum(p.get("times_used", 0) for p in picks.values())
total_points = sum(p.get("total_points", 0) for p in picks.values())

st.sidebar.metric("Picks Made", f"{total_picks}/90")
st.sidebar.metric("Points", total_points)
st.sidebar.metric("Players Used", len(picks))

st.sidebar.markdown("---")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%b %d, %Y %H:%M')}")


# ============================================================================
# PAGE: THIS WEEK (consolidated from Strategy Dashboard + This Week + Scoring Engine)
# ============================================================================

if page == "🏆 This Week":
    st.markdown("## 📅 This Week's Tournament")

    engine = load_scoring_engine()

    if engine:
        tournament = engine.get_current_week_tournament()

        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            course_info = engine.tournament_courses.get(tournament, {})

            # Tournament info
            st.markdown(f"### {tournament}")

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Week", t.week)
            with col2:
                st.metric("Purse", f"${t.purse/1e6:.1f}M")
            with col3:
                st.metric("Type", t.tournament_type)
            with col4:
                st.metric("Importance", f"{t.importance_score:.0f}/100")
            with col5:
                st.metric("Course", t.course or "TBD")

            if course_info:
                st.info(f"**{course_info.get('course_type', 'Unknown')} course** — {course_info.get('notes', '')}")

            # Weather widget
            render_weather_widget(t.course or tournament)

            st.markdown("---")

            # Tabs for different views
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🎯 Recommendations", "🏌️ Course Specialists", "📊 Field Analysis", "🎯 Course Fit", "Course History", "📝 Player Profiles"])
            

            with tab1:
                recommendations = engine.get_tournament_recommendations(tournament, top_n=20)

                rec_data = []
                for i, score in enumerate(recommendations, 1):
                    warning = ""
                    if score.remaining_uses == 0:
                        warning = "❌"
                    elif score.remaining_uses == 1:
                        warning = "⚠️"
                    elif score.owgr_rank <= 10 and t.importance_score < 50:
                        warning = "💡"

                    rec_data.append({
                        "Rank": i,
                        "Player": score.player,
                        "Total Score": score.total_score,
                        "Course Fit": score.course_fit,
                        "Current Form": score.current_form,
                        "Uses Left": f"{warning} {score.remaining_uses}/3".strip(),
                        "Course History": score.course_history_note or "No history"
                    })

                st.dataframe(
                    pd.DataFrame(rec_data),
                    column_config={
                        "Total Score": st.column_config.ProgressColumn(min_value=0, max_value=100),
                        "Course Fit": st.column_config.ProgressColumn(min_value=0, max_value=100),
                        "Current Form": st.column_config.ProgressColumn(min_value=0, max_value=100),
                    },
                    hide_index=True,
                    use_container_width=True
                )

            with tab2:
                st.markdown("### 🏌️ Players Who Excel Here")

                aliases = course_info.get("aliases", [])
                specialists = []

                if engine.course_db:
                    for alias in aliases:
                        specs = engine.course_db.get_course_specialists(alias, min_plays=2)
                        for player, stats, fit_score in specs:
                            if fit_score >= 50:
                                specialists.append({
                                    "Player": player.title(),
                                    "Plays": stats.times_played,
                                    "Wins": stats.wins,
                                    "Top 5s": stats.top_5s,
                                    "Avg Finish": round(stats.avg_finish, 1),
                                    "Fit Score": round(fit_score)
                                })
                        if specialists:
                            break

                if specialists:
                    seen = set()
                    unique = []
                    for s in specialists:
                        key = s["Player"].lower()
                        if key not in seen:
                            seen.add(key)
                            unique.append(s)

                    st.dataframe(
                        pd.DataFrame(unique[:15]),
                        column_config={
                            "Fit Score": st.column_config.ProgressColumn(min_value=0, max_value=100),
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Limited course history data available for this venue")

            with tab3:
                st.markdown("### 📊 Field Overview")

                if engine.predictions:
                    # World rank distribution
                    ranks = [p.owgr_rank for p in engine.predictions.values() if p.owgr_rank < 500]

                    col1, col2 = st.columns(2)

                    with col1:
                        fig = px.histogram(ranks, nbins=20, title="Field Strength (World Rankings)")
                        fig.update_layout(showlegend=False, xaxis_title="World Rank", yaxis_title="Players")
                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        # Top players in field
                        top_players = sorted(engine.predictions.items(), key=lambda x: x[1].owgr_rank)[:10]
                        st.markdown("**Top 10 in Field:**")
                        for player, form in top_players:
                            st.caption(f"#{form.owgr_rank} {player}")

                st.markdown("---")
                st.markdown("### 👥 Full Field List")

                col1, col2, col3 = st.columns(3)
                with col1:
                    show_field = st.button("👥 Full Field", use_container_width=True, type="primary")
                with col2:
                    show_top_30 = st.button("⭐ Top 30", use_container_width=True)
                with col3:
                    show_top_50 = st.button("★ Top 50", use_container_width=True)

                if show_field:
                    with st.spinner("Loading field..."):
                        output = run_script("planning/field_viewer.py")
                    st.code(output, language=None)

                if show_top_30:
                    with st.spinner("Loading top 30..."):
                        output = run_script("planning/field_viewer.py", "--top", "30")
                    st.code(output, language=None)

                if show_top_50:
                    with st.spinner("Loading top 50..."):
                        output = run_script("planning/field_viewer.py", "--top", "50")
                    st.code(output, language=None)

            with tab4:
                st.markdown("### 🎯 Course Fit Analysis")

                # Course profile button
                col1, col2 = st.columns(2)
                with col1:
                    show_course_profile = st.button("🏟️ Course Profile", use_container_width=True, type="primary")
                with col2:
                    pass

                if show_course_profile:
                    with st.spinner("Loading course profile..."):
                        output = run_script("planning/course_fit.py", "--course", tournament)
                    st.code(output, language=None)
                    
                
                st.markdown("---")
                st.markdown("**📊 Course Toughness Rankings")
                if st.button("📊 Course Toughness Rankings", use_container_width=True):                               
                    output = run_script("planning/course_stats_viewer.py")                                            
                    st.code(output, language=None)     

                st.markdown("---")
                st.markdown("**Check Player Fit for This Course:**")

                all_players = sorted(engine.predictions.keys()) if engine.predictions else []
                col1, col2 = st.columns([3, 1])
                with col1:
                    fit_player = st.selectbox("Select player:", [""] + all_players, key="fit_player")
                with col2:
                    check_fit = st.button("🎯 Check Fit", use_container_width=True, type="primary")

                if check_fit and fit_player:
                    with st.spinner(f"Analyzing {fit_player}'s course fit..."):
                        output = run_script("planning/course_fit.py", fit_player)
                    st.code(output, language=None)

            with tab5:
                st.markdown("### 📅 Course History")
                # Course Specialist button 
                if st.button("🏆 Couse Specialists (Historical)", use_container_width=True, type="primary"):
                    with st.spinner("Loading course specialists..."):
                        output = run_script("planning/course_history.py", "--tournament", tournament)
                    st.code(output, language=None)
                st.markdown("---")
                st.markdown("**Player Course History:**")
                all_players = sorted(engine.predictions.keys()) if engine.predictions else []
                col1, col2 = st.columns([3, 1])
                with col1:
                    hist_player = st.selectbox("Select player:", [""] + all_players, key="hist_player")
                with col2:
                    check_hist = st.button("📊 View History", use_container_width=True, type='primary')
                
                if check_hist and hist_player:
                    with st.spinner(f"Loading {hist_player}'s course history..."):
                        output = run_script("planning/course_history.py", hist_player)
                    st.code(output, language=None)

            with tab6:
                st.markdown("### 📝 Player Betting Profiles")                                                         
                st.caption("AI-generated insights from PGA Tour betting profiles")                                    
                                                                                                                    
                # Get tournament ID for loading profiles                                                              
                schedule = load_schedule()                                                                            
                tournament_id = None                                                                                  
                if not schedule.empty:                                                                                
                    match = schedule[schedule['tournament_name'] == tournament]                                       
                    if not match.empty:                                                                               
                        tournament_id = match.iloc[0].get('tournament_id', '')                                        
                                                                                                                    
                # Load betting profiles                                                                               
                profiles_df = load_betting_profiles(tournament_id)                                                    
                                                                                                                    
                if profiles_df.empty:                                                                                 
                    st.warning("No betting profiles available for this tournament. Run the weekly prep to fetch them.")                                                                                                               
                else:                                                                                                 
                    st.success(f"✓ {len(profiles_df)} player profiles loaded")                                        
                                                                                                                    
                    # Player selector                                                                                 
                    all_players = sorted(engine.predictions.keys()) if engine.predictions else []                     
                                                                                                                    
                    profile_player = st.selectbox(                                                                    
                        "Select a player to view their betting profile:",                                             
                        [""] + all_players,                                                                           
                        key="profile_player"                                                                          
                    )                                                                                                 
                                                                                                                    
                    if profile_player:                                                                                
                        profile = get_player_profile(profiles_df, profile_player)                                     
                                                                                                                    
                        if profile:                                                                                   
                            render_player_profile_card(profile, show_full=True)                                       
                        else:                                                                                         
                            st.info(f"No betting profile found for {profile_player}. They may not be in the field or the profile wasn't published.") 
               

# ============================================================================
# PAGE: SCORING ENGINE
# ============================================================================

elif page == "🎯 Scoring Engine":
    st.markdown("## 🎯 Scoring Engine")
    st.caption("Fantasy league scoring and recommendations")

    engine = load_scoring_engine()

    # Current tournament header card
    if engine:
        tournament = engine.get_current_week_tournament()
        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            course_info = engine.tournament_courses.get(tournament, {})

            # Tournament card - enhanced
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                        padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h2 style="margin: 0; color: #fff;">{tournament}</h2>
                <p style="color: #aaa; margin: 5px 0;">{t.course or t.location} • Week {t.week} • {t.start_date}</p>
                <div style="display: flex; gap: 30px; margin-top: 15px;">
                    <div><span style="color: #4CAF50; font-size: 24px; font-weight: bold;">{t.tournament_type}</span><br><span style="color: #888; font-size: 12px;">TYPE</span></div>
                    <div><span style="color: #2196F3; font-size: 24px; font-weight: bold;">${t.purse/1_000_000:.1f}M</span><br><span style="color: #888; font-size: 12px;">PURSE</span></div>
                    <div><span style="color: #FF9800; font-size: 24px; font-weight: bold;">{t.importance_score:.0f}</span><br><span style="color: #888; font-size: 12px;">IMPORTANCE</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if course_info.get("notes"):
                st.info(f"💡 {course_info.get('notes')}")

    # Show current scoring weights
    with st.expander("⚙️ Current Scoring Weights", expanded=False):
        w_col1, w_col2, w_col3, w_col4 = st.columns(4)
        with w_col1:
            st.metric("Importance", "25%", help="Tournament prestige/purse")
        with w_col2:
            st.metric("Course Fit", "25%", delta="-10%", delta_color="off", help="Historical performance at venue")
        with w_col3:
            st.metric("Form", "30%", delta="+5%", help="Recent results, hot hand")
        with w_col4:
            st.metric("Field", "20%", delta="+5%", help="Relative field difficulty")
        st.caption("*Weights optimized on 2026-02-16 based on backtest results*")

    st.markdown("---")

    # Tabs for different functions
    se_tab1, se_tab2, se_tab3, se_tab4 = st.tabs(["🏆 Top Picks", "💎 Value Plays", "📊 Full Rankings", "📰 Reports"])

    with se_tab1:
        st.markdown("### 🏆 Top Picks for This Week")

        # Get scores from engine
        if engine and tournament:
            scores = engine.get_tournament_recommendations(tournament, top_n=100, min_uses=0)
            scores_sorted = sorted(scores, key=lambda x: x.total_score, reverse=True)[:15]

            if scores_sorted:
                # Top 3 cards
                st.markdown("#### 🥇 Top 3 Recommendations")
                top3_cols = st.columns(3)
                medals = ["🥇", "🥈", "🥉"]

                for i, score in enumerate(scores_sorted[:3]):
                    with top3_cols[i]:
                        uses_left = engine.usage.get(score.player, 3)
                        rating_color = {"ELITE": "#4CAF50", "STRONG": "#2196F3", "SOLID": "#FF9800"}.get(score.value_rating, "#666")

                        st.markdown(f"""
                        <div style="background: #1e1e1e; padding: 15px; border-radius: 10px;
                                    border-left: 4px solid {rating_color}; text-align: center;">
                            <div style="font-size: 28px;">{medals[i]}</div>
                            <div style="font-size: 18px; font-weight: bold; margin: 10px 0;">{score.player}</div>
                            <div style="font-size: 32px; color: {rating_color}; font-weight: bold;">{score.total_score:.0f}</div>
                            <div style="font-size: 12px; color: #888;">TOTAL SCORE</div>
                            <hr style="border-color: #333; margin: 10px 0;">
                            <div style="display: flex; justify-content: space-around; font-size: 11px;">
                                <div><span style="color: #4CAF50;">{score.course_fit:.0f}</span><br>Course</div>
                                <div><span style="color: #2196F3;">{score.current_form:.0f}</span><br>Form</div>
                                <div><span style="color: #FF9800;">{score.field_strength:.0f}</span><br>Field</div>
                            </div>
                            <div style="margin-top: 10px; font-size: 12px; color: #aaa;">
                                {uses_left}/3 uses left • OWGR #{score.owgr_rank}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                # Rest of top 15
                st.markdown("#### 📋 Next Best Options")
                for i, score in enumerate(scores_sorted[3:15], start=4):
                    uses_left = engine.usage.get(score.player, 3)
                    col1, col2, col3, col4, col5, col6 = st.columns([0.5, 3, 1, 1, 1, 1])
                    with col1:
                        st.markdown(f"**{i}**")
                    with col2:
                        st.markdown(f"**{score.player}**")
                        st.caption(f"#{score.owgr_rank} • {score.form_trend} • {uses_left}/3 uses")
                    with col3:
                        st.metric("Total", f"{score.total_score:.0f}", label_visibility="collapsed")
                    with col4:
                        st.metric("Course", f"{score.course_fit:.0f}", label_visibility="collapsed")
                    with col5:
                        st.metric("Form", f"{score.current_form:.0f}", label_visibility="collapsed")
                    with col6:
                        rating_emoji = {"ELITE": "🔥", "STRONG": "💪", "SOLID": "✅", "FAIR": "➖"}.get(score.value_rating, "")
                        st.markdown(f"{rating_emoji} {score.value_rating}")
            else:
                st.warning("No scores available. Run the pipeline first.")
        else:
            st.info("Loading scoring engine...")

    with se_tab2:
        st.markdown("### 💎 Value Picks")
        st.caption("Mid-ranked players (OWGR 20-60) with high scores - save elite players for majors!")

        if engine and tournament:
            scores = engine.get_tournament_recommendations(tournament, top_n=100, min_uses=0)
            # Filter for value picks: rank 20-60 with good scores
            value_picks = [s for s in scores if 20 <= s.owgr_rank <= 80 and s.total_score >= 45]
            value_picks = sorted(value_picks, key=lambda x: x.total_score, reverse=True)[:10]

            if value_picks:
                for i, score in enumerate(value_picks, start=1):
                    uses_left = engine.usage.get(score.player, 3)
                    edge = score.total_score - 50  # vs baseline

                    col1, col2, col3 = st.columns([3, 1, 2])
                    with col1:
                        st.markdown(f"**{i}. {score.player}**")
                        st.caption(f"OWGR #{score.owgr_rank} • {score.form_trend} form • {uses_left}/3 uses")
                    with col2:
                        st.metric("Score", f"{score.total_score:.0f}", f"+{edge:.0f}")
                    with col3:
                        # Mini bar chart
                        st.progress(min(1.0, score.course_fit / 100), text=f"Course: {score.course_fit:.0f}")
                        st.progress(min(1.0, score.current_form / 100), text=f"Form: {score.current_form:.0f}")
            else:
                st.info("No value picks found matching criteria.")

    with se_tab3:
        st.markdown("### 📊 Full Player Rankings")

        if engine and tournament:
            scores = engine.get_tournament_recommendations(tournament, top_n=200, min_uses=0)

            # Filters
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            with filter_col1:
                min_score = st.slider("Min Score", 0, 100, 40, key="se_min_score")
            with filter_col2:
                max_rank = st.slider("Max OWGR", 1, 200, 150, key="se_max_rank")
            with filter_col3:
                sort_by = st.selectbox("Sort By", ["Total Score", "Course Fit", "Form", "OWGR"], key="se_sort")

            # Filter and sort
            filtered = [s for s in scores if s.total_score >= min_score and s.owgr_rank <= max_rank]

            sort_map = {"Total Score": "total_score", "Course Fit": "course_fit", "Form": "current_form", "OWGR": "owgr_rank"}
            reverse = sort_by != "OWGR"
            filtered = sorted(filtered, key=lambda x: getattr(x, sort_map[sort_by]), reverse=reverse)

            # Build dataframe for display
            data = []
            for s in filtered[:50]:
                uses = engine.usage.get(s.player, 3)
                data.append({
                    "Player": s.player,
                    "Total": round(s.total_score, 1),
                    "Course": round(s.course_fit, 1),
                    "Form": round(s.current_form, 1),
                    "Field": round(s.field_strength, 1),
                    "OWGR": s.owgr_rank,
                    "Trend": s.form_trend,
                    "Uses": f"{uses}/3",
                    "Rating": s.value_rating,
                })

            if data:
                df = pd.DataFrame(data)
                st.dataframe(df, hide_index=True, use_container_width=True,
                            column_config={
                                "Total": st.column_config.ProgressColumn("Total", min_value=0, max_value=100, format="%.0f"),
                                "Course": st.column_config.ProgressColumn("Course", min_value=0, max_value=100, format="%.0f"),
                                "Form": st.column_config.ProgressColumn("Form", min_value=0, max_value=100, format="%.0f"),
                            })
                st.caption(f"Showing {len(data)} players")

    with se_tab4:
        st.markdown("### 📰 Reports & Rankings")
        st.caption("Weekly reports, data refresh, and power-ranking intelligence in one place.")

        action_col1, action_col2 = st.columns(2)
        with action_col1:
            run_report = st.button("📰 Generate Weekly Report", use_container_width=True, type="primary", key="se_report")
        with action_col2:
            refresh_all = st.button("🔄 Refresh All Data", use_container_width=True, key="se_refresh")

        if run_report:
            with st.spinner("Generating weekly report..."):
                output = run_script("planning/weekly_report.py")
            with st.expander("Weekly report output", expanded=False):
                st.code(output, language=None)

        if refresh_all:
            with st.spinner("Refreshing data..."):
                output = run_script("run_pipeline.py", "--auto-weekly", "--skip-refresh")
            with st.expander("Refresh output", expanded=False):
                st.code(output, language=None)
            st.cache_data.clear()

        # Power Rankings section
        st.markdown("---")
        st.markdown("### 📈 Power Rankings")
        st.caption("Editorial ranking feed with quick scanning, filtering, and full-table drill-down.")

        pr_dir = DATA_DIR / "power_rankings"
        if pr_dir.exists():
            pr_files = sorted(pr_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
            pr_files = [f for f in pr_files if f.name not in ("paths.csv",) and not f.name.startswith(".")]

            if pr_files:
                file_options = {
                    f"{f.stem.replace('_', ' ').title()} ({datetime.fromtimestamp(f.stat().st_mtime).strftime('%b %d %H:%M')})": f
                    for f in pr_files
                }
                selected_label = st.selectbox(
                    "Ranking file",
                    list(file_options.keys()),
                    index=0,
                    key="se_pr_file",
                )
                selected_file = file_options[selected_label]
                df = pd.read_csv(selected_file)

                player_col = "player_name" if "player_name" in df.columns else "player" if "player" in df.columns else None
                if player_col is None:
                    st.warning("No player column found in selected ranking file.")
                else:
                    df[player_col] = df[player_col].fillna("").astype(str).str.strip()
                    df = df[df[player_col] != ""].copy()

                    if "rank" in df.columns:
                        df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
                        df = df.sort_values("rank", na_position="last")
                    else:
                        df = df.reset_index(drop=True)
                        df["rank"] = df.index + 1

                    tournament_name = (
                        str(df["tournament_name"].iloc[0]).strip()
                        if "tournament_name" in df.columns and not df.empty
                        else selected_file.stem.replace("_", " ").title()
                    )

                    last_updated = (
                        pd.to_datetime(df["scraped_at"], errors="coerce").max()
                        if "scraped_at" in df.columns
                        else pd.NaT
                    )
                    last_updated_str = (
                        last_updated.strftime("%Y-%m-%d %H:%M")
                        if pd.notna(last_updated)
                        else datetime.fromtimestamp(selected_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    )

                    st.success(f"{tournament_name} power rankings loaded")

                    top_player = df.iloc[0][player_col] if not df.empty else "—"
                    source_name = (
                        str(df["source"].iloc[0]).upper()
                        if "source" in df.columns and not df.empty and pd.notna(df["source"].iloc[0])
                        else "—"
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Players Ranked", len(df))
                    with m2:
                        st.metric("Top Ranked", str(top_player))
                    with m3:
                        st.metric("Source", source_name)
                    with m4:
                        st.metric("Updated", last_updated_str)

                    # Spotlight top 3
                    st.markdown("#### Top 3 Spotlight")
                    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                    top3 = df.head(3).copy()
                    spot_cols = st.columns(3)
                    for i in range(3):
                        with spot_cols[i]:
                            if i < len(top3):
                                row = top3.iloc[i]
                                rank = int(row.get("rank", i + 1)) if pd.notna(row.get("rank")) else i + 1
                                name = row.get(player_col, "Unknown")
                                country = str(row.get("country_flag", row.get("country", ""))).strip()
                                analysis = str(row.get("analysis", "") or "").strip()
                                st.markdown(f"### {medals.get(rank, f'#{rank}')}")
                                st.markdown(f"**{name}**")
                                if country:
                                    st.caption(country)
                                if analysis:
                                    st.caption(analysis[:140] + ("..." if len(analysis) > 140 else ""))
                            else:
                                st.markdown(" ")

                    st.markdown("#### Ranked Board")
                    board_col1, board_col2 = st.columns([2, 1])
                    with board_col1:
                        search_q = st.text_input("Search player", value="", key="se_pr_search")
                    with board_col2:
                        board_size = st.slider("Show rows", min_value=10, max_value=40, value=15, step=5, key="se_pr_rows")

                    board_df = df.copy()
                    if search_q.strip():
                        board_df = board_df[
                            board_df[player_col].str.contains(search_q.strip(), case=False, na=False)
                        ].copy()
                    board_df = board_df.head(board_size)

                    for _, row in board_df.iterrows():
                        rank_val = row.get("rank")
                        rank_num = int(rank_val) if pd.notna(rank_val) else None
                        rank_label = medals.get(rank_num, f"#{rank_num}" if rank_num else "•")
                        player = row.get(player_col, "Unknown")
                        country = str(row.get("country_flag", row.get("country", ""))).strip()
                        analysis = str(row.get("analysis", "") or "").strip()

                        r1, r2 = st.columns([1, 8])
                        with r1:
                            st.markdown(f"**{rank_label}**")
                        with r2:
                            st.markdown(f"**{player}**")
                            meta_parts = []
                            if country:
                                meta_parts.append(country)
                            if "player_id" in row and pd.notna(row.get("player_id")):
                                meta_parts.append(f"ID {int(row['player_id'])}")
                            if meta_parts:
                                st.caption(" • ".join(meta_parts))
                            if analysis:
                                st.caption(analysis[:180] + ("..." if len(analysis) > 180 else ""))

                    with st.expander("📊 Full Rankings Table"):
                        drop_cols = {"analysis"}
                        table_cols = [c for c in ["rank", player_col, "country_flag", "country", "player_id", "source", "scraped_at"] if c in df.columns]
                        table_cols += [c for c in df.columns if c not in set(table_cols) | drop_cols][:4]
                        st.dataframe(df[table_cols], hide_index=True, use_container_width=True, height=520)
            else:
                st.info("No power rankings available yet.")
        else:
            st.info("Power rankings directory not found.")


# ============================================================================
# PAGE: MY PICKS (consolidated with Performance)
# ============================================================================

elif page == "📋 My Picks":
    st.markdown("## 📋 My Picks")
    st.caption("Track usage and manage your lineup")

    engine = load_scoring_engine()
    all_players = sorted(engine.predictions.keys()) if engine and engine.predictions else []

    # Current tournament banner
    if engine:
        tournament = engine.get_current_week_tournament()
        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            st.success(f"📍 **This Week:** {tournament} — Week {t.week} • {t.tournament_type}")

    st.markdown("---")

    # Usage Tracker buttons
    st.markdown("### 📊 Usage Status")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        run_summary = st.button("📋 Summary", use_container_width=True, type="primary", help="--summary")
    with col2:
        run_lineups = st.button("📅 Lineups", use_container_width=True, help="--lineups")
    with col3:
        run_available = st.button("✅ Available", use_container_width=True, help="--available")

    if run_summary:
        with st.spinner("Running: usage_tracker.py --summary"):
            output = run_script("planning/usage_tracker.py", "--summary")
        st.code(output, language=None)

    if run_lineups:
        with st.spinner("Running: usage_tracker.py --lineups"):
            output = run_script("planning/usage_tracker.py", "--lineups")
        st.code(output, language=None)

    if run_available:
        with st.spinner("Running: usage_tracker.py --available"):
            output = run_script("planning/usage_tracker.py", "--available")
        st.code(output, language=None)

    st.markdown("---")

    # Manage Picks
    st.markdown("### ✏️ Manage Picks")

    manage_tab1, manage_tab2, manage_tab3 = st.tabs(["➕ Add Picks", "📝 Record Result", "🗑️ Remove Pick"])

    # Get tournaments
    current_tourney = ""
    upcoming_tourneys = []
    past_tourneys = []
    if engine:
        current_tourney = engine.get_current_week_tournament() or ""
        today = datetime.now().strftime("%Y-%m-%d")

        # Helper to get end date (start + 3 days for standard tournaments)
        def get_end_date(t):
            try:
                end_day = int(t.start_date[8:10]) + 3
                return t.start_date[:8] + str(end_day).zfill(2)
            except:
                return t.start_date

        # Include current + upcoming tournaments (end_date >= today means still playable)
        upcoming_tourneys = [name for name, t in engine.tournaments.items() if get_end_date(t) >= today]
        upcoming_tourneys.sort(key=lambda x: engine.tournaments[x].start_date)
        # Past tournaments are those that have ended
        past_tourneys = [name for name, t in engine.tournaments.items() if get_end_date(t) < today]
        past_tourneys.sort(key=lambda x: engine.tournaments[x].start_date, reverse=True)

    with manage_tab1:
        st.markdown("**Add players to your lineup**")

        tourney_for_pick = st.selectbox(
            "Tournament:",
            upcoming_tourneys,
            index=upcoming_tourneys.index(current_tourney) if current_tourney in upcoming_tourneys else 0,
            key="add_pick_tourney"
        )

        st.caption("Select up to 3 players:")
        col1, col2, col3 = st.columns(3)
        with col1:
            pick1 = st.selectbox("Player 1:", [""] + all_players, key="pick1")
        with col2:
            pick2 = st.selectbox("Player 2:", [""] + all_players, key="pick2")
        with col3:
            pick3 = st.selectbox("Player 3:", [""] + all_players, key="pick3")

        add_picks_btn = st.button("✅ Add Picks", type="primary", key="add_picks_btn")

        if add_picks_btn:
            selected = [p for p in [pick1, pick2, pick3] if p]
            if not selected:
                st.warning("Please select at least one player")
            elif not tourney_for_pick:
                st.warning("Please select a tournament")
            else:
                args = ["planning/usage_tracker.py", "--add"] + selected + ["--tournament", tourney_for_pick]
                with st.spinner(f"Adding {len(selected)} pick(s) to {tourney_for_pick}..."):
                    output = run_script(*args)
                st.code(output, language=None)
                if "Added" in output or "✓" in output:
                    st.success("Picks added! Reloading...")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning("Check output above for any issues.")

    with manage_tab2:
        st.markdown("**Record tournament result**")

        # Get players from tracker (picks) who need results recorded
        tracked_players = list(picks.keys()) if picks else []

        # Get tournaments where we have picks (only if lineup has players)
        lineups = usage_data.get("weekly_lineups", {})
        tourneys_with_picks = []
        for week_key, lineup in lineups.items():
            tourney_name = lineup.get("tournament", "")
            lineup_players = lineup.get("lineup", [])
            if tourney_name and lineup_players and tourney_name not in tourneys_with_picks:
                tourneys_with_picks.append(tourney_name)

        if not tracked_players:
            st.info("No players in tracker yet. Add picks first using the 'Add Picks' tab.")
        else:
            result_tourney = st.selectbox(
                "Tournament:",
                tourneys_with_picks if tourneys_with_picks else past_tourneys[:10],
                key="result_tourney"
            )

            # Filter to players who were picked for this tournament
            players_in_tourney = []
            for week_key, lineup in lineups.items():
                if lineup.get("tournament") == result_tourney:
                    players_in_tourney.extend(lineup.get("lineup", []))

            player_options = players_in_tourney if players_in_tourney else tracked_players
            result_player = st.selectbox("Player:", [""] + player_options, key="result_player")

            col1, col2 = st.columns(2)
            with col1:
                finish_pos = st.text_input("Finish position:", placeholder="e.g., 1st, T3, T15, MC", key="finish_pos")
            with col2:
                points_earned = st.number_input("Points earned:", min_value=0, max_value=500, value=0, key="points_earned")

            record_result_btn = st.button("📝 Record Result", type="primary", key="record_result_btn")

            if record_result_btn:
                if not result_player:
                    st.warning("Please select a player")
                elif not finish_pos:
                    st.warning("Please enter finish position")
                else:
                    with st.spinner(f"Recording result for {result_player}..."):
                        output = run_script(
                            "planning/usage_tracker.py",
                            "--result", result_player,
                            "--tournament", result_tourney,
                            "--finish", finish_pos,
                            "--points", str(points_earned)
                        )
                    st.code(output, language=None)
                    if "recorded" in output.lower() or "updated" in output.lower():
                        st.success(f"Result recorded for {result_player}!")
                        st.cache_data.clear()

    with manage_tab3:
        st.markdown("**Remove a pick (undo mistake)**")

        remove_tourney = st.selectbox(
            "Tournament:",
            upcoming_tourneys[:10] if upcoming_tourneys else ["No tournaments"],
            key="remove_tourney"
        )

        remove_player = st.selectbox("Player to remove:", [""] + all_players, key="remove_player")

        remove_btn = st.button("🗑️ Remove Pick", type="secondary", key="remove_btn")

        if remove_btn:
            if not remove_player:
                st.warning("Please select a player")
            else:
                with st.spinner(f"Removing {remove_player} from {remove_tourney}..."):
                    output = run_script(
                        "planning/usage_tracker.py",
                        "--remove", remove_player,
                        "--tournament", remove_tourney
                    )
                st.code(output, language=None)

    st.markdown("---")

    # Auto-Record Results
    st.markdown("### 🤖 Auto-Record Results")
    st.caption("Automatically fetch results from leaderboard data using FedEx points")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("👁️ Preview Results (Dry Run)", use_container_width=True):
            with st.spinner("Checking leaderboard for results..."):
                output = run_script("planning/auto_record_results.py", "--dry-run")
            st.code(output, language=None)
    with col2:
        if st.button("✅ Record All Results", use_container_width=True, type="primary"):
            with st.spinner("Recording results..."):
                output = run_script("planning/auto_record_results.py")
            st.code(output, language=None)
            st.cache_data.clear()


# ============================================================================
# PAGE: PLAYERS (consolidated from Player Stats + Stats Deep Dive)
# ============================================================================

elif page == "👤 Players":
    st.markdown("## 👤 Players")
    st.caption("Player lookup, strokes gained analysis, and statistical deep dive")

    engine = load_scoring_engine()
    all_players = sorted(engine.predictions.keys()) if engine and engine.predictions else []

    # Tabs for different views
    player_tab1, player_tab2, player_tab3 = st.tabs(["🔍 Player Lookup", "📊 Stats Deep Dive", "⚔️ Head-to-Head"])

    with player_tab1:
        st.markdown("### 🔍 Player Lookup")
        st.caption("Best events and usage optimization")

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            player_search = st.selectbox("Select a player:", [""] + all_players, key="quick_player")
        with col2:
            run_player = st.button("🔍 Best Events", use_container_width=True, type="primary", help="--player")
        with col3:
            run_optimize = st.button("⚡ Optimize Uses", use_container_width=True, help="--optimize")

        if run_player and player_search:
            with st.spinner(f"Running: scoring_engine.py --player '{player_search}'"):
                output = run_script("planning/scoring_engine.py", "--player", player_search)
            st.code(output, language=None)

        if run_optimize and player_search:
            with st.spinner(f"Running: scoring_engine.py --optimize '{player_search}'"):
                output = run_script("planning/scoring_engine.py", "--optimize", player_search)
            st.code(output, language=None)

        # Show comprehensive player stats when selected
        if player_search:
            st.markdown("---")
            st.markdown(f"### 📊 {player_search}")

            # Load player data from predictions
            preds_path = OUTPUTS_DIR / "latest_predictions.csv"
            player_data = {}
            if preds_path.exists():
                preds_df = pd.read_csv(preds_path)
                player_row = preds_df[preds_df["player_name"].apply(_name_key) == _name_key(player_search)]
                if not player_row.empty:
                    player_data = player_row.iloc[0].to_dict()

            if player_data:
                # Key metrics row
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    win_prob = player_data.get("win_prob", 0) or 0
                    st.metric("Win %", f"{win_prob*100:.2f}%")
                with col2:
                    top5 = player_data.get("top5_prob", 0) or 0
                    st.metric("Top 5 %", f"{top5*100:.1f}%")
                with col3:
                    top10 = player_data.get("top10_prob", 0) or 0
                    st.metric("Top 10 %", f"{top10*100:.1f}%")
                with col4:
                    ev = player_data.get("expected_value", 0) or 0
                    st.metric("Exp. Value", f"${ev:,.0f}")
                with col5:
                    sg = player_data.get("sg_total", 0) or 0
                    st.metric("SG Total", f"{sg:.2f}")

                # Second row - more stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    owgr = player_data.get("owgr_rank", player_data.get("world_rank", "—"))
                    st.metric("OWGR", owgr if pd.notna(owgr) else "—")
                with col2:
                    hist_plays = player_data.get("hist_times_played", 0)
                    st.metric("Course Plays", int(hist_plays) if pd.notna(hist_plays) else 0)
                with col3:
                    hist_avg = player_data.get("hist_avg_finish", None)
                    st.metric("Avg Finish (Course)", f"{hist_avg:.1f}" if pd.notna(hist_avg) else "—")
                with col4:
                    form_score = player_data.get("recent_form", player_data.get("form_score", None))
                    st.metric("Form Score", f"{form_score:.1f}" if pd.notna(form_score) else "—")

                # Strokes Gained breakdown
                st.markdown("#### ⛳ Strokes Gained Breakdown")
                sg_cols = st.columns(5)
                sg_metrics = [
                    ("OTT", "sg_ott", "Off The Tee"),
                    ("APP", "sg_app", "Approach"),
                    ("ATG", "sg_arg", "Around Green"),
                    ("PUTT", "sg_putt", "Putting"),
                    ("T2G", "sg_t2g", "Tee to Green"),
                ]
                for i, (label, col, tooltip) in enumerate(sg_metrics):
                    with sg_cols[i]:
                        val = player_data.get(col, 0)
                        if pd.notna(val):
                            color = "normal" if abs(val) < 0.5 else ("inverse" if val < 0 else "off")
                            st.metric(label, f"{val:.2f}", help=tooltip)
                        else:
                            st.metric(label, "—", help=tooltip)

            # Betting profile if available
            profiles_df = load_betting_profiles()
            if not profiles_df.empty:
                profile = get_player_profile(profiles_df, player_search)
                if profile:
                    st.markdown("#### 🎰 Betting Profile")
                    render_player_profile_card(profile, show_full=True)

            # Action buttons
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔍 Best Events", use_container_width=True, type="primary", key="player_best"):
                    with st.spinner(f"Getting best events for {player_search}..."):
                        output = run_script("planning/scoring_engine.py", "--player", player_search)
                    st.code(output, language=None)
            with col2:
                if st.button("📊 Full Stats Report", use_container_width=True, key="player_full_stats"):
                    with st.spinner(f"Getting full stats for {player_search}..."):
                        output = run_script("planning/player_stats.py", player_search, "--recent", "10")
                    st.code(output, language=None)

    with player_tab2:
        st.markdown("### 📊 Stats Deep Dive")
        st.caption("Detailed statistical analysis for smarter picks")

        # Load player stats from predictions
        stats_df = load_player_stats()

        if stats_df.empty:
            st.warning("No stats data available. Run predictions first to generate player stats.")
        else:
            st.success(f"Loaded stats for {len(stats_df)} players")

            # Sub-tabs for each analysis type
            deep_tab1, deep_tab2, deep_tab3 = st.tabs(["⛳ Strokes Gained", "🔥 Form Analysis", "🏌️ Course Fit"])

            with deep_tab1:
                render_strokes_gained_analysis(stats_df)

            with deep_tab2:
                render_form_stats_section(stats_df)

            with deep_tab3:
                render_course_specific_stats(stats_df)

    with player_tab3:
        st.markdown("### ⚔️ Head-to-Head Comparison")
        st.caption("Compare two players side-by-side")

        col1, col2 = st.columns(2)
        with col1:
            h2h_player1 = st.selectbox("Player 1:", [""] + all_players, key="h2h_player1")
        with col2:
            h2h_player2 = st.selectbox("Player 2:", [""] + all_players, key="h2h_player2")

        run_h2h = st.button("⚔️ Compare Players", use_container_width=True, type="primary")

        if run_h2h:
            if not h2h_player1 or not h2h_player2:
                st.warning("Please select two players to compare")
            elif h2h_player1 == h2h_player2:
                st.warning("Please select two different players")
            else:
                with st.spinner(f"Comparing {h2h_player1} vs {h2h_player2}..."):
                    output = run_script("planning/head_to_head.py", h2h_player1, h2h_player2)
                st.code(output, language=None)


# ============================================================================
# PAGE: BETTING (consolidated from Props Lab + Odds & Experts)
# ============================================================================

elif page == "🎰 Betting":
    st.markdown("## 🎰 Betting")
    st.caption("Sportsbook-style props powered by model predictions")

    # =========================================================================
    # MARKET AVAILABILITY SUMMARY STRIP
    # =========================================================================
    if market_availability_available:
        # Resolve active tournament ID from freshest available sources.
        avail_tournament_id = _latest_tournament_id_from_prop_lines(max_age_hours=48.0)
        if not avail_tournament_id:
            avail_tournament_id = _latest_tournament_id_from_live(max_age_hours=18.0)

        try:
            preds_probe = OUTPUTS_DIR / "latest_predictions.csv"
            if preds_probe.exists():
                temp_df = pd.read_csv(preds_probe, nrows=1)
                probe_tid = _tournament_id_from_df(temp_df)
                if probe_tid:
                    avail_tournament_id = probe_tid
        except Exception:
            pass

        if avail_tournament_id:
            try:
                availability = load_availability(avail_tournament_id)
                summary = availability.get_summary()

                # Display availability strip
                with st.container():
                    avail_cols = st.columns([1.5, 1, 1, 1, 1.5])

                    with avail_cols[0]:
                        books = summary.get("books_connected", [])
                        book_str = ", ".join(books) if books else "None"
                        st.metric("📡 Books Connected", book_str)

                    with avail_cols[1]:
                        st.metric("🎯 Live Markets", f"{summary['available_markets']}")

                    with avail_cols[2]:
                        fresh = summary.get("fresh_markets", 0)
                        if fresh > 0:
                            st.metric("🟢 Fresh", fresh)
                        else:
                            st.metric("🟡 Recent", summary.get("available_markets", 0) - summary.get("stale_markets", 0))

                    with avail_cols[3]:
                        stale = summary.get("stale_markets", 0)
                        if stale > 0:
                            st.metric("🟠 Stale", stale, delta="needs refresh", delta_color="inverse")
                        else:
                            st.metric("✓ Data Fresh", "OK")

                    with avail_cols[4]:
                        # Recent alerts
                        alerts = summary.get("recent_alerts", [])
                        if alerts:
                            last_alert = alerts[-1]
                            alert_type = last_alert.get("type", "").replace("_", " ").title()
                            st.caption(f"⚡ Last alert: {alert_type}")
                        else:
                            st.caption("No recent market changes")

                    # Market detail expander
                    with st.expander("📊 Market Availability Details", expanded=False):
                        market_data = []
                        for market_key, sources in availability.markets.items():
                            for source_key, status in sources.items():
                                badge = get_staleness_badge(status.staleness)
                                market_data.append({
                                    "Market": market_key.upper(),
                                    "Source": f"{'🎰' if source_key != 'MODEL' else '📊'} {source_key}",
                                    "Status": "✓ Available" if status.available else "✗ Unavailable",
                                    "Lines": status.player_count if status.available else 0,
                                    "Freshness": f"{badge['icon']} {badge['label']}",
                                })

                        if market_data:
                            avail_df = pd.DataFrame(market_data)
                            st.dataframe(avail_df, use_container_width=True, hide_index=True)

                            # Refresh button
                            if st.button("🔄 Refresh Market Scan"):
                                scan_all_availability(avail_tournament_id)
                                st.rerun()
            except Exception as e:
                st.caption(f"Market availability: {e}")
        else:
            st.caption("Market availability: no active tournament ID detected yet.")

        st.markdown("---")

    # Import props model
    try:
        from scripts.models.props_model import (
            generate_matchup, calculate_matchup_probability,
            generate_position_props, generate_round_score_prop,
            calculate_parlay, generate_suggested_parlays,
            prob_to_american, format_american_odds, calculate_edge,
            ParlayLeg
        )
        props_available = True
    except ImportError as e:
        st.error(f"Props model not available: {e}")
        props_available = False

    if props_available:
        # Load predictions data
        preds_df = pd.DataFrame()
        preds_path = OUTPUTS_DIR / "latest_predictions.csv"
        if preds_path.exists():
            preds_df = pd.read_csv(preds_path)

        if preds_df.empty:
            # Try to find any predictions file
            pred_files = get_prediction_files()
            if pred_files:
                preds_df = pd.read_csv(pred_files[0])

        if preds_df.empty:
            st.warning("No predictions available. Run predictions first to generate props.")
        else:
            # Merge in FanDuel winner market data for pricing/edge context.
            fanduel_df, fanduel_file, fanduel_source = load_latest_fanduel_odds_df()
            preds_df = preds_df.copy()
            preds_df["name_key"] = preds_df["player_name"].apply(_name_key)

            if not _is_recent_file(fanduel_file, max_age_hours=18.0):
                fanduel_df = pd.DataFrame()

            if not fanduel_df.empty and "player_name" in fanduel_df.columns:
                fd = fanduel_df.copy()
                fd["name_key"] = fd["player_name"].apply(_name_key)
                fd = fd.sort_values("odds_numeric", ascending=True, na_position="last")

                # Prefer robust ID-based join first when available.
                data_cols = [
                    "odds_to_win", "implied_prob", "model_win_prob",
                    "edge_win_prob", "edge_pct_points", "is_value_bet",
                    "odds_direction", "odds_swing", "fetched_at"
                ]
                if "player_id" in preds_df.columns and "player_id" in fd.columns:
                    preds_df["player_id"] = pd.to_numeric(preds_df["player_id"], errors="coerce").astype("Int64")
                    fd["player_id"] = pd.to_numeric(fd["player_id"], errors="coerce").astype("Int64")
                    id_cols = ["player_id"] + [c for c in data_cols if c in fd.columns]
                    fd_id = fd[id_cols].drop_duplicates("player_id")
                    preds_df = preds_df.merge(fd_id, on="player_id", how="left")

                # Name-based fallback for rows still missing odds.
                name_cols = ["name_key"] + [c for c in data_cols if c in fd.columns]
                fd_name = fd[name_cols].drop_duplicates("name_key")
                preds_df = preds_df.merge(
                    fd_name,
                    on="name_key",
                    how="left",
                    suffixes=("", "_name"),
                )
                for c in [c for c in data_cols if c in fd.columns]:
                    if f"{c}_name" in preds_df.columns:
                        if c not in preds_df.columns:
                            preds_df[c] = preds_df[f"{c}_name"]
                        else:
                            preds_df[c] = preds_df[c].fillna(preds_df[f"{c}_name"])
                        preds_df = preds_df.drop(columns=[f"{c}_name"], errors="ignore")

                # Ensure edge columns are always coherent.
                if "model_win_prob" not in preds_df.columns:
                    preds_df["model_win_prob"] = preds_df.get("win_prob")
                else:
                    preds_df["model_win_prob"] = preds_df["model_win_prob"].fillna(preds_df.get("win_prob"))

                preds_df["edge_win_prob"] = np.where(
                    preds_df.get("model_win_prob").notna() & preds_df.get("implied_prob").notna(),
                    preds_df.get("model_win_prob") - preds_df.get("implied_prob"),
                    preds_df.get("edge_win_prob")
                )
                preds_df["edge_pct_points"] = preds_df["edge_win_prob"] * 100
                preds_df["is_value_bet"] = preds_df["edge_win_prob"] > 0

            st.success(f"Loaded {len(preds_df)} players from model predictions")

            winner_book_label = "FANDUEL" if fanduel_source == "fanduel_odds" else "PGA_ODDS_CACHE"
            winner_edges_df = pd.DataFrame()
            if (
                "player_name" in preds_df.columns
                and "odds_to_win" in preds_df.columns
            ):
                winner_work = preds_df.copy()
                winner_work["book_odds"] = winner_work["odds_to_win"].apply(_parse_american_odds)
                winner_work["book_prob"] = pd.to_numeric(winner_work.get("implied_prob"), errors="coerce")
                winner_work["model_prob"] = pd.to_numeric(
                    winner_work.get("model_win_prob", winner_work.get("win_prob")),
                    errors="coerce",
                )
                if "edge_pct_points" in winner_work.columns:
                    winner_work["edge_pts"] = pd.to_numeric(winner_work["edge_pct_points"], errors="coerce")
                else:
                    winner_work["edge_pts"] = (winner_work["model_prob"] - winner_work["book_prob"]) * 100

                winner_work = winner_work[
                    winner_work["player_name"].notna()
                    & winner_work["book_odds"].notna()
                    & winner_work["book_prob"].notna()
                    & winner_work["model_prob"].notna()
                ].copy()

                if not winner_work.empty:
                    winner_edges_df = pd.DataFrame({
                        "market": "winner",
                        "selection": winner_work["player_name"].astype(str),
                        "book_odds": winner_work["book_odds"],
                        "book_prob": winner_work["book_prob"],
                        "model_prob": winner_work["model_prob"],
                        "edge_pts": winner_work["edge_pts"],
                        "book": winner_book_label,
                        "line_source": "winner_market",
                    })
                    if "fetched_at" in winner_work.columns:
                        winner_edges_df["fetched_at"] = winner_work["fetched_at"]

            # Market coverage summary for props workflow.
            if "odds_to_win" in preds_df.columns and preds_df["odds_to_win"].notna().any():
                coverage = int(preds_df["odds_to_win"].notna().sum())
                edge_series = (
                    pd.to_numeric(preds_df["edge_win_prob"], errors="coerce")
                    if "edge_win_prob" in preds_df.columns
                    else pd.Series(dtype=float)
                )
                edges = int((edge_series > 0).sum())
                avg_edge = (
                    pd.to_numeric(preds_df["edge_pct_points"], errors="coerce").mean()
                    if "edge_pct_points" in preds_df.columns
                    else np.nan
                )

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Winner Coverage", f"{coverage}/{len(preds_df)}")
                with c2:
                    st.metric("Positive Edges", edges)
                with c3:
                    st.metric("Avg Edge", f"{avg_edge:+.2f} pts" if pd.notna(avg_edge) else "—")
            else:
                st.info("FanDuel winner market not linked; continuing with model-only prop pricing.")

            prop_lines_df = pd.DataFrame()
            book_edges_df = pd.DataFrame()
            prop_lines_source = "none"
            prop_tournament_id = _tournament_id_from_df(preds_df)

            if not prop_tournament_id:
                prop_tournament_id = _latest_tournament_id_from_prop_lines(max_age_hours=48.0)

            if (
                not prop_tournament_id
                and not fanduel_df.empty
                and _is_recent_file(fanduel_file, max_age_hours=18.0)
            ):
                prop_tournament_id = _tournament_id_from_df(fanduel_df)

            if prop_edge_tools_available and load_latest_prop_lines and score_book_props:
                prop_lines_df = load_latest_prop_lines(prop_tournament_id if prop_tournament_id else None)
                if not prop_lines_df.empty:
                    prop_lines_source = "file"
                else:
                    # Build a model-based baseline so the Book Edges tab stays usable
                    # before sportsbook prop ingestion is set up.
                    prop_lines_source = "model_baseline"
                    rank_col = "expected_value" if "expected_value" in preds_df.columns else "win_prob"
                    seed_df = preds_df.sort_values(rank_col, ascending=False).head(20).copy()
                    baseline_rows = []

                    # H2H baseline lines from model matchups
                    pair_count = min(6, len(seed_df) // 2)
                    for i in range(pair_count):
                        a = seed_df.iloc[i * 2].to_dict()
                        b = seed_df.iloc[i * 2 + 1].to_dict()
                        matchup = generate_matchup(a, b)
                        baseline_rows.append({
                            "market": "h2h",
                            "player_a": matchup.player_a,
                            "player_b": matchup.player_b,
                            "odds_a": matchup.odds_a,
                            "odds_b": matchup.odds_b,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                    # Round-score + birdies baseline lines from model stats
                    for _, prow in seed_df.head(12).iterrows():
                        p = prow.to_dict()
                        rs = generate_round_score_prop(
                            p,
                            round_num=1,
                            course_par=72,
                            course_scoring_avg=71.0,
                        )
                        baseline_rows.append({
                            "market": "round_score",
                            "player_name": p["player_name"],
                            "line": rs.line,
                            "over_odds": rs.over_odds,
                            "under_odds": rs.under_odds,
                            "round_num": 1,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                        sg_app = p.get("sg_app", 0) or 0
                        sg_putt = p.get("sg_putt", 0) or 0
                        form = p.get("form_trend", 0) or 0
                        over_prob = float(np.clip(0.5 + 0.12 * (sg_app + sg_putt) + 0.08 * form, 0.08, 0.92))
                        under_prob = 1 - over_prob
                        baseline_rows.append({
                            "market": "birdies",
                            "player_name": p["player_name"],
                            "line": 4.5,
                            "over_odds": prob_to_american(over_prob),
                            "under_odds": prob_to_american(under_prob),
                            "round_num": 1,
                            "book": "MODEL_BASELINE",
                            "line_source": "model_baseline",
                        })

                    if baseline_rows:
                        prop_lines_df = pd.DataFrame(baseline_rows)

                if not prop_lines_df.empty:
                    book_edges_df = score_book_props(
                        preds_df,
                        prop_lines_df,
                        course_par=72,
                        course_avg=71.0,
                    )

            # Add winner market edges to unified edge table.
            if not winner_edges_df.empty:
                if book_edges_df.empty:
                    book_edges_df = winner_edges_df.copy()
                else:
                    book_edges_df = pd.concat([winner_edges_df, book_edges_df], ignore_index=True)

            def _has_live_prop_market(market_name: str) -> bool:
                if prop_lines_df.empty or "market" not in prop_lines_df.columns:
                    return False
                mdf = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == market_name.lower()
                ].copy()
                if mdf.empty:
                    return False
                if "book" in mdf.columns:
                    return (mdf["book"].astype(str).str.upper() != "MODEL_BASELINE").any()
                return prop_lines_source == "file"

            has_live_h2h = _has_live_prop_market("h2h")
            has_live_round_score = _has_live_prop_market("round_score")
            has_live_birdies = _has_live_prop_market("birdies")
            current_live_markets = []
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                live_m = prop_lines_df.copy()
                if "book" in live_m.columns:
                    live_m = live_m[live_m["book"].astype(str).str.upper() != "MODEL_BASELINE"]
                current_live_markets = sorted(live_m["market"].dropna().astype(str).str.lower().unique().tolist())

            # Build robust player-name matching for sportsbook prop lines.
            model_players = preds_df["player_name"].dropna().astype(str).str.strip().tolist()
            model_player_set = set(model_players)
            exact_name_map = {}
            short_name_map = {}

            def _short_name_key(name: str) -> str:
                if pd.isna(name):
                    return ""
                cleaned = (
                    str(name)
                    .replace(",", " ")
                    .replace(".", " ")
                    .replace("-", " ")
                    .lower()
                    .strip()
                )
                toks = [t for t in cleaned.split() if t]
                toks = [t for t in toks if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
                if not toks:
                    return ""
                first = toks[0]
                last = toks[-1]
                if not first or not last:
                    return ""
                return f"{last} {first[0]}"

            for nm in model_players:
                k = _name_key(nm)
                if k and k not in exact_name_map:
                    exact_name_map[k] = nm
                sk = _short_name_key(nm)
                if sk:
                    short_name_map.setdefault(sk, []).append(nm)

            def _resolve_model_player(name: str) -> str:
                k = _name_key(name)
                if k in exact_name_map:
                    return exact_name_map[k]
                sk = _short_name_key(name)
                cands = short_name_map.get(sk, [])
                if len(cands) == 1:
                    return cands[0]
                return str(name).strip()

            round_lines_live_df = pd.DataFrame()
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                round_lines_live_df = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == "round_score"
                ].copy()
                if not round_lines_live_df.empty:
                    if "player_name" not in round_lines_live_df.columns:
                        round_lines_live_df["player_name"] = ""
                    round_lines_live_df["player_name"] = round_lines_live_df["player_name"].fillna("").astype(str).str.strip()
                    round_lines_live_df["round_num"] = pd.to_numeric(round_lines_live_df.get("round_num"), errors="coerce").fillna(1).astype(int)
                    round_lines_live_df["line"] = pd.to_numeric(round_lines_live_df.get("line"), errors="coerce")
                    round_lines_live_df["over_odds"] = pd.to_numeric(round_lines_live_df.get("over_odds"), errors="coerce")
                    round_lines_live_df["under_odds"] = pd.to_numeric(round_lines_live_df.get("under_odds"), errors="coerce")
                    round_lines_live_df["model_player"] = round_lines_live_df["player_name"].apply(_resolve_model_player)
                    round_lines_live_df["is_player_match"] = round_lines_live_df["model_player"].isin(model_player_set)

            h2h_lines_live_df = pd.DataFrame()
            if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                h2h_lines_live_df = prop_lines_df[
                    prop_lines_df["market"].astype(str).str.lower() == "h2h"
                ].copy()
                if not h2h_lines_live_df.empty:
                    for c in ["player_a", "player_b"]:
                        if c not in h2h_lines_live_df.columns:
                            h2h_lines_live_df[c] = ""
                        h2h_lines_live_df[c] = h2h_lines_live_df[c].fillna("").astype(str).str.strip()
                    h2h_lines_live_df["odds_a"] = pd.to_numeric(h2h_lines_live_df.get("odds_a"), errors="coerce")
                    h2h_lines_live_df["odds_b"] = pd.to_numeric(h2h_lines_live_df.get("odds_b"), errors="coerce")
                    h2h_lines_live_df["model_player_a"] = h2h_lines_live_df["player_a"].apply(_resolve_model_player)
                    h2h_lines_live_df["model_player_b"] = h2h_lines_live_df["player_b"].apply(_resolve_model_player)
                    h2h_lines_live_df["is_match_a"] = h2h_lines_live_df["model_player_a"].isin(model_player_set)
                    h2h_lines_live_df["is_match_b"] = h2h_lines_live_df["model_player_b"].isin(model_player_set)
                    h2h_lines_live_df["is_full_match"] = h2h_lines_live_df["is_match_a"] & h2h_lines_live_df["is_match_b"]

            # =========================================================================
            # LOAD LIVE TOURNAMENT DATA FOR FILTERING
            # =========================================================================
            live_leaderboard_df = pd.DataFrame()
            live_contenders = set()
            live_contenders_normalized = set()
            tournament_round = 1
            is_tournament_live = False
            is_tournament_over = False
            leader_score = 0
            tournament_winner = ""

            live_dir = DATA_DIR / "live"
            live_tid = (prop_tournament_id or "").strip()
            live_path = live_dir / f"leaderboard_{live_tid.lower()}.csv" if live_tid else None

            if live_path and live_path.exists():
                try:
                    live_leaderboard_df = pd.read_csv(live_path)
                    if not live_leaderboard_df.empty:
                        tournament_round = int(live_leaderboard_df["current_round"].max()) if "current_round" in live_leaderboard_df.columns else 1
                        leader_score = int(live_leaderboard_df["total_numeric"].min()) if "total_numeric" in live_leaderboard_df.columns else 0

                        # Check if live (not all finished)
                        if "thru" in live_leaderboard_df.columns:
                            thru_vals = live_leaderboard_df["thru"].astype(str).str.upper()
                            all_finished = all(t in ["F", "F*", "18", ""] for t in thru_vals)
                            is_tournament_live = not all_finished

                            # Tournament is over if R4 and all finished
                            is_tournament_over = (tournament_round == 4 and all_finished)

                            if is_tournament_over:
                                # Get winner
                                winner_row = live_leaderboard_df[live_leaderboard_df["total_numeric"] == leader_score]
                                if not winner_row.empty:
                                    tournament_winner = winner_row.iloc[0].get("player_name", "Unknown")

                        # Get contenders (within 5 shots in R4, 7 in R3, all in R1-2)
                        if tournament_round >= 3 and not is_tournament_over:
                            threshold = leader_score + (5 if tournament_round == 4 else 7)
                            contenders_df = live_leaderboard_df[live_leaderboard_df["total_numeric"] <= threshold]
                        else:
                            contenders_df = live_leaderboard_df[live_leaderboard_df["made_cut"] == True] if "made_cut" in live_leaderboard_df.columns else live_leaderboard_df

                        live_contenders = set(contenders_df["player_name"].dropna().astype(str).str.strip().tolist())

                        # Also add by normalized name for matching
                        live_contenders_normalized = {_name_key(n) for n in live_contenders}
                except Exception as e:
                    st.caption(f"Could not load live data: {e}")

            def is_contender(player_name: str) -> bool:
                """Check if player is still a contender in the tournament."""
                if not live_contenders:
                    return True  # No live data, assume all are contenders
                if player_name in live_contenders:
                    return True
                return _name_key(player_name) in live_contenders_normalized

            def get_live_position(player_name: str) -> str:
                """Get player's current position from live leaderboard."""
                if live_leaderboard_df.empty:
                    return ""
                key = _name_key(player_name)
                match = live_leaderboard_df[live_leaderboard_df["player_name"].apply(_name_key) == key]
                if not match.empty:
                    row = match.iloc[0]
                    pos = row.get("position", "")
                    total = row.get("total", "")
                    thru = row.get("thru", "")
                    return f"{pos} ({total}) thru {thru}"
                return ""

            # Show tournament status
            if is_tournament_over:
                st.warning(f"🏁 **Tournament Complete** | Winner: {tournament_winner} ({leader_score:+d})")
                st.info("This tournament has finished. Betting recommendations are no longer available. Check back when the next tournament begins.")

            elif tournament_round >= 3 and live_contenders:
                st.info(f"🔴 **Round {tournament_round}** | Leader: {leader_score:+d} | Showing {len(live_contenders)} contenders")

            # Main tabs (consolidated)
            props_tab1, props_tab2, props_tab3, props_tab4 = st.tabs([
                "🤖 AI Picks",
                "📈 DraftKings Odds",
                "⚔️ Matchups",
                "🎲 Parlay Builder",
            ])

            # =================================================================
            # TAB 0: AI PICKS (LLM RECOMMENDATIONS)
            # =================================================================
            with props_tab1:
                st.markdown("### 🤖 AI-Powered Betting Recommendations")
                st.caption("Model-computed edges with intelligent pick recommendations")

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. No active betting recommendations.")
                    st.info(f"**Winner:** {tournament_winner} finished at {leader_score:+d}")
                elif not betting_recs_available:
                    st.warning("Betting recommendations module not available.")
                else:
                    # Get tournament ID
                    rec_tournament_id = (prop_tournament_id or "").strip()

                    # Risk profile selector
                    profile_col1, profile_col2, profile_col3 = st.columns([2, 2, 2])

                    with profile_col1:
                        risk_profile = st.selectbox(
                            "Risk Profile",
                            options=["balanced", "conservative", "aggressive"],
                            format_func=lambda x: {
                                "conservative": "🛡️ Conservative - Lower variance, high confidence",
                                "balanced": "⚖️ Balanced - Mix of value and safety",
                                "aggressive": "🚀 Aggressive - Chase bigger edges",
                            }.get(x, x),
                            index=0,
                            key="ai_risk_profile",
                        )

                    with profile_col2:
                        max_picks = st.slider("Max Picks", 3, 10, 5, key="ai_max_picks")

                    with profile_col3:
                        include_parlays = st.checkbox("Include Parlays", value=True, key="ai_parlays")

                    # Get edge summary first
                    if rec_tournament_id:
                        edge_summary = get_edge_summary(rec_tournament_id)
                    else:
                        edge_summary = {
                            "total_legs": 0,
                            "positive_edge_legs": 0,
                            "best_edge": 0,
                            "avg_edge": 0,
                            "markets": {},
                            "tournament_state": {},
                        }
                        st.caption("No active tournament ID detected yet. Run current event odds fetch to enable live recommendation state.")
                    tournament_state = edge_summary.get("tournament_state", {})

                    # Tournament state display
                    if tournament_state:
                        round_num = tournament_state.get("round", 1)
                        is_live = tournament_state.get("is_live", False)
                        leader_score = tournament_state.get("leader_score", 0)

                        state_cols = st.columns([1, 1, 1, 2])
                        with state_cols[0]:
                            round_emoji = "🔴" if is_live else "📍"
                            st.metric(f"{round_emoji} Round", round_num)
                        with state_cols[1]:
                            leader_display = f"{leader_score:+d}" if leader_score != 0 else "E"
                            st.metric("Leader Score", leader_display)
                        with state_cols[2]:
                            threshold = tournament_state.get("contender_threshold", 0)
                            thresh_display = f"{threshold:+d}" if threshold != 0 else "E"
                            st.metric("Contender Cutoff", thresh_display)
                        with state_cols[3]:
                            if is_live:
                                st.info("🔴 **LIVE** - Using real-time position-based probabilities")
                            elif round_num >= 3:
                                st.warning("⏸️ Round complete - Probabilities based on current standings")
                            else:
                                st.caption("📊 Using pre-tournament model predictions")

                    # Summary metrics
                    sum_c1, sum_c2, sum_c3, sum_c4 = st.columns(4)
                    with sum_c1:
                        st.metric("Total Legs Scanned", edge_summary.get("total_legs", 0))
                    with sum_c2:
                        pos_edges = edge_summary.get("positive_edge_legs", 0)
                        st.metric("Positive Edge Legs", pos_edges)
                    with sum_c3:
                        best = edge_summary.get("best_edge", 0) * 100
                        st.metric("Best Edge", f"{best:.1f}%")
                    with sum_c4:
                        avg = edge_summary.get("avg_edge", 0) * 100
                        st.metric("Avg Edge", f"{avg:.1f}%")

                    st.markdown("---")

                    # Generate recommendations
                    if st.button("🎯 Generate Recommendations", type="primary", key="gen_recs"):
                        if not rec_tournament_id:
                            st.warning("No active tournament ID detected for recommendations yet.")
                        else:
                            with st.spinner("Analyzing edges and generating picks..."):
                                profile_enum = RiskProfile(risk_profile)
                                recs = generate_recommendations(
                                    rec_tournament_id,
                                    profile=profile_enum,
                                    max_slips=max_picks,
                                    include_parlays=include_parlays,
                                )

                                if not recs:
                                    st.warning("No recommendations generated. Check if predictions and sportsbook lines are available.")
                                else:
                                    st.success(f"Generated {len(recs)} recommendations")

                                    for i, slip in enumerate(recs, 1):
                                        display = format_slip_for_display(slip)

                                        # Determine card styling based on EV
                                        ev_val = slip.ev_per_unit
                                        if ev_val > 0.1:
                                            border_color = "#10b981"  # Green
                                        elif ev_val > 0:
                                            border_color = "#f59e0b"  # Yellow
                                        else:
                                            border_color = "#6b7280"  # Gray

                                        with st.container():
                                            st.markdown(f"""
                                            <div style="border-left: 4px solid {border_color}; padding-left: 1rem; margin: 1rem 0;">
                                            <h4>#{i} {display['type']} {'🎲' if slip.is_parlay else '🎯'}</h4>
                                            </div>
                                            """, unsafe_allow_html=True)

                                            # Legs
                                            for leg in display['legs']:
                                                leg_cols = st.columns([3, 1, 1, 1])
                                                with leg_cols[0]:
                                                    source_emoji = "🎰" if leg['book'] != "MODEL" else "📊"
                                                    st.markdown(f"**{leg['player']}** {leg['selection']}")
                                                with leg_cols[1]:
                                                    st.markdown(f"`{leg['odds']}`")
                                                with leg_cols[2]:
                                                    edge_val = float(leg['edge'].replace('%', ''))
                                                    edge_color = "green" if edge_val > 5 else "orange" if edge_val > 0 else "red"
                                                    st.markdown(f":{edge_color}[{leg['edge']} edge]")
                                                with leg_cols[3]:
                                                    st.caption(f"{source_emoji} {leg['book']}")

                                            # Combined stats
                                            stat_cols = st.columns(4)
                                            with stat_cols[0]:
                                                st.metric("Combined Odds", display['combined_odds'])
                                            with stat_cols[1]:
                                                st.metric("Win Prob", display['combined_prob'])
                                            with stat_cols[2]:
                                                st.metric("Edge", display['edge'])
                                            with stat_cols[3]:
                                                ev_display = display['ev']
                                                st.metric("EV", ev_display)

                                            # Reasoning
                                            st.info(f"💡 {display['reasoning']}")

                                            # Risk notes
                                            if display['risk_notes']:
                                                with st.expander("⚠️ Risk Notes"):
                                                    for note in display['risk_notes']:
                                                        st.caption(f"• {note}")

                                            st.markdown("---")

                    # Edge breakdown by market
                    with st.expander("📊 Edge Breakdown by Market", expanded=False):
                        markets = edge_summary.get("markets", {})
                        if markets:
                            for market, data in markets.items():
                                m_cols = st.columns([2, 1, 1, 1])
                                with m_cols[0]:
                                    st.markdown(f"**{market.upper()}**")
                                with m_cols[1]:
                                    st.caption(f"{data['count']} legs")
                                with m_cols[2]:
                                    st.caption(f"Best: {data['best_edge']*100:.1f}%")
                                with m_cols[3]:
                                    st.caption(f"Avg: {data['avg_edge']*100:.1f}%")
                        else:
                            st.caption("No edge data available")

            # =================================================================
            # TAB 2: DRAFTKINGS ODDS
            # =================================================================
            with props_tab2:
                st.markdown("### 📈 DraftKings Odds")
                st.caption("Live odds from DraftKings - Outright, Top 5, Top 10")

                # Load DraftKings odds from prop_lines
                dk_odds_df = pd.DataFrame()
                if not prop_lines_df.empty and "market" in prop_lines_df.columns:
                    dk_odds_df = prop_lines_df[
                        prop_lines_df["market"].isin(["outright", "top5", "top10"])
                    ].copy()

                if dk_odds_df.empty:
                    st.info("No DraftKings odds available. Run the scraper to fetch latest odds.")
                    st.code("python3 scripts/scrapers/fetch_draftkings_props.py --tournament-id R2026007")
                else:
                    # Market type selector
                    market_options = dk_odds_df["market"].unique().tolist()
                    market_labels = {"outright": "🏆 Outright Winner", "top5": "🔝 Top 5", "top10": "🎯 Top 10"}

                    selected_market = st.selectbox(
                        "Market Type",
                        options=market_options,
                        format_func=lambda x: market_labels.get(x, x),
                        key="dk_market_select"
                    )

                    # Filter by selected market
                    market_df = dk_odds_df[dk_odds_df["market"] == selected_market].copy()

                    # Sort by odds (favorites first)
                    market_df["odds_num"] = pd.to_numeric(market_df["odds"], errors="coerce")
                    market_df = market_df.sort_values("odds_num", ascending=True)

                    # Display count
                    st.caption(f"Showing {len(market_df)} players")

                    # Search filter
                    search = st.text_input("Search player", key="dk_search", placeholder="Type to filter...")
                    if search:
                        market_df = market_df[
                            market_df["player_name"].str.lower().str.contains(search.lower(), na=False)
                        ]

                    # Format odds for display
                    def format_american_odds(odds):
                        if pd.isna(odds):
                            return "-"
                        odds = int(odds)
                        if odds > 0:
                            return f"+{odds}"
                        return str(odds)

                    # Create display columns
                    display_df = market_df[["player_name", "odds", "implied_prob"]].copy()
                    display_df["odds"] = display_df["odds"].apply(format_american_odds)
                    display_df["implied_prob"] = (display_df["implied_prob"] * 100).round(2).astype(str) + "%"
                    display_df.columns = ["Player", "Odds", "Implied %"]

                    # Show as table
                    st.dataframe(
                        display_df,
                        hide_index=True,
                        use_container_width=True,
                        height=500
                    )

                    # Show favorites summary
                    st.markdown("---")
                    st.markdown("#### 🔥 Top Favorites")
                    top5_df = market_df.head(5)
                    cols = st.columns(5)
                    for i, (_, row) in enumerate(top5_df.iterrows()):
                        with cols[i]:
                            odds_str = format_american_odds(row["odds"])
                            prob_pct = row.get("implied_prob", 0) * 100 if pd.notna(row.get("implied_prob")) else 0
                            st.metric(
                                row["player_name"].split()[-1],  # Last name only
                                odds_str,
                                f"{prob_pct:.1f}%"
                            )

            # =================================================================
            # TAB 3: HEAD-TO-HEAD MATCHUPS
            # =================================================================
            with props_tab3:
                st.markdown("### ⚔️ Head-to-Head Matchups")
                st.caption("Who will finish higher? Model-powered matchup predictions.")

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. Matchups are no longer active.")

                rank_col = "expected_value" if "expected_value" in preds_df.columns else "win_prob"
                preds_ranked = preds_df.copy()
                preds_ranked["model_rank"] = preds_ranked[rank_col].rank(ascending=False, method="min").astype(int)
                player_list = (
                    preds_ranked.sort_values("model_rank")["player_name"]
                    .dropna()
                    .astype(str)
                    .drop_duplicates()
                    .tolist()
                )
                player_lookup = {str(r["player_name"]): r.to_dict() for _, r in preds_ranked.iterrows() if pd.notna(r.get("player_name"))}

                live_h2h_count = len(h2h_lines_live_df)
                live_h2h_matched = (
                    int(h2h_lines_live_df["is_full_match"].sum())
                    if not h2h_lines_live_df.empty and "is_full_match" in h2h_lines_live_df.columns
                    else 0
                )
                h1, h2, h3 = st.columns(3)
                with h1:
                    st.metric("Model Players", len(player_list))
                with h2:
                    st.metric("Live H2H Lines", live_h2h_count)
                with h3:
                    st.metric("Mapped H2H Lines", live_h2h_matched)

                source_options = ["Model Explorer"]
                if live_h2h_count > 0:
                    source_options.append("Live Sportsbook Lines")
                source_mode = st.radio(
                    "Matchup Source",
                    options=source_options,
                    horizontal=True,
                    key="h2h_source_mode",
                )

                player_a = None
                player_b = None
                live_h2h_row = None

                if source_mode == "Live Sportsbook Lines" and live_h2h_count > 0:
                    live_pool = h2h_lines_live_df.copy()
                    if "is_full_match" in live_pool.columns and live_pool["is_full_match"].any():
                        live_pool = live_pool[live_pool["is_full_match"]].copy()
                    live_pool = live_pool.reset_index(drop=True)

                    if not live_pool.empty:
                        def _fmt_live_h2h(i):
                            row = live_pool.loc[i]
                            pa = row.get("model_player_a", row.get("player_a", "A"))
                            pb = row.get("model_player_b", row.get("player_b", "B"))
                            oa = row.get("odds_a")
                            ob = row.get("odds_b")
                            oa_str = f"{int(oa):+d}" if pd.notna(oa) else "—"
                            ob_str = f"{int(ob):+d}" if pd.notna(ob) else "—"
                            return f"{pa} vs {pb} ({oa_str} / {ob_str})"

                        live_idx = st.selectbox(
                            "Live Matchup Line:",
                            options=live_pool.index.tolist(),
                            format_func=_fmt_live_h2h,
                            key="h2h_live_pick",
                        )
                        picked = live_pool.loc[live_idx]
                        live_h2h_row = picked.to_dict()
                        player_a = str(picked.get("model_player_a", picked.get("player_a", ""))).strip()
                        player_b = str(picked.get("model_player_b", picked.get("player_b", ""))).strip()
                    else:
                        st.info("No fully mappable live H2H lines found; switch to Model Explorer.")
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        player_a = st.selectbox("Player A:", player_list, index=0, key="h2h_a")
                    with col2:
                        default_b = 1 if len(player_list) > 1 else 0
                        player_b = st.selectbox("Player B:", player_list, index=default_b, key="h2h_b")

                if player_a and player_b and player_a != player_b:
                    # Get player data
                    if player_a not in player_lookup or player_b not in player_lookup:
                        st.warning("One or both selected players were not found in model predictions.")
                        player_a_data = None
                        player_b_data = None
                    else:
                        player_a_data = player_lookup[player_a]
                        player_b_data = player_lookup[player_b]

                    # Generate matchup
                    if player_a_data is None or player_b_data is None:
                        matchup = None
                    else:
                        matchup = generate_matchup(player_a_data, player_b_data)

                    if matchup is not None:
                        st.markdown("---")

                        # Display matchup result
                        st.markdown("#### Matchup Result")

                        # Main matchup display
                        col1, col2, col3 = st.columns([2, 1, 2])

                        with col1:
                            st.markdown(f"### {matchup.player_a}")
                            st.metric(
                                "Win Probability",
                                f"{matchup.prob_a_wins*100:.1f}%",
                                delta=format_american_odds(matchup.odds_a)
                            )
                            # Player A stats
                            st.caption(f"Model Rank: #{int(player_a_data.get('model_rank', 'N/A'))}")
                            sg_a = player_a_data.get('sg_total', 0) or 0
                            st.caption(f"SG Total: {sg_a:+.2f}")

                        with col2:
                            st.markdown("### VS")
                            st.markdown(f"**Confidence:** {matchup.confidence}")

                        with col3:
                            st.markdown(f"### {matchup.player_b}")
                            st.metric(
                                "Win Probability",
                                f"{matchup.prob_b_wins*100:.1f}%",
                                delta=format_american_odds(matchup.odds_b)
                            )
                            # Player B stats
                            st.caption(f"Model Rank: #{int(player_b_data.get('model_rank', 'N/A'))}")
                            sg_b = player_b_data.get('sg_total', 0) or 0
                            st.caption(f"SG Total: {sg_b:+.2f}")

                        # Recommendation
                        st.markdown("---")
                        if matchup.prob_a_wins > 0.55:
                            st.success(f"**Recommendation:** {matchup.player_a} ({format_american_odds(matchup.odds_a)})")
                        elif matchup.prob_b_wins > 0.55:
                            st.success(f"**Recommendation:** {matchup.player_b} ({format_american_odds(matchup.odds_b)})")
                        else:
                            st.info("**Recommendation:** This matchup is close - consider passing or taking the + odds")

                        if live_h2h_row is not None:
                            oa = pd.to_numeric(live_h2h_row.get("odds_a"), errors="coerce")
                            ob = pd.to_numeric(live_h2h_row.get("odds_b"), errors="coerce")
                            if pd.notna(oa) and pd.notna(ob):
                                st.markdown("#### Live Sportsbook Line")
                                l1, l2, l3, l4 = st.columns(4)
                                with l1:
                                    st.metric(f"{matchup.player_a} Odds", f"{int(oa):+d}")
                                with l2:
                                    st.metric(f"{matchup.player_b} Odds", f"{int(ob):+d}")
                                with l3:
                                    st.metric(f"{matchup.player_a} Edge", f"{calculate_edge(matchup.prob_a_wins, int(oa)):+.1f} pts")
                                with l4:
                                    st.metric(f"{matchup.player_b} Edge", f"{calculate_edge(matchup.prob_b_wins, int(ob)):+.1f} pts")

                        # Key factors
                        st.markdown("#### Key Factors")
                        for factor, detail in matchup.factors.items():
                            st.markdown(f"- **{factor}:** {detail}")

                elif player_a == player_b:
                    st.warning("Please select two different players")

                # Quick matchup suggestions
                st.markdown("---")
                st.markdown("#### 🔥 Suggested Matchups")
                st.caption("Interesting matchups based on similar rankings")

                # Generate 3 interesting matchups
                if len(preds_ranked) >= 10:
                    top_ranked_df = preds_ranked.sort_values("model_rank").reset_index(drop=True)
                    suggested_matchups = [
                        (0, 1),   # #1 vs #2
                        (4, 5),   # #5 vs #6
                        (9, 14),  # #10 vs #15
                    ]

                    cols = st.columns(3)
                    for i, (idx_a, idx_b) in enumerate(suggested_matchups):
                        if idx_a < len(top_ranked_df) and idx_b < len(top_ranked_df):
                            p_a = top_ranked_df.iloc[idx_a]
                            p_b = top_ranked_df.iloc[idx_b]
                            with cols[i]:
                                st.markdown(f"**{p_a['player_name'][:12]}**")
                                st.caption("vs")
                                st.markdown(f"**{p_b['player_name'][:12]}**")

            # =================================================================
            # TAB 4: PARLAY BUILDER
            # =================================================================
            with props_tab4:
                st.markdown("### 🎲 Parlay Builder")
                st.caption("Combine multiple props into a parlay")

                if is_tournament_over:
                    st.warning("🏁 Tournament has finished. Parlays are no longer active.")

                # Contender filter for late rounds
                parlay_contenders_only = st.checkbox(
                    "Show contenders only",
                    value=(tournament_round >= 3),
                    key="parlay_contenders"
                )
                parlay_df = preds_df.copy()
                if parlay_contenders_only and live_contenders:
                    parlay_df = parlay_df[parlay_df["player_name"].apply(is_contender)]
                    st.caption(f"Showing {len(parlay_df)} contenders (within {5 if tournament_round == 4 else 7} shots of lead)")

                # Suggested parlays
                st.markdown("#### 📋 Suggested Parlays")

                suggested = generate_suggested_parlays(parlay_df)

                if suggested:
                    cols = st.columns(len(suggested))
                    for i, s in enumerate(suggested):
                        with cols[i]:
                            parlay = s["parlay"]
                            st.markdown(f"**{s['name']}**")
                            st.caption(s["description"])

                            for leg in parlay.legs:
                                st.markdown(f"- {leg.description}")

                            st.metric(
                                "Odds",
                                format_american_odds(parlay.combined_odds),
                                delta=f"${parlay.payout_per_unit:.0f} on $10"
                            )
                            st.caption(f"Prob: {parlay.combined_prob*100:.1f}%")
                else:
                    st.info("Not enough data to generate suggested parlays")

                st.markdown("---")

                # Custom parlay builder
                st.markdown("#### 🔧 Build Custom Parlay")

                # Initialize session state for parlay legs
                if "parlay_legs" not in st.session_state:
                    st.session_state.parlay_legs = []

                # Add leg form
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    leg_player = st.selectbox("Player:", parlay_df["player_name"].tolist()[:30], key="parlay_player")
                with col2:
                    leg_type = st.selectbox("Prop:", ["Top 5", "Top 10", "Top 20", "Make Cut"], key="parlay_type")
                with col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_leg = st.button("Add Leg", type="primary")

                if add_leg and leg_player:
                    # Get probability for this prop
                    player_data = preds_df[preds_df["player_name"] == leg_player].iloc[0].to_dict()
                    prop_map = {
                        "Top 5": player_data.get("top5_prob", 0.15),
                        "Top 10": player_data.get("top10_prob", 0.25),
                        "Top 20": player_data.get("top20_prob", 0.40),
                        "Make Cut": min(0.85, (player_data.get("top20_prob", 0.40) or 0.40) * 1.5 + 0.2)
                    }
                    prob = prop_map.get(leg_type, 0.5) or 0.5

                    new_leg = ParlayLeg(
                        description=f"{leg_player} {leg_type}",
                        probability=prob,
                        odds=prob_to_american(prob)
                    )
                    st.session_state.parlay_legs.append(new_leg)
                    st.rerun()

                # Display current parlay
                if st.session_state.parlay_legs:
                    st.markdown("**Current Parlay:**")
                    for i, leg in enumerate(st.session_state.parlay_legs):
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.markdown(f"{i+1}. {leg.description}")
                        with col2:
                            st.caption(format_american_odds(leg.odds))
                        with col3:
                            if st.button("❌", key=f"remove_{i}"):
                                st.session_state.parlay_legs.pop(i)
                                st.rerun()

                    # Calculate parlay
                    if len(st.session_state.parlay_legs) >= 2:
                        parlay = calculate_parlay(st.session_state.parlay_legs)
                        st.markdown("---")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Combined Odds", format_american_odds(parlay.combined_odds))
                        with col2:
                            st.metric("Win Probability", f"{parlay.combined_prob*100:.2f}%")
                        with col3:
                            st.metric("$10 Pays", f"${parlay.payout_per_unit:.2f}")

                    # Clear button
                    if st.button("Clear Parlay"):
                        st.session_state.parlay_legs = []
                        st.rerun()
                else:
                    st.info("Add at least 2 legs to build a parlay")

# ============================================================================
# PAGE: PREDICTIONS
# ============================================================================

elif page == "📊 Predictions":
    st.markdown("## 📊 Prediction Results")

    prediction_files = get_prediction_files()

    if not prediction_files:
        st.warning("No prediction files found. Run predictions first!")
    else:
        # File selector
        file_options = {f.stem.replace('_predictions', '').replace('_', ' ').title(): f
                       for f in prediction_files[:10]}

        selected = st.selectbox("Select Tournament:", list(file_options.keys()))
        df = pd.read_csv(file_options[selected])

        # Summary row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Players", len(df))
        with col2:
            st.metric("Avg EV", f"${df['expected_value'].mean():,.0f}")
        with col3:
            st.metric("Max EV", f"${df['expected_value'].max():,.0f}")
        with col4:
            with_history = df['hist_times_played'].notna().sum()
            st.metric("With History", f"{with_history}/{len(df)}")

        st.markdown("---")

        # Tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏆 Top Picks", "🎖️ Tier List", "⚔️ Head-to-Head", "📈 Visualizations", "🔍 Search"]) 

        with tab1:
            top_20 = df.nlargest(20, 'expected_value').copy()

            display_cols = ['player_name', 'expected_value', 'win_prob', 'top5_prob',
                           'top10_prob', 'sg_total', 'hist_times_played']

            display_df = top_20[display_cols].copy()
            display_df['expected_value'] = display_df['expected_value'].apply(lambda x: f"${x:,.0f}")
            display_df['win_prob'] = (display_df['win_prob'] * 100).round(2)
            display_df['top5_prob'] = (display_df['top5_prob'] * 100).round(1)
            display_df['top10_prob'] = (display_df['top10_prob'] * 100).round(1)
            display_df['sg_total'] = display_df['sg_total'].round(3)
            display_df['hist_times_played'] = display_df['hist_times_played'].fillna(0).astype(int)

            display_df.columns = ['Player', 'Expected Value', 'Win %', 'Top-5 %',
                                 'Top-10 %', 'SG Total', 'Course Plays']

            st.dataframe(display_df, hide_index=True, use_container_width=True)

        with tab2:
            render_tier_list(df)

        with tab3:
            render_head_to_head(df)

        with tab4:
            chart = st.radio("Select chart:",
                            ["Win Probability", "EV Distribution", "Form vs EV"],
                            horizontal=True)

            if chart == "Win Probability":
                top_30 = df.nlargest(30, 'win_prob')
                fig = px.bar(top_30, x='player_name', y='win_prob',
                            title="Top 30 by Win Probability")
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            elif chart == "EV Distribution":
                fig = px.histogram(df, x='expected_value', nbins=50,
                                  title="Expected Value Distribution")
                st.plotly_chart(fig, use_container_width=True)

            elif chart == "Form vs EV":
                fig = px.scatter(df, x='sg_total', y='expected_value',
                                hover_data=['player_name'],
                                title="Recent Form vs Expected Value")
                st.plotly_chart(fig, use_container_width=True)

        with tab5:
            search = st.text_input("Search for a player:")
            if search:
                results = df[df['player_name'].str.contains(search, case=False, na=False)]
                if len(results) > 0:
                    for _, player in results.iterrows():
                        with st.expander(f"📊 {player['player_name']}", expanded=True):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Expected Value", f"${player['expected_value']:,.0f}")
                                st.metric("Win %", f"{player['win_prob']*100:.2f}%")
                            with col2:
                                st.metric("Top-5 %", f"{player['top5_prob']*100:.1f}%")
                                st.metric("Top-10 %", f"{player['top10_prob']*100:.1f}%")
                            with col3:
                                st.metric("SG Total", f"{player['sg_total']:+.3f}")
                                plays = player['hist_times_played']
                                st.metric("Course History",
                                         f"{int(plays)} plays" if pd.notna(plays) else "None")
                else:
                    st.warning(f"No players found matching '{search}'")


# ============================================================================
# PAGE: LIVE
# ============================================================================

elif page == "🔴 Live":
    st.markdown("## 🔴 Live Tournament Tracking")

    # Load leaderboard data first
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(LIVE_DIR.glob("leaderboard_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)

    # Tournament selector and refresh
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        if existing:
            file_options = {}
            for f in existing[:10]:
                meta_path = leaderboard_meta_path(f)
                name = f.stem.replace("leaderboard_", "").upper()
                meta = load_leaderboard_meta(meta_path)
                if meta:
                    name = meta.get("tournament_name", name)
                file_options[name] = f
            selected = st.selectbox("Tournament:", list(file_options.keys()), key="live_select")
        else:
            selected = None
            st.info("No leaderboard data. Fetch or upload below.")

    with col2:
        fetch_id = st.text_input("Fetch Tournament ID:", placeholder="R2026005", key="fetch_id")

    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            with st.spinner("Fetching..."):
                tid = fetch_id if fetch_id else None
                df, meta, error = fetch_live_leaderboard(tid)
                if not error and df is not None:
                    st.success("Updated!")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(error or "Failed to fetch")

    # Load selected data
    live_df = None
    live_meta = {}
    if selected and existing:
        live_df = pd.read_csv(file_options[selected])
        meta_path = leaderboard_meta_path(file_options[selected])
        live_meta = load_leaderboard_meta(meta_path)

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Leaderboard",
        "🎯 vs Predictions",
        "💰 vs Market Odds",
        "🏆 My Lineup",
        "📤 Upload"
    ])

    with tab1:
        if live_df is not None:
            render_live_leaderboard(live_df, live_meta)
        else:
            st.info("Select a tournament or fetch live data to view leaderboard")

    with tab2:
        if live_df is not None:
            render_live_vs_predictions(live_df, live_meta)
        else:
            st.info("Load leaderboard data first")

    with tab3:
        if live_df is not None:
            render_live_odds_comparison(live_df)
        else:
            st.info("Load leaderboard data first")

    with tab4:
        if live_df is not None:
            render_fantasy_lineup_tracker(live_df)
        else:
            st.info("Load leaderboard data first")

    with tab5:
        st.markdown("### Upload Leaderboard CSV")
        st.markdown("""
        Upload a CSV with columns: `player_name`, `position`, `total`, `thru`, `R1`-`R4` (optional)
        """)

        uploaded = st.file_uploader("Choose a CSV file", type="csv", key="live_upload")

        if uploaded:
            tournament_name = st.text_input("Tournament Name:", value=uploaded.name.replace(".csv", ""))

            if st.button("💾 Save Leaderboard", type="primary"):
                df = pd.read_csv(uploaded)

                required = ["player_name"]
                missing = [c for c in required if c not in df.columns]
                if missing:
                    st.error(f"Missing required columns: {missing}")
                else:
                    if "position" not in df.columns:
                        df["position"] = range(1, len(df) + 1)

                    slug = tournament_name.lower().replace(" ", "_").replace("-", "_")
                    out_path = LIVE_DIR / f"leaderboard_{slug}.csv"
                    df.to_csv(out_path, index=False)

                    meta = {
                        "tournament_name": tournament_name,
                        "fetched_at": datetime.now().isoformat(),
                        "player_count": len(df),
                    }
                    meta_path = LIVE_DIR / f"leaderboard_{slug}_meta.json"
                    with open(meta_path, "w") as f:
                        json.dump(meta, f, indent=2)

                    st.success(f"Saved to {out_path}")
                    st.cache_data.clear()

# =============================================================================
# PAGE: PIPELINE CONTROL
# =============================================================================
elif page == "⚙️ Pipeline":
    st.markdown("## ⚙️ Pipeline Control")
    st.caption("Smart weekly workflow - run the right scrapers at the right time")

    import subprocess

    # Helper function for running commands
    def run_scraper(cmd, timeout=120):
        """Run a scraper command and return success status."""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            if err:
                output = f"{output}\n{err}".strip() if output else err
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    def normalize_file_slug(name: str) -> str:
        """Create filesystem-safe slug for generated filenames."""
        if not name:
            return "tournament"
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return slug or "tournament"

    def resolve_power_rankings_slug(t_id: str, schedule_slug: str, tournament_name: str) -> str:
        """
        Resolve a slug that exists in data/power_rankings/paths.csv.
        Priority:
        1) direct tournament_id match in paths.csv
        2) schedule slug / normalized variants if present in paths.csv
        """
        paths_file = DATA_DIR / "power_rankings" / "paths.csv"
        if not paths_file.exists():
            return ""

        try:
            paths_df = pd.read_csv(paths_file, dtype=str).fillna("")
        except Exception:
            return ""

        tid = str(t_id or "").strip().upper()
        if tid and "pga_id" in paths_df.columns:
            tid_rows = paths_df[paths_df["pga_id"].str.upper().str.strip() == tid]
            if not tid_rows.empty:
                slug_val = str(tid_rows.iloc[0].get("slug", "")).strip()
                if slug_val:
                    return slug_val

        available = set(paths_df.get("slug", pd.Series(dtype=str)).astype(str).str.strip().tolist())
        if not available:
            return ""

        candidates = []
        sched = str(schedule_slug or "").strip()
        if sched:
            candidates.extend([sched, sched.replace("-", "_"), f"{sched.replace('-', '_')}_2026"])

        hyphen_name = re.sub(r"[^a-z0-9]+", "-", str(tournament_name or "").lower()).strip("-")
        if hyphen_name:
            under_name = hyphen_name.replace("-", "_")
            candidates.extend([hyphen_name, under_name, f"{under_name}_2026"])

        for c in candidates:
            if c in available:
                return c

        return ""

    def build_tournament_page_url(t_id: str, schedule_slug: str) -> str:
        """Build PGA TOUR tournament page URL used as fallback for PR discovery."""
        tid = str(t_id or "").strip().upper()
        slug = str(schedule_slug or "").strip().strip("/")
        if not tid or not slug:
            return ""
        # Tournament IDs are RYYYYNNN; year is chars 1:5.
        year = tid[1:5] if len(tid) >= 5 and tid.startswith("R") else ""
        if not year.isdigit():
            return ""
        return f"https://www.pgatour.com/tournaments/{year}/{slug}/{tid}"

    # Load schedule for tournament selection
    schedule_df = pd.DataFrame()
    schedule_path = DATA_DIR / "raw" / "schedule_2026.csv"
    if schedule_path.exists():
        schedule_df = pd.read_csv(schedule_path)
        if "purse" in schedule_df.columns:
            schedule_df["purse"] = schedule_df["purse"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False)
            schedule_df["purse"] = pd.to_numeric(schedule_df["purse"], errors="coerce")

    # Determine current day and tournament status
    today = datetime.now()
    day_of_week = today.strftime("%A")
    today_str = today.strftime("%Y-%m-%d")

    current_tournament = None
    next_tournament = None
    last_tournament = None
    tournament_in_progress = False

    if not schedule_df.empty:
        schedule_df["start_dt"] = pd.to_datetime(schedule_df["start_date"])
        schedule_df["end_dt"] = pd.to_datetime(schedule_df["end_date"])
        today_dt = pd.to_datetime(today_str)

        # Current tournament (in progress)
        current = schedule_df[(schedule_df["start_dt"] <= today_dt) & (schedule_df["end_dt"] >= today_dt)]
        if not current.empty:
            current_tournament = current.iloc[0]
            tournament_in_progress = True

        # Next upcoming tournament
        upcoming = schedule_df[schedule_df["start_dt"] > today_dt].sort_values("start_dt")
        if not upcoming.empty:
            next_tournament = upcoming.iloc[0]

        # Last completed tournament
        past = schedule_df[schedule_df["end_dt"] < today_dt].sort_values("end_dt", ascending=False)
        if not past.empty:
            last_tournament = past.iloc[0]

    # Smart Schedule Banner
    st.markdown("### 📅 Today's Schedule")

    if day_of_week == "Monday":
        st.info("📊 **Monday** — Post-tournament day. Update rankings and record last week's results.")
        recommended_action = "monday"
    elif day_of_week == "Tuesday":
        st.info("📋 **Tuesday** — Prep day. Fetch field, betting profiles, and run initial predictions.")
        recommended_action = "tuesday"
    elif day_of_week == "Wednesday":
        st.info("🎯 **Wednesday** — Final prep. Refresh odds and finalize picks before tournament starts.")
        recommended_action = "wednesday"
    elif day_of_week in ["Thursday", "Friday", "Saturday"]:
        st.info(f"🔴 **{day_of_week}** — Tournament in progress. Fetch live leaderboard and updated odds.")
        recommended_action = "live"
    else:  # Sunday
        st.info("🏁 **Sunday** — Final round. Record results after tournament ends.")
        recommended_action = "sunday"

    # Tournament Status
    col1, col2 = st.columns(2)
    with col1:
        if tournament_in_progress and current_tournament is not None:
            st.success(f"🏌️ **In Progress:** {current_tournament['tournament_name']}")
            active_tournament = current_tournament
        elif next_tournament is not None:
            days_until = (next_tournament["start_dt"] - today_dt).days
            st.warning(f"📆 **Next:** {next_tournament['tournament_name']} ({days_until} days)")
            active_tournament = next_tournament
        else:
            active_tournament = None
            st.warning("No upcoming tournament found")

    with col2:
        if last_tournament is not None:
            st.caption(f"Last week: {last_tournament['tournament_name']}")

    # Get active tournament details
    if active_tournament is not None:
        tournament_id = str(active_tournament.get("tournament_id", ""))
        power_slug = str(active_tournament.get("power_slug", ""))
        selected_tournament = str(active_tournament.get("tournament_name", ""))
        purse = active_tournament.get("purse", 0)
        tournament_type = str(active_tournament.get("tournament_type", "Standard"))

        st.caption(f"ID: {tournament_id} | Purse: ${purse:,.0f} | Type: {tournament_type}")
    else:
        tournament_id = ""
        power_slug = ""
        selected_tournament = ""
        purse = 0
        tournament_type = "Standard"

    st.markdown("---")

    # =========================================================================
    # SMART WORKFLOW TABS
    # =========================================================================
    workflow_tabs = st.tabs([
        "📊 Monday",
        "📋 Tuesday",
        "🎯 Wednesday",
        "🔴 Live",
        "🏁 Record Results",
        "🔧 Manual",
        "⏰ Scheduler"
    ])

    # -------------------------------------------------------------------------
    # MONDAY TAB - Post-Tournament
    # -------------------------------------------------------------------------
    with workflow_tabs[0]:
        st.markdown("### 📊 Monday — Post-Tournament Refresh")
        st.caption("Run after tournament ends to update rankings and stats")

        mon_col1, mon_col2 = st.columns([2, 1])
        with mon_col1:
            st.markdown("""
            **What this does:**
            - 🌍 Updates OWGR world rankings (changes Monday)
            - 📈 Refreshes player form stats with weekend results
            - 👥 Updates player database
            - 📜 Records historical leaderboard
            """)

        with mon_col2:
            if st.button("🚀 Run Monday Refresh", type="primary", use_container_width=True, key="mon_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("World Rankings", ["python3", "scripts/scrapers/fetch_world_rankings.py"]),
                    ("Player Database", ["python3", "scripts/scrapers/fetch_player_database.py"]),
                    ("Form Stats", ["python3", "scripts/scrapers/fetch_form_stats.py", "--year", "2026"]),
                ]

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    success, output = run_scraper(cmd, timeout=120)
                    results.append((name, success))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # TUESDAY TAB - Tournament Prep
    # -------------------------------------------------------------------------
    with workflow_tabs[1]:
        st.markdown("### 📋 Tuesday — Tournament Prep")
        st.caption("Run to prepare for the new tournament week")

        tues_col1, tues_col2 = st.columns([2, 1])
        with tues_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 🏌️ Fetches tournament field from PGA Tour
            - ⛳ Gets course characteristics and history
            - 💼 Fetches betting profiles with course history
            - 📊 Fetches power rankings
            - 🎯 Generates initial predictions
            """)

        with tues_col2:
            if tournament_id:
                if st.button("🚀 Run Tuesday Prep", type="primary", use_container_width=True, key="tues_run"):
                    progress = st.progress(0)
                    status = st.empty()

                    slug = normalize_file_slug(selected_tournament)
                    field_path = f"data/fields/{slug}_field.csv"
                    pr_slug = resolve_power_rankings_slug(tournament_id, power_slug, selected_tournament)
                    pr_fallback_url = build_tournament_page_url(tournament_id, power_slug)
                    pr_output_slug = (power_slug or selected_tournament).replace("-", "_").replace(" ", "_").lower()

                    tasks = [
                        ("Field", ["python3", "scripts/scrapers/fetch_field_from_pgatour.py",
                                   "--pga-id", tournament_id, "--name", selected_tournament,
                                   "--output", field_path, "--match-ids"]),
                        ("Course Info", ["python3", "scripts/scrapers/fetch_course_characteristics.py",
                                         "--tournament-id", tournament_id, "--profile"]),
                        ("Betting Profiles", ["python3", "scripts/scrapers/fetch_betting_profiles.py",
                                              "--tournament-id", tournament_id, "--field", field_path]),
                        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                                      "--tournament-id", tournament_id]),
                    ]
                    if pr_slug:
                        tasks.insert(2, ("Power Rankings", ["python3", "scripts/scrapers/fetch_power_rankings.py",
                                                             "--slug", pr_slug, "--allow-fail"]))
                    elif pr_fallback_url:
                        tasks.insert(2, ("Power Rankings", ["python3", "scripts/scrapers/fetch_power_rankings.py",
                                                             "--path", pr_fallback_url,
                                                             "--slug", pr_output_slug,
                                                             "--allow-fail"]))
                    else:
                        st.warning(
                            "Power rankings path not configured and no tournament page URL could be built. "
                            "Add a row in data/power_rankings/paths.csv."
                        )

                    results = []
                    for i, (name, cmd) in enumerate(tasks):
                        status.text(f"Running: {name}...")
                        success, output = run_scraper(cmd, timeout=180)
                        results.append((name, success))
                        progress.progress((i + 1) / len(tasks))

                    # Run predictions
                    status.text("Generating predictions...")
                    pred_cmd = [
                        "python3", "scripts/run_pipeline.py",
                        "--tournament", selected_tournament,
                        "--use-schedule", "--skip-refresh", "--calibrate", "--lineup"
                    ]
                    success, output = run_scraper(pred_cmd, timeout=300)
                    results.append(("Predictions", success))
                    progress.progress(1.0)

                    status.empty()
                    progress.empty()

                    for name, success in results:
                        if success:
                            st.success(f"✅ {name}")
                        else:
                            st.error(f"❌ {name}")

                    st.cache_data.clear()
            else:
                st.warning("Select a tournament first")

    # -------------------------------------------------------------------------
    # WEDNESDAY TAB - Final Prep
    # -------------------------------------------------------------------------
    with workflow_tabs[2]:
        st.markdown("### 🎯 Wednesday — Final Prep")
        st.caption("Refresh odds and finalize picks before tournament starts")

        wed_col1, wed_col2 = st.columns([2, 1])
        with wed_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 🎰 Refreshes DraftKings odds (lines move daily)
            - 🏆 Refreshes PGA Tour odds
            - 📊 Updates power rankings
            - 🎯 Re-runs predictions with latest data
            """)

        with wed_col2:
            if tournament_id:
                if st.button("🚀 Run Wednesday Refresh", type="primary", use_container_width=True, key="wed_run"):
                    progress = st.progress(0)
                    status = st.empty()

                    tasks = [
                        ("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                             "--tournament-id", tournament_id]),
                        ("PGA Odds", ["python3", "scripts/scrapers/fetch_pga_odds.py",
                                      "--tournament-id", tournament_id]),
                    ]

                    results = []
                    for i, (name, cmd) in enumerate(tasks):
                        status.text(f"Running: {name}...")
                        success, output = run_scraper(cmd, timeout=120)
                        results.append((name, success))
                        progress.progress((i + 1) / len(tasks))

                    # Re-run predictions
                    status.text("Updating predictions...")
                    pred_cmd = [
                        "python3", "scripts/run_pipeline.py",
                        "--tournament", selected_tournament,
                        "--use-schedule", "--skip-refresh", "--calibrate", "--lineup"
                    ]
                    success, output = run_scraper(pred_cmd, timeout=300)
                    results.append(("Predictions", success))
                    progress.progress(1.0)

                    status.empty()
                    progress.empty()

                    for name, success in results:
                        if success:
                            st.success(f"✅ {name}")
                        else:
                            st.error(f"❌ {name}")

                    st.cache_data.clear()
            else:
                st.warning("Select a tournament first")

    # -------------------------------------------------------------------------
    # LIVE TAB - During Tournament
    # -------------------------------------------------------------------------
    with workflow_tabs[3]:
        st.markdown("### 🔴 Live — Tournament Updates")
        st.caption("Run during tournament to get live scores and odds")

        live_col1, live_col2 = st.columns([2, 1])
        with live_col1:
            st.markdown(f"""
            **Tournament:** {selected_tournament or 'Select tournament'}

            **What this does:**
            - 📊 Fetches live leaderboard scores
            - 🎰 Updates DraftKings live odds
            """)

        with live_col2:
            if st.button("🔄 Refresh Live Data", type="primary", use_container_width=True, key="live_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("Live Leaderboard", ["python3", "scripts/scrapers/fetch_live_leaderboard.py"]),
                ]
                if tournament_id:
                    tasks.append(("DraftKings Odds", ["python3", "scripts/scrapers/fetch_draftkings_props.py",
                                                      "--tournament-id", tournament_id]))

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    success, output = run_scraper(cmd, timeout=120)
                    results.append((name, success))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # RECORD RESULTS TAB
    # -------------------------------------------------------------------------
    with workflow_tabs[4]:
        st.markdown("### 🏁 Record Results")
        st.caption("Run after tournament ends to record results and update tracking")

        rec_col1, rec_col2 = st.columns([2, 1])
        with rec_col1:
            last_tourn_name = last_tournament["tournament_name"] if last_tournament is not None else "N/A"
            st.markdown(f"""
            **Last Tournament:** {last_tourn_name}

            **What this does:**
            - 📊 Fetches final leaderboard
            - ✅ Auto-records your picks' results
            - 📈 Updates season tracking
            """)

        with rec_col2:
            if st.button("🏁 Record Results", type="primary", use_container_width=True, key="record_run"):
                progress = st.progress(0)
                status = st.empty()

                tasks = [
                    ("Final Leaderboard", ["python3", "scripts/scrapers/fetch_leaderboard.py"]),
                    ("Auto Record", ["python3", "scripts/planning/auto_record_results.py"]),
                ]

                results = []
                for i, (name, cmd) in enumerate(tasks):
                    status.text(f"Running: {name}...")
                    success, output = run_scraper(cmd, timeout=120)
                    results.append((name, success))
                    progress.progress((i + 1) / len(tasks))

                status.empty()
                progress.empty()

                for name, success in results:
                    if success:
                        st.success(f"✅ {name}")
                    else:
                        st.error(f"❌ {name}")

                st.cache_data.clear()

    # -------------------------------------------------------------------------
    # MANUAL TAB - Individual Scrapers
    # -------------------------------------------------------------------------
    with workflow_tabs[5]:
        st.markdown("### 🔧 Manual — Individual Scrapers")
        st.caption("Run individual scrapers as needed")

        # Tournament selector for manual tab
        if not schedule_df.empty:
            manual_tournament = st.selectbox(
                "Select Tournament",
                options=schedule_df["tournament_name"].tolist(),
                index=0 if active_tournament is None else schedule_df["tournament_name"].tolist().index(selected_tournament) if selected_tournament in schedule_df["tournament_name"].tolist() else 0,
                key="manual_tournament"
            )
            manual_row = schedule_df[schedule_df["tournament_name"] == manual_tournament].iloc[0]
            manual_id = str(manual_row.get("tournament_id", ""))
            manual_slug = str(manual_row.get("power_slug", ""))
        else:
            manual_tournament = ""
            manual_id = ""
            manual_slug = ""

        scraper_col1, scraper_col2, scraper_col3 = st.columns(3)

        with scraper_col1:
            st.markdown("**Core Data**")
            if st.button("🌍 World Rankings", use_container_width=True, key="m_owgr"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_world_rankings.py"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("👥 Player Database", use_container_width=True, key="m_players"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_player_database.py"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

            if st.button("📈 Form Stats", use_container_width=True, key="m_form"):
                with st.spinner("Fetching..."):
                    success, _ = run_scraper(["python3", "scripts/scrapers/fetch_form_stats.py", "--year", "2026"])
                    if success:
                        st.success("✅ Done")
                    else:
                        st.error("❌ Failed")

        with scraper_col2:
            st.markdown("**Tournament Data**")
            if st.button("🏌️ Field", use_container_width=True, key="m_field"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        slug = normalize_file_slug(manual_tournament)
                        success, output = run_scraper([
                            "python3", "scripts/scrapers/fetch_field_from_pgatour.py",
                            "--pga-id", manual_id, "--name", manual_tournament,
                            "--output", f"data/fields/{slug}_field.csv", "--match-ids"
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Field output", expanded=not success):
                                st.code(output, language=None)
                else:
                    st.warning("Need tournament ID")

            if st.button("⛳ Course Info", use_container_width=True, key="m_course"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, output = run_scraper([
                            "python3", "scripts/scrapers/fetch_course_characteristics.py",
                            "--tournament-id", manual_id, "--profile"
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Course info output", expanded=not success):
                                st.code(output, language=None)
                else:
                    st.warning("Need tournament ID")

            if st.button("📊 Power Rankings", use_container_width=True, key="m_power"):
                resolved_slug = resolve_power_rankings_slug(manual_id, manual_slug, manual_tournament)
                fallback_url = build_tournament_page_url(manual_id, manual_slug)
                fallback_slug = (manual_slug or manual_tournament).replace("-", "_").replace(" ", "_").lower()

                if resolved_slug:
                    cmd = [
                        "python3", "scripts/scrapers/fetch_power_rankings.py",
                        "--slug", resolved_slug, "--allow-fail"
                    ]
                elif fallback_url:
                    cmd = [
                        "python3", "scripts/scrapers/fetch_power_rankings.py",
                        "--path", fallback_url, "--slug", fallback_slug, "--allow-fail"
                    ]
                else:
                    cmd = []

                if not cmd:
                    st.error(
                        "Power rankings unavailable: no configured slug and no fallback tournament URL."
                    )
                else:
                    with st.spinner("Fetching..."):
                        success, output = run_scraper(cmd)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                        if output:
                            with st.expander("Power rankings output", expanded=not success):
                                st.code(output, language=None)

        with scraper_col3:
            st.markdown("**Odds & Betting**")
            if st.button("🎰 DraftKings Odds", use_container_width=True, key="m_dk"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_draftkings_props.py",
                            "--tournament-id", manual_id
                        ], timeout=180)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

            if st.button("🏆 PGA Tour Odds", use_container_width=True, key="m_pga"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_pga_odds.py",
                            "--tournament-id", manual_id
                        ])
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

            if st.button("💼 Betting Profiles", use_container_width=True, key="m_betting"):
                if manual_id:
                    with st.spinner("Fetching..."):
                        slug = normalize_file_slug(manual_tournament)
                        success, _ = run_scraper([
                            "python3", "scripts/scrapers/fetch_betting_profiles.py",
                            "--tournament-id", manual_id, "--field", f"data/fields/{slug}_field.csv"
                        ], timeout=180)
                        if success:
                            st.success("✅ Done")
                        else:
                            st.error("❌ Failed")
                else:
                    st.warning("Need tournament ID")

    # -------------------------------------------------------------------------
    # SCHEDULER TAB - Automated Schedule
    # -------------------------------------------------------------------------
    with workflow_tabs[6]:
        st.markdown("### ⏰ Automated Scheduler")
        st.caption("Set up automatic data refresh on a schedule")

        st.markdown("""
        **Weekly Schedule:**

        | Day | Time | Task |
        |-----|------|------|
        | Monday | 6:00 AM | Post-tournament: OWGR, form stats, player DB |
        | Tuesday | 6:00 AM | Tournament prep: field, course info, profiles, predictions |
        | Tuesday | 6:00 PM | Odds refresh: DraftKings, PGA odds |
        | Wednesday | 6:00 AM | Final prep: odds refresh, re-run predictions |
        | Wednesday | 6:00 PM | Final odds refresh |
        | Thu-Sun | 8 AM, 2 PM, 8 PM | Live: leaderboard, live odds |
        | Sunday | 11:00 PM | Record: final results, auto-record picks |
        """)

        st.markdown("---")

        # Check scheduler status
        st.markdown("#### Scheduler Status")

        scheduler_history_path = PROJECT_ROOT / "logs" / "scheduler_history.json"

        if scheduler_history_path.exists():
            try:
                history = json.loads(scheduler_history_path.read_text())
                if history:
                    st.success(f"✅ Scheduler has run {len(history)} times")

                    # Show last 5 runs
                    st.markdown("**Recent Runs:**")
                    recent = history[-5:]
                    for entry in reversed(recent):
                        ts = entry.get("timestamp", "")[:16].replace("T", " ")
                        sched = entry.get("schedule", "")
                        success = entry.get("success_count", 0)
                        total = entry.get("total_count", 0)
                        status = "✓" if success == total else "⚠️"
                        st.caption(f"{status} {ts} — {sched}: {success}/{total} tasks")
                else:
                    st.info("No scheduler history yet")
            except:
                st.info("No scheduler history yet")
        else:
            st.info("Scheduler has not run yet")

        st.markdown("---")

        # Manual run buttons
        st.markdown("#### Run Scheduled Task Now")

        sched_col1, sched_col2 = st.columns(2)

        with sched_col1:
            schedule_option = st.selectbox(
                "Select Schedule",
                options=[
                    "monday",
                    "tuesday-morning",
                    "tuesday-evening",
                    "wednesday-morning",
                    "live",
                    "record"
                ],
                format_func=lambda x: {
                    "monday": "📊 Monday - Post-Tournament",
                    "tuesday-morning": "📋 Tuesday AM - Tournament Prep",
                    "tuesday-evening": "🎰 Tuesday PM - Odds Refresh",
                    "wednesday-morning": "🎯 Wednesday AM - Final Prep",
                    "live": "🔴 Live - Tournament Updates",
                    "record": "🏁 Record - Results"
                }.get(x, x),
                key="sched_select"
            )

        with sched_col2:
            if st.button("▶️ Run Now", type="primary", use_container_width=True, key="run_sched"):
                with st.spinner(f"Running {schedule_option} schedule..."):
                    success, output = run_scraper([
                        "python3", "scripts/scheduled_refresh.py",
                        "--schedule", schedule_option
                    ], timeout=600)

                    if success:
                        st.success("✅ Schedule completed!")
                        st.cache_data.clear()
                    else:
                        st.error("❌ Schedule failed")
                        with st.expander("Details"):
                            st.code(output[:2000] if output else "No output")

        st.markdown("---")

        # Setup instructions
        st.markdown("#### Setup Automated Schedule")

        st.markdown("""
        **Option 1: macOS launchd (Recommended)**

        Run this in Terminal to install automated scheduling:
        ```bash
        cd /Users/jacklegnon/Desktop/golf_data
        ./scripts/setup_scheduler.sh install
        ```

        To check status:
        ```bash
        ./scripts/setup_scheduler.sh status
        ```

        To uninstall:
        ```bash
        ./scripts/setup_scheduler.sh uninstall
        ```

        **Option 2: Cron (Linux/macOS)**

        Add to crontab (`crontab -e`):
        ```
        # Monday 6am
        0 6 * * 1 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule monday

        # Tuesday 6am & 6pm
        0 6 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-morning
        0 18 * * 2 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-evening

        # Wednesday 6am
        0 6 * * 3 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule wednesday-morning

        # Thu-Sun 8am, 2pm, 8pm
        0 8,14,20 * * 4-7 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule live

        # Sunday 11pm
        0 23 * * 0 cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule record
        ```
        """)

    # Data Status Section
    st.markdown("---")
    st.markdown("### 📁 Data Status")

    def check_file_age(filepath):
        """Get file age in hours and formatted string."""
        if not filepath.exists():
            return None, "Not found"
        mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600
        if age_hours < 1:
            return age_hours, f"{int(age_hours * 60)} min ago"
        elif age_hours < 24:
            return age_hours, f"{age_hours:.1f} hrs ago"
        else:
            return age_hours, f"{age_hours/24:.1f} days ago"

    status_col1, status_col2, status_col3 = st.columns(3)

    with status_col1:
        st.markdown("**Core Data**")
        files = [
            ("OWGR Rankings", DATA_DIR / "rankings" / "owgr_2026.csv"),
            ("Player Database", DATA_DIR / "players" / "pga_players_2026.csv"),
            ("Form Stats", DATA_DIR / "historical" / "form_stats_2026.csv"),
            ("Course History", DATA_DIR / "processed" / "course_history_2026.csv"),
        ]
        for name, path in files:
            age, age_str = check_file_age(path)
            if age is None:
                st.caption(f"❌ {name}: {age_str}")
            elif age < 24:
                st.caption(f"✅ {name}: {age_str}")
            else:
                st.caption(f"⚠️ {name}: {age_str}")

    with status_col2:
        st.markdown("**Tournament Data**")
        if tournament_id:
            files = [
                ("Field", DATA_DIR / "fields" / f"{selected_tournament.lower().replace(' ', '_')}_field.csv"),
                ("PGA Odds", DATA_DIR / "odds" / f"pga_odds_{tournament_id}.csv"),
                ("DK Odds", DATA_DIR / "odds" / f"prop_lines_{tournament_id}.csv"),
                ("Betting Profiles", DATA_DIR / "betting_profiles" / f"betting_profiles_{tournament_id}.csv"),
            ]
            for name, path in files:
                age, age_str = check_file_age(path)
                if age is None:
                    st.caption(f"❌ {name}: {age_str}")
                elif age < 24:
                    st.caption(f"✅ {name}: {age_str}")
                else:
                    st.caption(f"⚠️ {name}: {age_str}")
        else:
            st.caption("Select a tournament to see status")

    with status_col3:
        st.markdown("**Predictions**")
        pred_files = sorted(OUTPUTS_DIR.glob("*_predictions.csv"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        if pred_files:
            for f in pred_files:
                age, age_str = check_file_age(f)
                st.caption(f"📄 {f.stem[:30]}... ({age_str})")
        else:
            st.caption("No prediction files found")
