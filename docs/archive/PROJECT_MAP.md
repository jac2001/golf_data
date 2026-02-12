# Project File Guide

Complete reference for every file in the project.

---

## 📓 Notebooks (`notebooks/analysis/`)

### Learning Sequence (Do in order!)

| File | Purpose | Time | Key Concepts |
|------|---------|------|--------------|
| `01_prize_money_analysis.ipynb` | Prize payout curves | 60 min | Data cleaning, EDA, feature engineering |
| `02_win_probability_model.ipynb` | Win prediction ML | 90 min | Random Forest, ROC-AUC, feature importance |
| `03_weekly_recommendation_engine.ipynb` | Weekly picks system | 75 min | Expected value, usage tracking, OOP |
| `04_season_optimizer.ipynb` | Strategic planning | 90 min | Greedy algorithms, optimization, resource allocation |
| `05_enhanced_features.ipynb` | Course history integration | 60 min | Feature engineering, model comparison |
| `PGA_STATS_EDA.ipynb` | Original exploration | - | Initial EDA (reference) |

---

## 🕷️ Scrapers (`scripts/scrapers/`)

### Active Scrapers

**`multi_year_stats_scraper_fixed.py`** ⭐ Main stats scraper
```bash
# Scrape tournament-level strokes gained stats
python scripts/scrapers/multi_year_stats_scraper_fixed.py --year 2024

Time: ~15-20 min per year
Output: historical_data/tournament_stats_YYYY.csv
Records: ~50,000 per year
```

**`per_tournament_data_scraper.py`** - Original 2025 stats scraper
```bash
# Used for current year
python scripts/scrapers/per_tournament_data_scraper.py

Output: pgatour_tournament_stats_long.csv
```

**`results_scaper.py`** - Tournament leaderboards
```bash
# Scrape finish positions and earnings
python scripts/scrapers/results_scaper.py

Output: tournament_leaderboards.csv
```

**`schedule_scraper.py`** - Tournament schedules
```bash
# Get 2026 schedule
python scripts/scrapers/schedule_scraper.py

Output: schedule_2026.csv
```

**`multi_year_scraper.py`** - Combined scraper (legacy)
- Combined leaderboards + stats
- Replaced by fixed version above

---

## ⚙️ Feature Engineering (`scripts/features/`)

**`course_history_features.py`** ⭐ Key feature generator
```bash
# Create course-specific player features
python scripts/features/course_history_features.py \
    --data-dir data/historical \
    --target-year 2026 \
    --output data/processed/course_history_2026.csv

Input: Historical leaderboards (2020-2024)
Output: Player-course history features
Features: avg_finish, times_played, cut_rate, etc.
```

**`merge_and_retrain.py`** - Model retraining
```bash
# Merge course history with current data and retrain
python scripts/features/merge_and_retrain.py

Output:
- data/processed/full_df_with_course_history.csv
- data/models/rf_win_model_enhanced.pkl
```

---

## ✅ Validation (`scripts/validation/`)

**`proper_validation.py`** ⭐ Critical for realistic assessment
```bash
# Year-based cross-validation
python scripts/validation/proper_validation.py

Train: 2020-2023
Test: 2024
Shows TRUE model performance (no overfitting)
```

---

## 📊 Data Files (`data/`)

### Raw Data (`data/raw/`)

| File | Size | Records | Description |
|------|------|---------|-------------|
| `full_df.csv` | 4MB | 3,023 | Main 2025 dataset with SG stats |
| `tournament_leaderboards.csv` | 444KB | 5,400 | 2025 results (finish, earnings) |
| `pgatour_tournament_stats_long.csv` | 38MB | 320,610 | All 2025 stats (long format) |
| `schedule_2026.csv` | 2KB | 30 | 2026 tournament schedule |
| `pgatour_stat_id_catalog.csv` | 18KB | - | Stat ID reference |

### Processed Data (`data/processed/`)

| File | Description |
|------|-------------|
| `full_df_with_course_history.csv` | Enhanced dataset with course features |
| `course_history_2026.csv` | Player-course history for 2026 predictions |
| `payout_model.csv` | Prize distribution by position & type |

### Historical Data (`data/historical/`)

| File | Size | Description |
|------|------|-------------|
| `leaderboards_2020.csv` | 279KB | 2020 tournament results |
| `leaderboards_2021.csv` | 414KB | 2021 tournament results |
| `leaderboards_2022.csv` | 403KB | 2022 tournament results |
| `leaderboards_2023.csv` | 459KB | 2023 tournament results |
| `leaderboards_2024.csv` | 384KB | 2024 tournament results |
| `tournament_stats_2023.csv` | 2.7MB | 2023 SG stats ✅ |
| `tournament_stats_2024.csv` | - | TODO: Scrape next |
| `tournament_stats_2022.csv` | - | TODO: Scrape |
| `tournament_stats_2021.csv` | - | TODO: Scrape |
| `tournament_stats_2020.csv` | - | TODO: Scrape |

### Models (`data/models/`)

| File | Description |
|------|-------------|
| `rf_win_model_enhanced.pkl` | Win prediction with course history |
| `rf_top5_model.pkl` | Top-5 finish prediction |
| `rf_win_model.pkl` | Baseline win prediction (no history) |
| `model_features.pkl` | Feature list for models |
| `enhanced_features_list.pkl` | Enhanced feature list |

---

## 📚 Documentation (`docs/`)

**`HISTORICAL_DATA_GUIDE.md`**
- Complete guide to scraping 2020-2024 data
- Explains overfitting issue (0.98 → 0.57 AUC)
- Step-by-step scraping instructions

**`STATS_SCRAPING_GUIDE.md`**
- Detailed guide for stats scraper
- Progress monitoring
- Troubleshooting
- Time estimates

---

## 📈 Outputs (`outputs/`)

**`optimal_season_plan_2026.csv`**
- Greedy optimizer results
- Weekly picks for all 30 tournaments
- Usage allocation strategy

**`weekly_picks_summary_2026.csv`**
- Human-readable weekly picks
- Tournament names and dates

**`usage_tracker.json`**
- Current usage counts by player
- Tracks 3-use limit

---

## 🔧 Helper Files

**Web Scraping Library**
- `web_scraping.py` - Shared scraping utilities

**Old/Reference Files**
- `pgatour_player_event_history.csv` - Player career stats
- `pgatour_players.csv` - Player information
- `pgatour_strokes_gained_long.csv` - Historical SG data

---

## 🗂️ File Organization Summary

```
📁 Total: ~70MB
   ├── 📓 Notebooks: 1.4MB (6 files)
   ├── 🕷️ Scripts: 92KB (10 files)
   ├── 📊 Data: 69MB
   │   ├── Raw: 42MB
   │   ├── Historical: 23MB
   │   ├── Processed: 4MB
   │   └── Models: 1MB
   ├── 📚 Docs: 16KB (3 files)
   └── 📈 Outputs: 4KB (3 files)
```

---

## 🎯 Common Tasks

### Task: Get Weekly Picks
1. Open `notebooks/analysis/03_weekly_recommendation_engine.ipynb`
2. Update field data
3. Run cells
4. Get top 3 + alternate

### Task: Scrape New Year
```bash
cd golf_data
python scripts/scrapers/multi_year_stats_scraper_fixed.py --year 2024
```

### Task: Update Models
```bash
python scripts/features/course_history_features.py --target-year 2026
python scripts/features/merge_and_retrain.py
```

### Task: Validate Performance
```bash
python scripts/validation/proper_validation.py
```

---

## 📋 Checklist: Complete System

### Data Collection ✅
- [x] 2025 current data
- [x] Historical leaderboards (2020-2024)
- [x] 2023 tournament stats
- [ ] 2024 tournament stats (in progress)
- [ ] 2022 tournament stats
- [ ] 2021 tournament stats
- [ ] 2020 tournament stats

### Feature Engineering ✅
- [x] Prize money model
- [x] Course history features
- [x] Rolling averages
- [x] Strokes gained metrics

### Modeling ✅
- [x] Win prediction model
- [x] Top-5 prediction model
- [x] Expected value calculator
- [x] Usage tracker

### Optimization ✅
- [x] Weekly recommendation engine
- [x] Season-long optimizer
- [x] What-if scenario capability

### Validation ⚠️
- [x] Proper year-based validation
- [ ] Full 5-year model training
- [ ] 2026 season predictions

---

## 🚀 Next Actions

1. **Scrape remaining years**: 2024, 2022, 2021, 2020
2. **Merge complete dataset**: All years + stats + course history
3. **Retrain models**: Use full 5-year data
4. **Final validation**: Test on 2025 held-out data
5. **Deploy for 2026**: Ready for weekly picks!

---

*Last updated: January 2026*