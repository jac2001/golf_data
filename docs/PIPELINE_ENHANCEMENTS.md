# Pipeline Enhancements Roadmap

## Current System Status ✅

Your prediction system is production-ready with:
- ✅ Multi-year historical data (2020-2025)
- ✅ 4 trained models (Win/Top5/Top10/Top20)
- ✅ Complete prediction pipeline
- ✅ Field scraping (ESPN + PGA Tour)
- ✅ Expected value calculation
- ✅ Weekly workflow documented

**Performance**: 0.886-0.970 ROC-AUC (exceptional)

---

## Phase 1: Weekly Automation (Priority: HIGH)

### 1.1 Automated Weekly Workflow Script

**Goal**: Run predictions with a single command

**Implementation**: `scripts/predictions/weekly_predictions.sh`

```bash
# Usage: ./weekly_predictions.sh --tournament-id 401811929 --name "American Express"
```

**Features**:
- Auto-fetch field from ESPN
- Clean and match player IDs
- Run predictions with optimal parameters
- Generate picks markdown
- Save to outputs/[tournament]_[year]_predictions.csv

**Estimated effort**: 1-2 hours

---

### 1.2 Post-Tournament Results Tracker

**Goal**: Compare predictions to actual results

**Implementation**: `scripts/validation/compare_predictions_to_results.py`

```python
# Compare predictions to actual tournament results
# Calculate calibration metrics:
# - Did 6% win probs win 6% of the time?
# - Brier score for probability accuracy
# - Expected picks vs actual picks performance
```

**Output**: `outputs/calibration/[tournament]_results_comparison.csv`

**Estimated effort**: 2-3 hours

---

### 1.3 Results Scraper (Update for 2026)

**Goal**: Automatically scrape tournament results each week

**Implementation**: `scripts/scrapers/scrape_weekly_results.py`

```python
# Scrape completed tournament:
# - Final leaderboard
# - Strokes gained stats
# - Append to data/historical/leaderboards_2026.csv
# - Append to data/historical/tournament_stats_2026.csv
```

**Estimated effort**: 2-3 hours

---

## Phase 2: Model Improvements (Priority: MEDIUM)

### 2.1 Monthly Model Retraining

**Goal**: Keep models updated with latest data

**Implementation**: `scripts/validation/retrain_monthly.sh`

```bash
# Run monthly (after ~4 new tournaments)
# 1. Merge new 2026 data with historical
# 2. Retrain all 4 models
# 3. Validate on holdout set
# 4. Compare to previous model performance
# 5. Update if improved
```

**Trigger**: Manual or cron job (1st of each month)

**Estimated effort**: 1 hour (leverages existing scripts)

---

### 2.2 Weather Features (Optional Enhancement)

**Goal**: Add weather data to predictions

**Data sources**:
- Weather.com API
- OpenWeather API
- PGA Tour weather data

**Features to add**:
- Wind speed (mph)
- Wind direction vs hole layout
- Rain probability
- Temperature

**Expected improvement**: 2-5% better predictions in windy conditions

**Estimated effort**: 4-6 hours

---

### 2.3 Form Momentum Features

**Goal**: Capture hot/cold streaks better

**New features**:
- Recent top-10 streak count
- Recent wins in last 10 starts
- Recent missed cuts
- Trend in SG stats (improving vs declining)

**Expected improvement**: 3-5% better win probability predictions

**Estimated effort**: 3-4 hours

---

## Phase 3: Performance Tracking (Priority: HIGH)

### 3.1 Season-Long Calibration Dashboard

**Goal**: Track how well your predictions match reality

**Metrics to track**:
- **Calibration**: Do 10% probabilities happen 10% of the time?
- **Brier Score**: Accuracy of probability predictions
- **Top-N Hit Rate**: % of your top-10 picks that make top-20
- **EV Accuracy**: Predicted EV vs actual winnings
- **League Ranking**: Your standing vs league average

**Implementation**: `scripts/validation/season_calibration_report.py`

**Output**: HTML dashboard or markdown report

**Estimated effort**: 3-4 hours

---

### 3.2 Weekly Picks Performance Log

**Goal**: Track your fantasy league performance

**Implementation**: `outputs/season_log.csv`

```csv
week,tournament,your_picks,actual_results,points_earned,league_rank,notes
1,American Express,"Scheffler,Brennan,Griffin","Scheffler(1),Griffin(18),Brennan(45)",150,3/50,"Scheffler won!"
2,Farmers Insurance,"...",85,5/50,"Weather affected picks"
```

**Update**: Manual entry after each tournament

**Estimated effort**: 15 minutes per week

---

## Phase 4: Advanced Features (Priority: LOW)

### 4.1 Course Fit Analysis

**Goal**: Better understand player-course compatibility

**Features**:
- Par-5 scoring vs course par-5 difficulty
- Driving distance vs course length
- Fairway accuracy vs narrow fairways
- Green size vs approach dispersion

**Expected improvement**: 5-8% on specific course types

**Estimated effort**: 8-10 hours

---

### 4.2 Ensemble Model

**Goal**: Combine multiple algorithms for better predictions

**Approach**:
- Current: Random Forest only
- Add: XGBoost, LightGBM, Neural Network
- Ensemble: Weighted average of predictions

**Expected improvement**: 3-5% across all models

**Estimated effort**: 10-12 hours

---

### 4.3 Optimal Lineup Selector

**Goal**: Maximize EV given league constraints

**Features**:
- Salary cap optimization (if league uses one)
- Max players per tournament
- Correlation-aware picks (avoid correlated players)
- Risk tolerance adjustment

**Implementation**: `scripts/predictions/optimize_lineup.py`

**Estimated effort**: 6-8 hours

---

## Phase 5: Data Quality (Priority: MEDIUM)

### 5.1 Data Validation Pipeline

**Goal**: Catch data quality issues early

**Checks**:
- Missing SG stats for key players
- Tournament IDs changed
- Field size anomalies
- Duplicate player entries
- Course history mismatches

**Implementation**: `scripts/validation/data_quality_check.py`

**Run**: Before each prediction

**Estimated effort**: 2-3 hours

---

### 5.2 Player Database Maintenance

**Goal**: Keep player IDs and names up-to-date

**Tasks**:
- Handle name changes (marriage, etc.)
- Track rookies (no historical data)
- LIV Golf players returning to PGA
- International name variations

**Implementation**: `data/player_database.csv` with aliases

**Estimated effort**: 1 hour setup, 15 min/month maintenance

---

## Immediate Next Steps (This Week)

### Recommended Priority Order:

1. **Run Cleanup Script** ✅
   ```bash
   ./scripts/utils/cleanup_project.sh
   ```

2. **Create Weekly Automation Script** (Phase 1.1)
   - Automates field scraping + predictions
   - Saves 15-20 minutes per week

3. **Set up Performance Tracking** (Phase 3.2)
   - Create `outputs/season_log.csv`
   - Track your picks starting this week

4. **Plan Post-Tournament Analysis** (Phase 1.2)
   - After American Express finishes, compare predictions to results

---

## Long-Term Vision (6-12 Months)

### Goal: Fully Automated Fantasy Golf System

**Weekly workflow becomes**:
1. Monday: Auto-scrape last week's results → update training data
2. Tuesday: Auto-retrain models (if enough new data)
3. Wednesday: Auto-scrape this week's field → run predictions
4. Thursday: Review predictions, make picks
5. Sunday: Track results, update log

**Your time investment**: 15-30 minutes per week (down from 60-90 minutes)

**System improvements over time**:
- Models improve with more data
- Calibration metrics guide adjustments
- You learn which predictions to trust most

---

## Success Metrics (End of 2026 Season)

**Model Performance**:
- ✅ Maintain 0.80+ ROC-AUC on 2026 data (test set)
- ✅ Calibration error < 5% (predictions match reality)
- ✅ Brier score < 0.20 (industry standard for good probability predictions)

**Fantasy League Performance**:
- ✅ Finish top 20% of league (better than 80% of competitors)
- ✅ Beat league average by 15%+ points
- ✅ Have 3+ tournament winners picked correctly

**Efficiency**:
- ✅ Weekly workflow < 30 minutes
- ✅ Automated data updates
- ✅ Minimal manual intervention needed

---

## Questions to Consider

1. **How much time do you want to invest weekly?**
   - 15 min: Automated workflow only
   - 30 min: + review and adjust picks
   - 60 min: + track results and analyze

2. **What's your league format?**
   - Pick 3 players? → Focus on EV optimization
   - Salary cap? → Need optimizer
   - Pick top 10? → Focus on consistency

3. **What's your risk tolerance?**
   - Conservative: Pick favorites (Scheffler, Cantlay)
   - Balanced: Mix favorites + value plays (current approach)
   - Aggressive: Fade chalk, pick longshots

4. **Do you want to track other data?**
   - Betting odds for comparison
   - DFS (DraftKings) pricing
   - Expert picks consensus

---

## Files to Create (By Phase)

**Phase 1**:
- `scripts/predictions/weekly_predictions.sh`
- `scripts/validation/compare_predictions_to_results.py`
- `scripts/scrapers/scrape_weekly_results.py`

**Phase 2**:
- `scripts/validation/retrain_monthly.sh`
- `scripts/features/weather_features.py` (optional)
- `scripts/features/momentum_features.py` (optional)

**Phase 3**:
- `scripts/validation/season_calibration_report.py`
- `outputs/season_log.csv`

**Phase 4**:
- `scripts/predictions/optimize_lineup.py`
- `scripts/models/ensemble_model.py`

**Phase 5**:
- `scripts/validation/data_quality_check.py`
- `data/player_database.csv`

---

## Ready to Start?

Let me know which enhancement you'd like to tackle first! Recommended:

1. **Cleanup** (5 minutes) → Clean project structure
2. **Weekly automation** (1-2 hours) → Save time every week
3. **Performance tracking** (30 minutes) → Learn what works

---

*Created: January 19, 2026*
*Current System: Production Ready ✅*
*Next Milestone: Automated Weekly Workflow*