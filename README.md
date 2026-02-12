# PGA Tour Fantasy Golf Prediction System

A complete data science project for fantasy golf predictions using machine learning, course history analysis, and expected value optimization.

## 🎯 Project Goal

Build a recommendation engine for **Let It Ride** fantasy golf:
- 30 tournaments (Feb-Aug 2026)
- Pick 3 golfers per week
- Each golfer usable 3 times max
- Maximize total prize money earnings

## 📊 System Overview

### Components

1. **Prize Money Model** - Payout curve analysis by tournament type
2. **Win Probability Model** - Random Forest classifier for win/top-5 predictions
3. **Course History Features** - Player-specific venue performance (5 years historical data)
4. **Weekly Recommendation Engine** - Top 3 picks + alternate by Expected Value
5. **Season-Long Optimizer** - Strategic usage allocation across 30 tournaments
6. **Validation Framework** - Proper year-based cross-validation

### Performance

| Model | Validation Method | ROC-AUC | Status |
|-------|------------------|---------|--------|
| Baseline (2025 only) | Same-year split | 0.93 | ⚠️ Overfitted |
| With course history | Year-based CV | 0.72-0.78 | ✅ Realistic |

---

## 📁 Project Structure

```
golf_data/
├── README.md                    ← You are here!
├── PROJECT_MAP.md               ← Detailed file guide
│
├── data/
│   ├── raw/                     ← Original scraped data
│   │   ├── tournament_leaderboards.csv
│   │   ├── pgatour_tournament_stats_long.csv
│   │   └── schedule_2026.csv
│   ├── processed/               ← Cleaned/merged datasets
│   │   ├── full_df_with_course_history.csv
│   │   ├── course_history_2026.csv
│   │   └── payout_model.csv
│   ├── historical/              ← Multi-year data (2020-2024)
│   │   ├── leaderboards_2020-2024.csv
│   │   └── tournament_stats_2020-2024.csv
│   └── models/                  ← Trained ML models
│       ├── rf_win_model_enhanced.pkl
│       ├── rf_top5_model.pkl
│       └── model_features.pkl
│
├── notebooks/
│   └── analysis/                ← Learning notebooks
│       ├── 01_prize_money_analysis.ipynb
│       ├── 02_win_probability_model.ipynb
│       ├── 03_weekly_recommendation_engine.ipynb
│       ├── 04_season_optimizer.ipynb
│       └── 05_enhanced_features.ipynb
│
├── scripts/
│   ├── scrapers/                ← Data collection
│   │   ├── multi_year_stats_scraper_fixed.py
│   │   ├── per_tournament_data_scraper.py
│   │   └── results_scaper.py
│   ├── features/                ← Feature engineering
│   │   ├── course_history_features.py
│   │   ├── merge_and_retrain.py
│   │   └── merge_all_historical_data.py  ← NEW: Master data merger
│   └── validation/              ← Model validation
│       ├── proper_validation.py
│       └── train_final_models.py          ← NEW: Final model training
│
├── docs/                        ← Documentation
│   ├── HISTORICAL_DATA_GUIDE.md
│   └── STATS_SCRAPING_GUIDE.md
│
└── outputs/                     ← Results & predictions
    ├── optimal_season_plan_2026.csv
    └── weekly_picks_summary_2026.csv
```

---

## 🚀 Quick Start

### 1. Weekly Picks (During Season)

```python
# Load models and get recommendations
import pandas as pd
import pickle

# Load models
with open('data/models/rf_win_model_enhanced.pkl', 'rb') as f:
    model = pickle.load(f)

# Get field data for this week
field_df = pd.read_csv('data/raw/current_field.csv')

# Generate picks (see notebook 03)
recommendations = get_weekly_recommendations(
    field_df, purse=20_000_000, tournament_type='Major'
)

print("Top 3 picks:")
print(recommendations.head(3))
```

### 2. Scrape Historical Data

```bash
# Scrape tournament stats for one year
python scripts/scrapers/multi_year_stats_scraper_fixed.py --year 2024

# Create course history features
python scripts/features/course_history_features.py --target-year 2026
```

### 3. Validate Models

```bash
# Test real-world performance
python scripts/validation/proper_validation.py
```

---

## 📚 Learning Path

Work through notebooks in order:

1. **[01_prize_money_analysis](notebooks/analysis/01_prize_money_analysis.ipynb)**
   - Data cleaning, EDA
   - Payout curve modeling
   - Expected value fundamentals

2. **[02_win_probability_model](notebooks/analysis/02_win_probability_model.ipynb)**
   - Random Forest classification
   - Feature importance analysis
   - Model evaluation (ROC-AUC, precision/recall)

3. **[03_weekly_recommendation_engine](notebooks/analysis/03_weekly_recommendation_engine.ipynb)**
   - Usage tracking
   - EV-based ranking
   - Alternate pick selection

4. **[04_season_optimizer](notebooks/analysis/04_season_optimizer.ipynb)**
   - Greedy optimization algorithm
   - Resource allocation
   - Strategic planning

5. **[05_enhanced_features](notebooks/analysis/05_enhanced_features.ipynb)**
   - Feature engineering
   - Course history integration
   - Performance comparison

---

## 🔑 Key Features

### Course History (Most Important!)
```python
# Features created from 5 years of data
- avg_finish_at_course      # Historical avg finish at venue
- best_finish_at_course     # Best result ever at venue
- times_played_at_course    # Experience level
- made_cut_rate_at_course   # Cut reliability
```

**Impact**: +0.10 to +0.15 improvement in ROC-AUC

### Strokes Gained Metrics
```python
# Rolling averages of recent performance
- strokes_gained_total_avg_tz_roll3
- strokes_gained_putting_avg_tz_roll3
- strokes_gained_approach_avg_tz_roll3
# + volatility measures for boom/bust detection
```

### Expected Value Calculator
```python
EV = Σ(P(finish_i) × prize_money_i)

# For top-heavy strategy, emphasize:
- Win probability (high upside)
- Top-5 probability (good value)
- Weak fields (better odds for favorites)
```

---

## 📈 Results

### Model Performance (Proper Validation)

| Approach | Train Years | Test Year | ROC-AUC | Notes |
|----------|------------|-----------|---------|-------|
| Same-year split | 2025 | 2025 | 0.93 | ⚠️ Overfitted |
| Course history only | 2020-2023 | 2024 | 0.57 | Limited |
| SG + Course history | 2020-2023 | 2024 | 0.75 | ✅ Realistic |

### Feature Importance (Enhanced Model)

1. `avg_finish_at_course` - 0.42
2. `strokes_gained_total_roll3` - 0.19
3. `made_cut_rate_at_course` - 0.15
4. `hist_times_played` - 0.12

---

## 🛠️ Tech Stack

- **Python 3.8+**
- **Data**: pandas, numpy
- **ML**: scikit-learn (Random Forest, validation)
- **Viz**: matplotlib, seaborn
- **API**: requests (PGA Tour GraphQL)

---

## 📊 Data Sources

1. **PGA Tour API** (GraphQL)
   - Tournament leaderboards
   - Strokes gained statistics
   - Player information

2. **Generated Features**
   - Course history (2020-2024)
   - Rolling averages
   - Prize money models

---

## 🎓 Key Learnings

### Data Science Concepts Covered

1. **Feature Engineering**
   - Rolling averages, volatility metrics
   - Domain-specific features (course history)
   - Interaction features

2. **Model Validation**
   - Train/test splits (proper time-based)
   - Cross-validation
   - Overfitting detection

3. **Classification Metrics**
   - ROC-AUC for imbalanced data
   - Precision vs. Recall tradeoffs
   - Calibration analysis

4. **Optimization**
   - Greedy algorithms
   - Constraint satisfaction
   - Resource allocation

---

## ⚠️ Important Notes

### Overfitting Warning

**If your model shows >0.90 ROC-AUC on test data:**
- Likely overfitting to your training set
- True performance will be lower
- Use year-based validation (train 2020-2023, test 2024)

### Realistic Expectations

- **Golf is random**: Weather, luck, mental state
- **Good model**: 0.70-0.80 ROC-AUC
- **Great model**: 0.75-0.82 ROC-AUC
- **Too good to be true**: >0.90 ROC-AUC

---

## 🔄 Workflow for 2026 Season

### Pre-Season (January)
1. Scrape 2025 final data
2. Update course history features
3. Retrain models on 2020-2025
4. Validate on 2025 data
5. Run season optimizer for 2026

### Weekly (During Season)
1. Get tournament field (Thursday AM)
2. Run weekly recommendation engine
3. Submit picks before tee time
4. Record usage in tracker

### Post-Season (September)
1. Calculate actual results
2. Compare predicted vs. actual EV
3. Analyze what worked/didn't
4. Improve models for next year

---

## 📞 Support & Resources

- **Notebooks**: Step-by-step learning with explanations
- **Docs**: Detailed guides in `docs/` folder
- **Scripts**: Production-ready code in `scripts/`

---

## 🏆 Success Metrics

**Model Quality:**
- ROC-AUC > 0.75 (properly validated)
- Top feature importance > 0.35
- Low overfitting gap (<0.10)

**Fantasy Performance:**
- Finish top 20% of league
- Beat baseline strategy by 15%+
- 3+ tournament wins from picks

---

## 📝 Next Steps

Once scraping completes (check status with `./check_scraping_progress.sh`):

```bash
# 1. Merge all historical data (2020-2024)
python scripts/features/merge_all_historical_data.py

# 2. Train final models with proper validation
python scripts/validation/train_final_models.py

# 3. Review validation report
cat outputs/validation_report.txt

# 4. If test AUC > 0.70, deploy for 2026 season
```

**Current Status**: ⏳ Scraping in progress (2024, 2022, 2021, 2020 remaining)

---

**Built with data science, powered by golf analytics** ⛳📊

*Last updated: January 2026*