# Weekly Golf Prediction Workflow

> Last updated: 2026-02-16

This guide walks you through the weekly process for generating golf predictions and managing your fantasy lineup.

---

## Quick Reference

```bash
# TUESDAY: Full pipeline for new tournament week
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate

# THURSDAY-SUNDAY: Live updates during tournament
python3 scripts/scrapers/fetch_live_leaderboard.py
python3 scripts/scrapers/fetch_draftkings_props.py

# SUNDAY NIGHT: Record results after tournament ends
python3 scripts/planning/auto_record_results.py

# View dashboard anytime
streamlit run dashboard.py
```

---

## Detailed Weekly Schedule

### Monday (Optional)
**Goal:** Light data refresh if needed

```bash
# Update world rankings (changes on Mondays)
python3 scripts/scrapers/fetch_world_rankings.py
```

---

### Tuesday (Main Prep Day)
**Goal:** Full data refresh and predictions for the new tournament week

#### Step 1: Run the Full Pipeline
```bash
# Auto-detects current week's tournament from schedule
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate
```

This runs:
- Data refresh (rankings, player database, form stats)
- Field fetch from PGA Tour
- Odds from PGA Tour
- Betting profiles
- Power rankings
- Course characteristics
- Predictions
- Lineup recommendations

#### Step 2: Fetch Additional Odds (Optional)
```bash
# DraftKings props and lines
python3 scripts/scrapers/fetch_draftkings_props.py

# Multi-book odds comparison
python3 scripts/scrapers/fetch_odds_api.py
```

#### Step 3: Review in Dashboard
```bash
streamlit run dashboard.py
```

Navigate to:
- **🏆 This Week** - Overview and top picks
- **🎯 Scoring Engine** - Detailed player scores
- **🎰 Betting** - Odds and value plays

---

### Wednesday
**Goal:** Finalize picks before tournament starts

#### Step 1: Refresh Odds (they change daily)
```bash
python3 scripts/scrapers/fetch_draftkings_props.py
python3 scripts/scrapers/fetch_pga_odds.py
```

#### Step 2: Get Expert Picks
```bash
python3 scripts/scrapers/fetch_expert_picks_pga.py
```

#### Step 3: Add Your Picks to Tracker
In the dashboard (**📋 My Picks** → **Add Picks**):
1. Select the tournament
2. Choose your 3 players
3. Click "Add Picks"

Or via command line:
```bash
python3 scripts/planning/usage_tracker.py --add "Player One" "Player Two" "Player Three" \
    --tournament "Tournament Name"
```

---

### Thursday - Sunday (Tournament Days)
**Goal:** Monitor live performance

#### Live Leaderboard Updates
```bash
# Run periodically during tournament rounds
python3 scripts/scrapers/fetch_live_leaderboard.py
```

#### Live Odds Updates
```bash
python3 scripts/scrapers/fetch_draftkings_props.py
```

#### View Live Data
```bash
streamlit run dashboard.py
```
Navigate to **🔴 Live** tab for real-time leaderboard with your picks highlighted.

---

### Sunday Night / Monday Morning
**Goal:** Record results and update tracking

#### Step 1: Auto-Record Results
```bash
# Automatically matches your picks to final results
python3 scripts/planning/auto_record_results.py
```

If auto-record doesn't find results, manually record:
```bash
python3 scripts/planning/usage_tracker.py --result "Player Name" \
    --tournament "Tournament Name" \
    --finish "T15" \
    --points 45
```

#### Step 2: Verify Results
```bash
python3 scripts/planning/usage_tracker.py --summary
python3 scripts/planning/usage_tracker.py --lineups
```

#### Step 3: Update Historical Data
```bash
# Add tournament results to historical leaderboards
python3 scripts/scrapers/fetch_leaderboard.py
```

---

## Key Scripts Reference

### Data Fetching
| Script | Purpose | When to Run |
|--------|---------|-------------|
| `fetch_world_rankings.py` | OWGR rankings | Monday/Tuesday |
| `fetch_field_from_pgatour.py` | Tournament field | Tuesday |
| `fetch_draftkings_props.py` | DK odds & props | Daily |
| `fetch_pga_odds.py` | PGA Tour odds | Daily |
| `fetch_odds_api.py` | Multi-book odds | Tuesday/Wednesday |
| `fetch_betting_profiles.py` | Player betting profiles | Tuesday |
| `fetch_expert_picks_pga.py` | Expert consensus | Wednesday |
| `fetch_live_leaderboard.py` | Live scores | During tournament |
| `fetch_weather_openmetro.py` | Weather forecast | Wednesday |

### Predictions & Analysis
| Script | Purpose | When to Run |
|--------|---------|-------------|
| `run_pipeline.py` | Full prediction pipeline | Tuesday |
| `scoring_engine.py` | Score players for tournament | After predictions |
| `weight_optimizer.py` | Test scoring weights | Periodically |

### Fantasy Management
| Script | Purpose | When to Run |
|--------|---------|-------------|
| `usage_tracker.py` | Track picks & uses | Before/after tournament |
| `auto_record_results.py` | Record results automatically | Sunday night |

---

## Pipeline Options

### Full Pipeline
```bash
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate
```

### With Specific Tournament
```bash
python3 scripts/run_pipeline.py \
    --tournament "The Genesis Invitational" \
    --use-schedule \
    --lineup \
    --calibrate
```

### Skip Data Refresh (Use Cached)
```bash
python3 scripts/run_pipeline.py --auto-weekly --skip-refresh --lineup
```

### Data Refresh Only (No Predictions)
```bash
python3 scripts/run_pipeline.py --weekly-refresh
```

---

## Dashboard Pages

| Page | Purpose |
|------|---------|
| **🏆 This Week** | Tournament overview, top picks, key stats |
| **🎯 Scoring Engine** | Detailed scoring breakdown by player |
| **🎰 Betting** | Odds comparison, value plays, props |
| **👤 Players** | Player lookup, stats, course history |
| **📊 Predictions** | Full prediction table with filters |
| **🔴 Live** | Live leaderboard during tournament |
| **📋 My Picks** | Fantasy lineup management, usage tracking |

---

## Scoring Engine Weights

Current optimized weights (as of 2026-02-16):
- **Importance:** 25% - Tournament prestige/purse
- **Course Fit:** 25% - Historical performance at venue
- **Form:** 30% - Recent results, hot hand
- **Field Strength:** 20% - Relative field difficulty

To test different weights:
```bash
python3 scripts/planning/weight_optimizer.py --backtest 5
```

---

## Fantasy League Rules (Let It Ride)

- **3 uses per player** for the entire season
- **3 players per weekly lineup**
- **30 tournaments** in the season
- Track usage carefully for majors and playoffs!

### Check Player Usage
```bash
python3 scripts/planning/usage_tracker.py --check "Scottie Scheffler"
```

### View Season Summary
```bash
python3 scripts/planning/usage_tracker.py --summary
```

---

## Troubleshooting

### Predictions file not found
```bash
# Check outputs directory
ls -la outputs/*predictions*.csv

# Re-run predictions
python3 scripts/run_pipeline.py --auto-weekly
```

### Dashboard not loading
```bash
# Clear cache
rm -rf __pycache__ scripts/__pycache__ scripts/**/__pycache__

# Restart
streamlit run dashboard.py
```

### Auto-record not finding results
```bash
# Check historical leaderboards have the tournament
grep -i "tournament name" data/historical/leaderboards_2026.csv

# Manually add if needed, then re-run
python3 scripts/planning/auto_record_results.py
```

### Odds not updating
```bash
# Check rate limits, wait a few minutes, then:
python3 scripts/scrapers/fetch_draftkings_props.py

# Or try PGA odds
python3 scripts/scrapers/fetch_pga_odds.py
```

---

## Season Calendar Reminders

| Week | Tournament | Type | Notes |
|------|------------|------|-------|
| 10 | The Masters | Major | Save elite players! |
| 15 | PGA Championship | Major | |
| 20 | U.S. Open | Major | |
| 24 | The Open Championship | Major | |
| 6 | THE PLAYERS | Signature | Near-major field |
| 28-30 | FedEx Playoffs | Playoff | Top 70/50/30 only |

---

## File Locations

```
golf_data/
├── data/
│   ├── fields/          # Tournament fields
│   ├── odds/            # Betting odds
│   ├── live/            # Live leaderboards
│   ├── historical/      # Past results
│   ├── fantasy/         # Usage tracker data
│   └── rankings/        # OWGR rankings
├── outputs/
│   └── *_predictions.csv  # Generated predictions
├── scripts/
│   ├── scrapers/        # Data fetching
│   ├── predictions/     # ML models
│   └── planning/        # Scoring & fantasy
└── dashboard.py         # Streamlit dashboard
```

---

## Quick Checklist

### Before Tournament (Tuesday/Wednesday)
- [ ] Run full pipeline: `python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate`
- [ ] Refresh odds: `python3 scripts/scrapers/fetch_draftkings_props.py`
- [ ] Review dashboard predictions
- [ ] Add picks to tracker
- [ ] Verify picks saved: `python3 scripts/planning/usage_tracker.py --lineups`

### After Tournament (Sunday/Monday)
- [ ] Record results: `python3 scripts/planning/auto_record_results.py`
- [ ] Verify results: `python3 scripts/planning/usage_tracker.py --summary`
- [ ] Check remaining uses for key players
- [ ] Plan ahead for upcoming majors
