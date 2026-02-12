# Additional Features - Before Sportsbook Odds

## Priority Features to Add

Based on your league's **3 uses per player** rule, here's what to build first:

---

## 🎯 Priority 1: Season Strategy Tools (CRITICAL)

### 1A. Player Usage Tracker (1 hour) ⭐⭐⭐
**Why**: Track who you've used and who to save
**Impact**: Essential for 3-use rule
**Difficulty**: Easy

**Features**:
- CSV tracker: `player_name, uses_remaining, weeks_used`
- Simple update script
- Dashboard integration

**Example**:
```csv
player_name,uses_remaining,weeks_used
Scottie Scheffler,2,"1,5"
Jon Rahm,3,""
Patrick Cantlay,3,""
```

---

### 1B. Season Planner Dashboard (2 hours) ⭐⭐⭐
**Why**: Visualize optimal allocation
**Impact**: High - strategic advantage
**Difficulty**: Medium

**Features**:
- View all 40 tournaments
- See recommended player allocations
- Track uses remaining
- Calculate opportunity cost

---

### 1C. Weekly Opportunity Cost Calculator (2 hours) ⭐⭐
**Why**: Know if you should use elite player NOW or LATER
**Impact**: High - prevents wasting elite players
**Difficulty**: Medium

**Formula**:
```
Opportunity Cost = EV(use now) - Max(EV at remaining tournaments)
```

**Output**:
```
Use Scheffler this week?
- EV this week: $868K (American Express)
- Best remaining EV: $1.2M (Masters)
- Opportunity cost: -$332K
→ SAVE for Masters
```

---

## 📊 Priority 2: Advanced Statistics (4-6 hours total)

### 2A. Weather Data Integration (2 hours) ⭐⭐
**Why**: Wind significantly affects scores
**Impact**: Medium-High (2-5% improvement on windy days)
**Difficulty**: Medium

**Data Source**: OpenWeather API (free tier)
**Features to add**:
- `wind_speed` (mph)
- `wind_direction` vs hole layout
- `rain_probability`
- `temperature`

**Implementation**:
```python
# Add to predict_tournament.py
def get_weather_forecast(venue, tournament_date):
    """Fetch 4-day weather forecast"""
    api_key = os.getenv('OPENWEATHER_API_KEY')
    # Get venue coordinates
    # Fetch forecast
    # Return wind/rain/temp
```

**Expected improvement**: 3-5% better predictions in windy conditions

---

### 2B. Advanced Strokes Gained Stats (2 hours) ⭐
**Why**: More granular skill assessment
**Impact**: Medium (2-3% improvement)
**Difficulty**: Easy

**Stats to add** (already in PGA Tour data):
- `sg_arg` - Around the green
- `sg_scrambling` - Recovery shots
- `par3_scoring` - Par 3 performance
- `par4_scoring` - Par 4 performance
- `par5_scoring` - Par 5 performance

**PGA Tour Stat IDs**:
```python
ADDITIONAL_STATS = {
    2181: 'sg_arg',         # Around the green
    2216: 'scrambling',      # Scrambling %
    2427: 'par3_avg',       # Par 3 scoring
    2428: 'par4_avg',       # Par 4 scoring
    2429: 'par5_avg'        # Par 5 scoring
}
```

**Add to scraper**: `multi_year_stats_scraper_fixed.py`

---

### 2C. Form Momentum Features (2 hours) ⭐⭐
**Why**: Capture hot/cold streaks
**Impact**: Medium (3-5% improvement for win probability)
**Difficulty**: Easy

**New features**:
```python
def calculate_momentum(player_id, recent_tournaments):
    """Calculate form momentum"""
    return {
        'recent_top10_streak': count_consecutive_top10s(),
        'recent_wins': wins_in_last_10_starts(),
        'recent_mcs': missed_cuts_in_last_10(),
        'sg_trend': linear_regression_slope(sg_total),  # Improving?
        'form_score': weighted_recent_results()
    }
```

**Example**:
```
Scottie Scheffler:
- Recent top-10 streak: 4
- Recent wins: 2 in last 10
- SG trend: +0.15 (improving!)
- Form score: 9.2/10
```

---

### 2D. Course Fit Analysis (3-4 hours) ⭐⭐
**Why**: Some players better suited to certain course types
**Impact**: Medium-High (5-8% on specific course types)
**Difficulty**: Medium-Hard

**Features**:
- **Driving distance** vs course length
  ```python
  if player_avg_distance > course_avg + 10:
      advantage = 'long_hitter_advantage'
  ```

- **Accuracy** vs fairway width
  ```python
  if narrow_fairways and player_accuracy > 65%:
      advantage = 'accuracy_advantage'
  ```

- **Par 5 scoring** vs course par 5 difficulty
  ```python
  if player_par5_avg < 4.6 and course_has_reachable_par5s:
      advantage = 'par5_birdie_advantage'
  ```

**Requires**:
- Course database (length, fairway width, par 5 reachability)
- Player skills database (distance, accuracy, par 5 scoring)

---

## 🧠 Priority 3: Model Improvements (6-8 hours)

### 3A. Ensemble Model (6 hours) ⭐
**Why**: Combine multiple algorithms
**Impact**: Medium (3-5% improvement)
**Difficulty**: Hard

**Current**: Random Forest only
**Add**: XGBoost, LightGBM, Neural Network

**Ensemble approach**:
```python
predictions = (
    0.4 * random_forest_pred +
    0.3 * xgboost_pred +
    0.2 * lightgbm_pred +
    0.1 * neural_net_pred
)
```

**Expected improvement**: 0.88 → 0.91 ROC-AUC

---

### 3B. Top-20 Model Training (2 hours) ⭐
**Why**: Currently estimating top-20 from top-10
**Impact**: Medium (better EV accuracy)
**Difficulty**: Easy

**Current approach**:
```python
top20_prob_est = top10_prob + (top10_prob - top5_prob) * 1.2
```

**Better approach**: Train dedicated top-20 model
```python
top20_model = RandomForestClassifier()
top20_model.fit(X_train, y_train['top20'])
```

---

## 🔍 Priority 4: Data Quality & Validation (4-5 hours)

### 4A. Data Quality Checks (2 hours) ⭐⭐
**Why**: Catch errors before predictions
**Impact**: High (prevent bad predictions)
**Difficulty**: Medium

**Checks**:
```python
def validate_data_quality(field_df, stats_df, master_df):
    """Run pre-prediction validation"""

    issues = []

    # Check 1: Field size reasonable?
    if len(field_df) < 100 or len(field_df) > 200:
        issues.append(f"Unusual field size: {len(field_df)}")

    # Check 2: Key players missing SG stats?
    top_players = ['Scheffler', 'Rahm', 'McIlroy']
    for player in top_players:
        if player in field and no_sg_stats(player):
            issues.append(f"Missing SG stats for {player}")

    # Check 3: Tournament name matches historical?
    if venue_clean not in master_df['venue_clean'].values:
        issues.append(f"New venue: {venue_clean}")

    # Check 4: Duplicate player IDs?
    if field_df['player_id'].duplicated().any():
        issues.append("Duplicate player IDs in field")

    return issues
```

---

### 4B. Model Calibration Tracker (2 hours) ⭐
**Why**: Track if predictions match reality
**Impact**: Medium (improves model over time)
**Difficulty**: Medium

**After each tournament**:
```python
def calculate_calibration(predictions, actuals):
    """
    Check if 10% predictions happen 10% of time

    Calibration plot:
    - X-axis: Predicted probability bins (0-10%, 10-20%, ...)
    - Y-axis: Actual frequency in that bin
    - Perfect calibration: y = x line
    """

    bins = [0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0]

    for i in range(len(bins)-1):
        bin_preds = predictions[(predictions >= bins[i]) & (predictions < bins[i+1])]
        bin_actuals = actuals[(predictions >= bins[i]) & (predictions < bins[i+1])]

        print(f"{bins[i]*100:.0f}-{bins[i+1]*100:.0f}%: "
              f"Predicted {bin_preds.mean()*100:.1f}%, "
              f"Actual {bin_actuals.mean()*100:.1f}%")
```

---

### 4C. Feature Importance Tracking (1 hour) ⭐
**Why**: Understand what drives predictions
**Impact**: Low (informational)
**Difficulty**: Easy

**After retraining**:
```python
# Already have this in training script, just visualize better
importance = pd.DataFrame({
    'feature': feature_names,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

# Add to dashboard
```

---

## 🎨 Priority 5: Dashboard Enhancements (3-4 hours)

### 5A. Season Planner Page (2 hours) ⭐⭐⭐
**Why**: Critical for 3-use strategy
**Impact**: High
**Difficulty**: Medium

**Features**:
- Calendar view of all tournaments
- Player allocation heatmap
- Uses remaining counter
- Optimal allocation suggestions

---

### 5B. Comparison Tab (1 hour) ⭐
**Why**: Compare multiple players side-by-side
**Impact**: Medium
**Difficulty**: Easy

**Features**:
- Select 3-5 players
- Compare stats, probs, EV
- Show differentiators
- Recommend best pick

---

### 5C. Historical Performance Tab (1 hour) ⭐
**Why**: Learn from past predictions
**Impact**: Medium
**Difficulty**: Easy

**Features**:
- Past predictions vs actuals
- Win rate by confidence level
- Calibration plots
- Best/worst predictions

---

## Implementation Timeline

### Week 1: Season Strategy (CRITICAL for 3-use rule)
**Total: 5-6 hours**
- [ ] Player usage tracker (1h)
- [ ] Opportunity cost calculator (2h)
- [ ] Season planner dashboard page (2h)
- [ ] Test with American Express (30min)

### Week 2: Advanced Stats
**Total: 6-8 hours**
- [ ] Form momentum features (2h)
- [ ] Advanced SG stats (2h)
- [ ] Weather data (2h)
- [ ] Retrain models (2h)

### Week 3: Model Improvements
**Total: 8-10 hours**
- [ ] Top-20 model training (2h)
- [ ] Data quality checks (2h)
- [ ] Calibration tracking (2h)
- [ ] Ensemble model (4h) - optional

### Week 4: Course Fit & Polish
**Total: 5-7 hours**
- [ ] Course fit analysis (4h)
- [ ] Dashboard enhancements (2h)
- [ ] Documentation (1h)

---

## Recommended Priority Order

### This Week (Before American Express)
1. **Player Usage Tracker** ⭐⭐⭐
   - Need immediately for 3-use rule
   - Track Scheffler, Rahm, etc.

2. **Opportunity Cost Calculator** ⭐⭐⭐
   - Decide: use Scheffler now or save?
   - Critical strategic decision

### Next 2 Weeks (After American Express)
3. **Form Momentum Features** ⭐⭐
   - Easy to add
   - High impact

4. **Advanced SG Stats** ⭐⭐
   - Data already available
   - Quick implementation

5. **Weather Integration** ⭐⭐
   - Medium effort
   - Good ROI

### Month 2
6. **Season Planner Dashboard** ⭐⭐⭐
7. **Course Fit Analysis** ⭐⭐
8. **Ensemble Models** ⭐

---

## Quick Wins (< 2 hours each)

These are easy adds with good impact:

1. ✅ **Player usage tracker** (1h)
2. ✅ **Advanced SG stats** (2h) - data exists
3. ✅ **Top-20 model** (2h) - just train another RF
4. ✅ **Form momentum** (2h) - simple calculations
5. ✅ **Dashboard comparison tab** (1h)

---

## After These Features → Sportsbook Odds

Once you have:
- ✅ Usage tracking (know who to save)
- ✅ Advanced stats (better predictions)
- ✅ Form momentum (capture streaks)
- ✅ Season strategy (optimal allocation)

**Then add sportsbook odds** for:
- Market validation
- Value detection
- Additional features

---

## Questions to Decide

**1. Which features do you want first?**
- Season strategy tools (usage tracking)?
- Advanced stats (weather, form momentum)?
- Model improvements (ensemble, top-20)?

**2. How much time per week?**
- 1-2 hours? → Focus on quick wins
- 5+ hours? → Build season optimizer

**3. What's most valuable to your league?**
- Optimal player allocation?
- Better predictions?
- Both?

---

**My recommendation: Start with Player Usage Tracker (1 hour) since American Express is this week and you need to track elite player usage immediately!**

Want me to build the usage tracker now?

*Created: January 19, 2026*
*Status: Feature Roadmap*
*Next: Build player usage tracker for 3-use rule*