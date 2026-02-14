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
from datetime import datetime
import plotly.express as px

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
    /* Compact tabs for AI assistant */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
    }
    /* Chat message styling */
    [data-testid="stChatMessage"] {
        padding: 0.75rem 1rem;
    }
    /* Markdown tables in chat */
    [data-testid="stChatMessage"] table {
        font-size: 0.85rem;
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
# SIDEBAR
# ============================================================================

# Sidebar header
st.sidebar.markdown("## ⛳ Golf Fantasy")
st.sidebar.markdown("---")

# Navigation
page = st.sidebar.radio(
    "📍 Navigation",
    ["🏆 Strategy Dashboard", "📅 This Week", "🎯 Scoring Engine",
     "📋 My Picks", "👤 Player Stats", "💰 Odds & Experts", "📊 Predictions", "📈 Season Stats"],
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
# PAGE: STRATEGY DASHBOARD
# ============================================================================

if page == "🏆 Strategy Dashboard":
    # Header
    st.markdown('<p class="main-header">🏆 Fantasy Strategy Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Let It Ride League • 3 picks/week • 3 uses/player • 30 weeks</p>',
                unsafe_allow_html=True)
    st.markdown("---")

    engine = load_scoring_engine()

    if engine:
        # Current tournament banner
        tournament = engine.get_current_week_tournament()

        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            course_info = engine.tournament_courses.get(tournament, {})

            # Tournament header card
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### 📅 This Week: {tournament}")
                st.markdown(f"**Week {t.week}** • {t.start_date} • {t.course or t.location}")
                if course_info.get("notes"):
                    st.caption(f"💡 {course_info.get('notes')}")

            with col2:
                type_color = "#FFD700" if t.tournament_type == "Major" else "#C0C0C0" if t.tournament_type == "Signature" else "#CD7F32"
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem; background: {type_color}20; border-radius: 10px; border: 2px solid {type_color}">
                    <div style="font-size: 0.9rem; color: #666;">{t.tournament_type}</div>
                    <div style="font-size: 2rem; font-weight: bold;">{t.importance_score:.0f}</div>
                    <div style="font-size: 0.8rem; color: #666;">Importance</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")

            # Main content in columns
            col1, col2 = st.columns([2, 1])

            with col1:
                # Top Recommendations
                st.markdown("#### 🎯 Top Recommendations")

                recommendations = engine.get_tournament_recommendations(tournament, top_n=10)

                if recommendations:
                    
                    tournament_id = getattr(t, 'tournament_id', None) or tournament.lower().replace(" ", "_").replace("'", "")
                    profiles_df = load_betting_profiles(tournament_id)                                                
                                                                                                                        
                    rec_data = []                                                                                     
                    for i, score in enumerate(recommendations, 1):                                                    
                        status = "✅" if score.remaining_uses == 3 else "⚠️" if score.remaining_uses == 1 else "❌" if score.remaining_uses == 0 else "✓"                                                                                   
                                                                                                                        
                          # Generate quick insight                                                                      
                        insight = get_quick_insight(score.player, profiles_df, score)                                 
                                                                                                                        
                        rec_data.append({                                                                             
                              "#": i,                                                                                   
                              "Player": score.player,                                                                   
                              "Score": score.total_score,                                                               
                              "Form": score.current_form,                                                               
                              "Uses": f"{status} {score.remaining_uses}",                                               
                              "Insight": insight                                                                        
                          })                                                                                            
                                                                                                                        
                    df = pd.DataFrame(rec_data)

                    # Color code the score column
                    # Color code the score column                                                                     
                    st.dataframe(                                                                                     
                          df,                                                                                           
                          column_config={                                                                               
                              "#": st.column_config.NumberColumn(width="small"),                                        
                              "Score": st.column_config.ProgressColumn(                                                 
                                  min_value=0, max_value=100, format="%.0f"                                             
                              ),                                                                                        
                              "Form": st.column_config.ProgressColumn(                                                  
                                  min_value=0, max_value=100, format="%.0f"                                             
                              ),                                                                                        
                              "Insight": st.column_config.TextColumn(width="large"),                                    
                          },                                                                                            
                          hide_index=True,                                                                              
                          use_container_width=True                                                                      
                      ) 

                # Value Picks
                st.markdown("#### 💎 Value Picks")
                st.caption("Players ranked 20-60 with strong course fits")

                min_score = 35 if t.importance_score < 40 else 45
                value_picks = engine.get_value_picks(tournament, min_score=min_score)

                if value_picks:
                    for score in value_picks[:5]:
                        col_a, col_b, col_c = st.columns([2, 1, 1])
                        with col_a:
                            st.markdown(f"**#{score.owgr_rank} {score.player}**")
                        with col_b:
                            st.caption(f"Score: {score.total_score:.0f}")
                        with col_c:
                            st.caption(score.course_history_note or "No history")
                else:
                    st.info("No value picks meeting criteria")

            with col2:
                # Usage Status
                st.markdown("#### 📊 My Usage")

                if picks:
                    exhausted = [p for p, i in picks.items() if i.get("remaining_uses", 3) == 0]
                    last_use = [p for p, i in picks.items() if i.get("remaining_uses", 3) == 1]
                    available = [p for p, i in picks.items() if i.get("remaining_uses", 3) >= 2]

                    if exhausted:
                        st.markdown("**❌ Exhausted:**")
                        for p in exhausted:
                            st.caption(f"  {p}")

                    if last_use:
                        st.markdown("**⚠️ Last Use:**")
                        for p in last_use:
                            st.caption(f"  {p}")

                    if available:
                        st.markdown("**✅ Available:**")
                        for p in available[:5]:
                            st.caption(f"  {p}")
                        if len(available) > 5:
                            st.caption(f"  +{len(available)-5} more")
                else:
                    st.info("No picks recorded yet")

                st.markdown("---")

                # Upcoming Events
                st.markdown("#### 🗓️ Coming Up")

                today = datetime.now().strftime('%Y-%m-%d')
                upcoming = [(n, t) for n, t in engine.tournaments.items()
                           if t.start_date > today and t.importance_score >= 40]
                upcoming.sort(key=lambda x: x[1].start_date)

                for name, t in upcoming[:5]:
                    icon = "⭐" if t.tournament_type == "Major" else "★" if t.tournament_type == "Signature" else "•"
                    st.markdown(f"{icon} **Wk {t.week}**: {name[:25]}")

        else:
            st.warning("No current tournament found")
    else:
        st.error("Could not load scoring engine")
        
        
        
    st.markdown("### 🔄 Weekly Data Refresh")                                                                             
                                                                                                                        
    col1, col2, col3 = st.columns(3)                                                                                      
    with col1:                                                                                                            
        if st.button("🔄 Quick Refresh", use_container_width=True):                                                       
            output = run_script("weekly_prep.py", "--quick")                                                              
            st.code(output, language=None)                                                                                
    with col2:                                                                                                            
        if st.button("🔄 Full Refresh", use_container_width=True, type="primary"):                                        
            output = run_script("weekly_prep.py")                                                                         
            st.code(output, language=None)                                                                                
    with col3:                                                                                                            
        if st.button("👁️ Preview", use_container_width=True):                                                             
            output = run_script("weekly_prep.py", "--dry-run")                                                            
            st.code(output, language=None)                                                                                
                

    # ============================================================================
# PAGE: THIS WEEK
# ============================================================================

elif page == "📅 This Week":
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
    st.caption("Run scoring engine commands — same output as terminal")

    engine = load_scoring_engine()

    # Current tournament banner
    if engine:
        tournament = engine.get_current_week_tournament()
        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            st.success(f"📍 **This Week:** {tournament} — Week {t.week} • {t.tournament_type} • Importance: {t.importance_score:.0f}/100")

    st.markdown("---")

    # Main scoring engine buttons
    st.markdown("### 📋 This Week's Picks")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        run_this_week = st.button("📋 This Week", use_container_width=True, type="primary", help="--this-week")
    with col2:
        run_value = st.button("💎 Value Picks", use_container_width=True, help="--value")
    with col3:
        run_strategy = st.button("📊 Strategy", use_container_width=True, help="--strategy")
    with col4:
        run_top_20 = st.button("🔝 Top 20", use_container_width=True, help="--this-week --top 20")

    if run_this_week:
        with st.spinner("Running: scoring_engine.py --this-week"):
            output = run_script("planning/scoring_engine.py", "--this-week")
        st.code(output, language=None)

    if run_value:
        with st.spinner("Running: scoring_engine.py --value"):
            output = run_script("planning/scoring_engine.py", "--value")
        st.code(output, language=None)

    if run_strategy:
        with st.spinner("Running: scoring_engine.py --strategy"):
            output = run_script("planning/scoring_engine.py", "--strategy")
        st.code(output, language=None)

    if run_top_20:
        with st.spinner("Running: scoring_engine.py --this-week --top 20"):
            output = run_script("planning/scoring_engine.py", "--this-week", "--top", "20")
        st.code(output, language=None)

    st.markdown("---")

    # Weekly Report
    st.markdown("### 📰 Weekly Report")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        run_report = st.button("📰 Full Report", use_container_width=True, type="primary")

    if run_report:
        with st.spinner("Running: weekly_report.py"):
            output = run_script("planning/weekly_report.py")
        st.code(output, language=None)

    st.markdown("---")

    # Power Rankings
    st.markdown("### 📈 Power Rankings")
    col1, col2 = st.columns(2)

    with col1:
        show_power_rankings = st.button("📈 Show Rankings", use_container_width=True, type="primary")

    if show_power_rankings:
        pr_dir = DATA_DIR / "power_rankings"
        if pr_dir.exists():
            pr_files = sorted(pr_dir.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
            pr_files = [f for f in pr_files if f.name not in ("paths.csv",) and not f.name.startswith(".")]
            if pr_files:
                latest_pr = pr_files[0]
                df = pd.read_csv(latest_pr)

                # Get tournament name if available
                tournament_name = df['tournament_name'].iloc[0] if 'tournament_name' in df.columns else latest_pr.stem.replace('_', ' ').title()
                st.markdown(f"**📈 Power Rankings:** {tournament_name.strip()}")

                # Sort by rank
                if 'rank' in df.columns:
                    df = df.sort_values('rank')

                # Check if we have analysis column for rich display
                has_analysis = 'analysis' in df.columns
                player_col = 'player_name' if 'player_name' in df.columns else 'player'

                if has_analysis and player_col in df.columns:
                    # Rich display with analysis
                    st.markdown("---")

                    # Show top 15 with analysis
                    for _, row in df.head(15).iterrows():
                        rank = row.get('rank', '?')
                        player = row.get(player_col, 'Unknown')
                        country = row.get('country_flag', row.get('country', ''))[:3] if row.get('country_flag') or row.get('country') else ''
                        analysis = row.get('analysis', '')

                        # Create a card-like display
                        with st.container():
                            col1, col2 = st.columns([1, 8])
                            with col1:
                                st.markdown(f"### #{rank}")
                            with col2:
                                st.markdown(f"**{player}** {country}")
                                if analysis:
                                    st.caption(analysis)
                            st.markdown("---")
                else:
                    # Fallback to simple table
                    if 'rank' in df.columns and player_col in df.columns:
                        display_cols = ['rank', player_col] + [c for c in df.columns if c not in ('rank', player_col, 'analysis', 'scraped_at', 'source')][:3]
                        display_cols = [c for c in display_cols if c in df.columns]
                        st.dataframe(df[display_cols].head(20), hide_index=True, use_container_width=True)
                    else:
                        st.dataframe(df.head(20), hide_index=True, use_container_width=True)
            else:
                st.warning("No power rankings files found")
        else:
            st.warning("Power rankings directory not found")


# ============================================================================
# PAGE: MY PICKS
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
        upcoming_tourneys = [name for name, t in engine.tournaments.items() if t.start_date >= today]
        upcoming_tourneys.sort(key=lambda x: engine.tournaments[x].start_date)
        past_tourneys = [name for name, t in engine.tournaments.items() if t.start_date <= today]
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
                st.success("Picks updated! Refresh to see changes in sidebar.")

    with manage_tab2:
        st.markdown("**Record tournament result**")

        result_tourney = st.selectbox(
            "Tournament:",
            past_tourneys[:10] if past_tourneys else ["No past tournaments"],
            key="result_tourney"
        )

        result_player = st.selectbox("Player:", [""] + all_players, key="result_player")

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
# PAGE: PLAYER STATS
# ============================================================================

elif page == "👤 Player Stats":
    st.markdown("## 👤 Player Stats")
    st.caption("Strokes gained breakdown and player lookup")

    engine = load_scoring_engine()
    all_players = sorted(engine.predictions.keys()) if engine and engine.predictions else []

    st.markdown("---")

    # Player Lookup (scoring engine)
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

    # Show betting profile for selected player
    if player_search:
        profiles_df = load_betting_profiles()
        if not profiles_df.empty:
            profile = get_player_profile(profiles_df, player_search)
            if profile:
                render_player_profile_card(profile, show_full=True)



    st.markdown("---")

    # Strokes Gained Stats
    st.markdown("### 📊 Strokes Gained")
    st.caption("Detailed stats breakdown")

    col1, col2 = st.columns([2, 1])
    with col1:
        stats_player = st.selectbox("Select a player:", [""] + all_players, key="stats_player")
    with col2:
        recent_count = st.selectbox("Recent results:", [5, 10, 15], key="recent_count")

    col1, col2, col3 = st.columns(3)
    with col1:
        run_player_stats = st.button("📊 Full Stats", use_container_width=True, type="primary")
    with col2:
        run_top_sg = st.button("🏆 Top 20 SG", use_container_width=True)

    if run_player_stats and stats_player:
        with st.spinner(f"Running: player_stats.py '{stats_player}' --recent {recent_count}"):
            output = run_script("planning/player_stats.py", stats_player, "--recent", str(recent_count))
        st.code(output, language=None)

    if run_top_sg:
        with st.spinner("Running: player_stats.py --top 20"):
            output = run_script("planning/player_stats.py", "--top", "20")
        st.code(output, language=None)

    st.markdown("---")

    # Head-to-Head Comparison
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
# PAGE: ODDS & EXPERTS
# ============================================================================

elif page == "💰 Odds & Experts":
    st.markdown("## 💰 Odds & Expert Picks")
    st.caption("Vegas odds and expert recommendations")

    engine = load_scoring_engine()

    # Current tournament banner
    if engine:
        tournament = engine.get_current_week_tournament()
        if tournament and tournament in engine.tournaments:
            t = engine.tournaments[tournament]
            st.success(f"📍 **This Week:** {tournament} — Week {t.week} • {t.tournament_type}")

    st.markdown("---")

    # Betting Odds Section
    st.markdown("### 🎰 Betting Odds")
    st.caption("Vegas odds for the tournament field")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        show_favorites = st.button("🏆 Favorites", use_container_width=True, type="primary")
    with col2:
        show_top_10 = st.button("🔝 Top 10", use_container_width=True)
    with col3:
        show_longshots = st.button("🎯 Longshots", use_container_width=True)
    with col4:
        show_value = st.button("💎 Value Picks", use_container_width=True)

    if show_favorites:
        with st.spinner("Loading odds..."):
            output = run_script("planning/odds_viewer.py", "--favorites", "30")
        st.code(output, language=None)

    if show_top_10:
        with st.spinner("Loading top 10..."):
            output = run_script("planning/odds_viewer.py", "--favorites", "10")
        st.code(output, language=None)

    if show_longshots:
        with st.spinner("Loading longshots..."):
            output = run_script("planning/odds_viewer.py", "--longshots")
        st.code(output, language=None)

    if show_value:
        with st.spinner("Loading value picks..."):
            output = run_script("planning/odds_viewer.py", "--value")
        st.code(output, language=None)

    st.markdown("---")

    # Multi-Book Odds Section
    st.markdown("### 📊 Multi-Book Odds Comparison")
    st.caption("Compare odds across DraftKings, FanDuel, BetMGM, Caesars & more")

    # Tabs for different input methods
    odds_tab1, odds_tab2, odds_tab3 = st.tabs(["📊 View Odds", "📤 Upload from OddsChecker", "🔄 Fetch from API"])

    with odds_tab1:
        multi_odds_file = DATA_DIR / "odds" / "multi_book_odds_latest.csv"

        if multi_odds_file.exists():
            df = pd.read_csv(multi_odds_file)

            if not df.empty:
                source = df.get("source", pd.Series(["unknown"])).iloc[0] if "source" in df.columns else "unknown"
                st.success(f"**{len(df)} players** from **{int(df['num_books'].max())} sportsbooks** (source: {source})")

                # Consensus favorites
                st.markdown("#### ⭐ Consensus Favorites")
                fav_cols = ["rank", "player_name", "odds_consensus", "odds_best", "odds_worst", "implied_prob_consensus", "num_books"]
                fav_cols = [c for c in fav_cols if c in df.columns]
                st.dataframe(df[fav_cols].head(15), hide_index=True, use_container_width=True)

                # Value opportunities (high odds spread)
                if "value_spread_pct" in df.columns:
                    value_df = df[df["value_spread_pct"] >= 10].sort_values("value_spread_pct", ascending=False)
                    if not value_df.empty:
                        st.markdown("#### ⚡ Line Shopping Value (>10% spread)")
                        st.caption("Best odds vs worst odds - find where to place your bet!")
                        value_cols = ["player_name", "odds_best", "odds_worst", "odds_spread", "value_spread_pct"]
                        value_cols = [c for c in value_cols if c in value_df.columns]
                        st.dataframe(value_df[value_cols].head(10), hide_index=True, use_container_width=True)

                # Book comparison for top players
                book_cols = [c for c in df.columns if c.startswith("odds_") and c not in ["odds_consensus", "odds_best", "odds_worst", "odds_spread"]]
                if book_cols:
                    st.markdown("#### 📈 Book-by-Book Comparison")
                    compare_cols = ["player_name"] + book_cols[:6]
                    compare_cols = [c for c in compare_cols if c in df.columns]
                    st.dataframe(df[compare_cols].head(10), hide_index=True, use_container_width=True)
        else:
            st.info("No multi-book odds yet. Upload from OddsChecker or fetch from API.")

    with odds_tab2:
        st.markdown("#### Upload Odds from OddsChecker")
        st.markdown("""
        1. Go to [OddsChecker Golf](https://www.oddschecker.com/golf/pebble-beach/winner)
        2. Copy odds for players you're interested in
        3. Create a CSV with this format and upload below:
        """)

        st.code("""player_name,odds_draftkings,odds_fanduel,odds_betmgm,odds_caesars
Scottie Scheffler,+300,+280,+300,+290
Rory McIlroy,+1200,+1100,+1300,+1200
Tommy Fleetwood,+2500,+2200,+2500,+2400""", language="csv")

        uploaded_file = st.file_uploader("Upload CSV with multi-book odds", type="csv", key="odds_upload")

        if uploaded_file is not None:
            try:
                import numpy as np
                upload_df = pd.read_csv(uploaded_file)
                st.success(f"Loaded {len(upload_df)} players")

                # Process the uploaded data
                odds_cols = [c for c in upload_df.columns if c.startswith("odds_")]

                if odds_cols and "player_name" in upload_df.columns:
                    processed_rows = []
                    for _, row in upload_df.iterrows():
                        odds_values = []
                        for col in odds_cols:
                            val = row.get(col)
                            if pd.notna(val):
                                try:
                                    odds_num = int(str(val).replace("+", "").replace("-", ""))
                                    odds_values.append(odds_num)
                                except:
                                    pass

                        if odds_values:
                            processed_rows.append({
                                "player_name": row["player_name"],
                                "odds_consensus": int(np.mean(odds_values)),
                                "odds_best": max(odds_values),
                                "odds_worst": min(odds_values),
                                "odds_spread": max(odds_values) - min(odds_values),
                                "num_books": len(odds_values),
                                "implied_prob_consensus": 100 / (int(np.mean(odds_values)) + 100),
                                "value_spread_pct": (max(odds_values) - min(odds_values)) / np.mean(odds_values) * 100,
                                "source": "oddschecker_upload",
                            })

                    if processed_rows:
                        result_df = pd.DataFrame(processed_rows)
                        result_df = result_df.sort_values("implied_prob_consensus", ascending=False)
                        result_df["rank"] = range(1, len(result_df) + 1)

                        # Show processed data
                        st.markdown("#### Processed Odds")
                        st.dataframe(result_df[["rank", "player_name", "odds_consensus", "odds_best", "odds_worst", "value_spread_pct"]],
                                   hide_index=True, use_container_width=True)

                        # Save button
                        if st.button("💾 Save as Multi-Book Odds", type="primary"):
                            save_path = DATA_DIR / "odds" / "multi_book_odds_latest.csv"
                            result_df.to_csv(save_path, index=False)
                            st.success(f"Saved to {save_path.name}!")
                            st.rerun()
                else:
                    st.warning("CSV must have 'player_name' column and odds columns like 'odds_draftkings'")
            except Exception as e:
                st.error(f"Error processing file: {e}")

    with odds_tab3:
        st.markdown("#### Fetch from The Odds API")
        st.caption("Free tier: 500 requests/month - works for **Majors only** (Masters, PGA Championship, US Open, The Open)")

        col1, col2 = st.columns(2)
        with col1:
            sport_key = st.selectbox("Select Event", [
                "golf_masters_tournament_winner",
                "golf_pga_championship_winner",
                "golf_us_open_winner",
                "golf_the_open_championship_winner"
            ], format_func=lambda x: x.replace("golf_", "").replace("_winner", "").replace("_", " ").title())

        with col2:
            if st.button("🔄 Fetch Odds", type="primary"):
                with st.spinner("Fetching from The Odds API..."):
                    output = run_script("scrapers/fetch_odds_api.py", "--sport-key", sport_key)
                if "ERROR" in output:
                    st.error("Failed to fetch odds")
                    st.code(output, language=None)
                else:
                    st.success("Odds fetched successfully!")
                    st.code(output, language=None)
                    st.rerun()

    st.markdown("---")

    # Expert Picks Section
    st.markdown("### 📰 Expert Picks")
    st.caption("Picks from PGA Tour experts")

    col1, col2 = st.columns(2)
    with col1:
        show_expert_picks = st.button("📰 Show Expert Picks", use_container_width=True, type="primary")
    with col2:
        refresh_expert_picks = st.button("🔄 Refresh from PGA", use_container_width=True)

    if refresh_expert_picks:
        with st.spinner("Fetching latest expert picks from PGA Tour..."):
            output = run_script("scrapers/fetch_expert_picks_pga.py")
        st.success("Expert picks refreshed!")
        st.code(output, language=None)

    if show_expert_picks:
        # Load expert picks data
        expert_picks_dir = DATA_DIR / "expert_picks"
        latest_file = expert_picks_dir / "expert_picks_latest.csv"

        if not latest_file.exists():
            # Try to find any recent file
            picks_files = sorted(expert_picks_dir.glob("expert_picks_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True)
            if picks_files:
                latest_file = picks_files[0]

        if latest_file.exists():
            df = pd.read_csv(latest_file)

            if not df.empty:
                tournament = df['tournament_name'].iloc[0] if 'tournament_name' in df.columns else "Unknown"
                st.markdown(f"**Tournament:** {tournament.strip()}")

                # Count player mentions across all lineups
                from collections import Counter
                player_counts = Counter()
                winner_counts = Counter()

                for _, row in df.iterrows():
                    try:
                        lineup = json.loads(row.get('lineup_player_names', '[]'))
                        for player in lineup:
                            if player:
                                player_counts[player] += 1
                    except:
                        pass
                    winner = row.get('winner_name', '')
                    if winner:
                        winner_counts[winner] += 1

                # Show consensus picks
                st.markdown("#### ⭐ Consensus Picks")
                consensus_cols = st.columns(2)

                with consensus_cols[0]:
                    st.markdown("**Most Selected (Lineup)**")
                    for player, count in player_counts.most_common(6):
                        pct = count / len(df) * 100
                        st.markdown(f"- **{player}** — {count}/{len(df)} experts ({pct:.0f}%)")

                with consensus_cols[1]:
                    st.markdown("**Winner Picks**")
                    for player, count in winner_counts.most_common(5):
                        pct = count / len(df) * 100
                        st.markdown(f"- **{player}** — {count}/{len(df)} experts ({pct:.0f}%)")

                st.markdown("---")

                # Show each expert's picks in cards
                st.markdown("#### 👤 Expert Lineups")

                for _, row in df.iterrows():
                    expert_name = row.get('expert_name', 'Unknown')
                    expert_title = row.get('expert_title', '')
                    winner = row.get('winner_name', '')
                    comment = row.get('comment', '')

                    try:
                        lineup = json.loads(row.get('lineup_player_names', '[]'))
                        bench = json.loads(row.get('bench_player_names', '[]'))
                    except:
                        lineup = []
                        bench = []

                    with st.container():
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.markdown(f"**{expert_name}**")
                            if expert_title:
                                st.caption(expert_title)
                        with col2:
                            lineup_str = ", ".join(lineup) if lineup else "N/A"
                            st.markdown(f"**Lineup:** {lineup_str}")
                            if bench:
                                st.caption(f"Bench: {', '.join(bench)}")
                            if winner:
                                st.markdown(f"🏆 **Winner Pick:** {winner}")

                        if comment:
                            with st.expander("💬 Analysis"):
                                st.write(comment)
                        st.markdown("---")
            else:
                st.warning("No expert picks data found")
        else:
            st.warning("No expert picks file found. Click 'Refresh from PGA' to fetch.")


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
        tab1, tab2, tab3 = st.tabs(["🏆 Top Picks", "📈 Visualizations", "🔍 Search"])

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

        with tab3:
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
# PAGE: SEASON STATS
# ============================================================================

elif page == "📈 Season Stats":
    st.markdown("## 📈 Season Statistics")

    engine = load_scoring_engine()
    
    
    tab1, tab2, tab3 = st.tabs(["🏆 My Performance", "📊 Model Analysis", "Detailed Log"])
    
    
    with tab1:
    
    
        if engine:
            # Season progress
            schedule = load_schedule()
            today = datetime.now().strftime('%Y-%m-%d')

            if not schedule.empty:
                completed = len(schedule[schedule['start_date'] < today])
                total = len(schedule)

                st.progress(completed / total, text=f"Season Progress: Week {completed}/{total}")

        st.markdown("---")
        # My Performance
        st.markdown("### 📊 My Season Performance")



        if picks:
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Players Used", len(picks))
            with col2:
                st.metric("Total Picks", total_picks)
            with col3:
                st.metric("Total Points", total_points)
            with col4:
                avg_pts = total_points / total_picks if total_picks > 0 else 0
                st.metric("Avg Points/Pick", f"{avg_pts:.1f}")

            st.markdown("---")

            # Weekly breakdown
            st.markdown("### 📅 Weekly Results")

            lineups = usage_data.get("weekly_lineups", {})
            
            if lineups:                                                                                               
                weekly_data = []                                                                                      
                cumulative = 0                                                                                        
                for week_key in sorted(lineups.keys(), key=lambda x: int(x.split("_")[1])):                           
                    lineup = lineups[week_key]                                                                        
                    # Calculate week points from picks                                                                
                    week_pts = 0                                                                                      
                    for player in lineup.get("lineup", []):                                                           
                        if player in picks:                                                                           
                            for t in picks[player].get("tournaments_used", []):                                       
                                if t.get("tournament") == lineup.get("tournament"):                                   
                                    week_pts += t.get("points", 0)                                                    
                    cumulative += week_pts                                                                            
                                                                                                                    
                    weekly_data.append({                                                                              
                        "Week": lineup.get("week", "?"),                                                              
                        "Tournament": lineup.get("tournament", "Unknown")[:30],                                       
                        "Points": week_pts if week_pts else "Pending",                                                
                        "Cumulative": cumulative                                                                      
                    })                                                                                                
                                                                                                                    
                st.dataframe(pd.DataFrame(weekly_data), hide_index=True, use_container_width=True)                    
                    
        # Player usage breakdown                                                                                  
            st.markdown("---")                                                                                        
            st.markdown("### 👥 Player Usage")                                                                        
                                                                                                                    
            usage_table = []                                                                                          
            for player, info in sorted(picks.items(), key=lambda x: x[1].get("total_points", 0), reverse=True):       
                remaining = info.get("remaining_uses", 3)                                                             
                status = "❌" if remaining == 0 else "⚠️" if remaining == 1 else "✅"                                 
                                                                                                                    
                usage_table.append({                                                                                  
                    "Status": status,                                                                                 
                    "Player": player,                                                                                 
                    "Used": f"{info.get('times_used', 0)}/3",                                                         
                    "Remaining": remaining,                                                                           
                    "Points": info.get("total_points", 0)                                                             
                })                                                                                                    
                                                                                                                    
            st.dataframe(pd.DataFrame(usage_table), hide_index=True, use_container_width=True)                        
                                                                                                                    
        else:                                                                                                         
            st.info("No picks recorded yet. Start tracking your picks to see stats!")                                 
            st.code('python3 scripts/planning/usage_tracker.py --add "Player Name" --tournament "Tournament Name"')   


    # ========== TAB 2: Model Analysis ==========                                                                     
    with tab2:                                                                                                        
        st.markdown("### 📊 Model Performance")                                                                       
                                                                                                                    
        col1, col2 = st.columns(2)                                                                                    
        with col1:                                                                                                    
            if st.button("📊 Multi-Tournament Report", use_container_width=True, type="primary"):                     
                output = run_script("predictions/prediction_tracker.py", "report", "--last-n", "10")                  
                st.code(output, language=None)                                                                        
                                                                                                                    
        with col2:                                                                                                    
            if st.button("🔧 Build Calibration Factors", use_container_width=True):                                   
                output = run_script("predictions/prediction_tracker.py", "calibration-factors")                       
                st.code(output, language=None)                                                                        
                                                                                                                    
        st.markdown("---")                                                                                            
        st.markdown("### 🧠 Model Learnings")                                                                         
                                                                                                                    
        learnings_file = PROJECT_ROOT / "data" / "prediction_tracking" / "model_learnings.json"                       
        if learnings_file.exists():                                                                                   
            with open(learnings_file) as f:                                                                           
                learnings = json.load(f)                                                                              
                                                                                                                    
            col1, col2, col3 = st.columns(3)                                                                          
            with col1:                                                                                                
                st.metric("Tournaments Analyzed", learnings.get("summary", {}).get("tournaments_analyzed", 0))        
            with col2:                                                                                                
                top5_err = learnings.get("accuracy", {}).get("top5", {}).get("calibration_error", 0)                  
                st.metric("Top5 Cal. Error", f"{top5_err*100:.1f}%")                                                  
            with col3:                                                                                                
                top10_err = learnings.get("accuracy", {}).get("top10", {}).get("calibration_error", 0)                
                st.metric("Top10 Cal. Error", f"{top10_err*100:.1f}%")                                                
                                                                                                                    
            # Show biases                                                                                             
            if learnings.get("biases"):                                                                               
                st.warning("**Known Biases:**\n" + "\n".join(f"- {b}" for b in learnings["biases"]))                  
                                                                                                                    
            # Course fit effectiveness                                                                                
            cfe = learnings.get("course_fit_effectiveness", {})                                                       
            if cfe:                                                                                                   
                corr = cfe.get("correlation_with_finish", 0)                                                          
                interp = cfe.get("interpretation", "")                                                                
                if corr < 0:                                                                                          
                    st.success(f"**Course Fit:** r={corr:.3f} — {interp}")                                            
                else:                                                                                                 
                    st.info(f"**Course Fit:** r={corr:.3f} — {interp}")                                               
        else:                                                                                                         
            st.info("Run 'Multi-Tournament Report' to generate model learnings.")                                     
                                                                                                                    
        st.markdown("---")                                                                                            
        st.markdown("### 🎯 Per-Tournament Calibration")                                                              
                                                                                                                    
        # List available reports                                                                                      
        reports_dir = OUTPUTS_DIR / "picks_reports"                                                                   
        if reports_dir.exists():                                                                                      
            reports = sorted([f.stem for f in reports_dir.glob("*.txt")])                                             
            if reports:                                                                                               
                selected_report = st.selectbox("Select tournament:", reports)                                         
                if st.button("📄 View Report"):                                                                       
                    report_path = reports_dir / f"{selected_report}.txt"                                              
                    if report_path.exists():                                                                          
                        st.code(report_path.read_text(), language=None)                                               
                                                                                                                    
    # ========== TAB 3: Detailed Log ==========                                                                       
    with tab3:                                                                                                        
        st.markdown("### 📋 Detailed Season Log")                                                                     
                                                                                                                    
        col1, col2 = st.columns(2)                                                                                    
        with col1:                                                                                                    
            if st.button("📋 View Detailed Log", use_container_width=True, type="primary"):                           
                output = run_script("planning/season_log.py", "--detailed")                                           
                st.code(output, language=None)                                                                        
        with col2:                                                                                                    
            if st.button("📥 Export to CSV", use_container_width=True):                                               
                output = run_script("planning/season_log.py", "--export")                                             
                st.code(output, language=None)                                                                        
                                                                                                                    
        st.markdown("---")                                                                                            
                                                                                                                    
        # Show CSV if exists                                                                                          
        picks_log = DATA_DIR / "fantasy" / "season_picks_log.csv"                                                     
        if picks_log.exists():                                                                                        
            st.markdown("### 📊 Picks Log Data")                                                                      
            df = pd.read_csv(picks_log)                                                                               
            st.dataframe(df, use_container_width=True)                                                                
                                                                                                                    
        # Majors countdown                                                                                            
        st.markdown("---")                                                                                            
        st.markdown("### ⭐ Major Championships")                                                                     
                                                                                                                    
        if engine:                                                                                                    
            majors = [(n, t) for n, t in engine.tournaments.items()                                                   
                    if t.tournament_type == "Major" and t.start_date >= today]                                       
                                                                                                                    
            for name, t in sorted(majors, key=lambda x: x[1].start_date):                                             
                course_info = engine.tournament_courses.get(name, {})                                                 
                col1, col2, col3 = st.columns([2, 1, 1])                                                              
                                                                                                                    
                with col1:                                                                                            
                    st.markdown(f"**⭐ {name}**")                                                                     
                with col2:                                                                                            
                    st.caption(f"Week {t.week} • {t.start_date}")                                                     
                with col3:                                                                                            
                    st.caption(course_info.get("course", "TBD"))                                                      
                        
        
        


