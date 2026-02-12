# Project Cleanup and Organization Plan

## Current State Analysis

### Files to Review

**Root Directory (Cluttered)**:
- ❓ `CHALLENGE_4_QUICK_FIXES.md` - One-time implementation guide
- ❓ `CLEANUP_ANALYSIS.md` - Old analysis document
- ❓ `MERGE_SCRIPT_FIXES.md` - Old fix documentation
- ❓ `PROJECT_MAP.md` - May be outdated
- ❓ `results_scaper.py` - Old scraper script (typo in name)
- ❓ `check_scraping_progress.sh` - Utility script
- ❓ `organize_project.sh` - Old organization script
- ❓ `scrape_all_years.sh` - Batch scraping script

**Duplicate/Old Files**:
- `data/models/rf_win_model.pkl` (old)
- `data/models/rf_win_model_enhanced.pkl` (old)
- `data/models/rf_top5_model.pkl` (old)
- `data/models/model_features.pkl` (old)
- `data/models/enhanced_features_list.pkl` (old)

**Duplicate Field Files**:
- `data/fields/american_express_2026.csv` (incomplete - 120 players)
- `data/fields/american_express_2026_espn.csv` (raw with noise)
- `data/fields/american_express_2026_clean.csv` ✅ (KEEP - correct)
- `data/fields/american_express_2025_field.csv` (test data)
- `data/fields/test_field_small.csv` (test data)
- `scripts/scrapers/data/fields/*` (duplicate location)

**Duplicate Output Files**:
- `outputs/american_express_predictions.csv` (old - 2025 data)
- `outputs/american_express_2026_predictions.csv` (incomplete field)
- `outputs/american_express_2026_predictions_final.csv` ✅ (KEEP - correct)
- `outputs/THE_AMERICAN_EXPRESS_2026_PICKS.md` (superseded)
- `outputs/THE_AMERICAN_EXPRESS_2026_FINAL_PICKS.md` ✅ (KEEP - correct)

**Duplicate Processed Data**:
- `data/processed/master_training_data_2020_2024.csv` (old)
- `data/processed/full_df.csv` (intermediate)
- `data/processed/full_df_with_course_history.csv` (intermediate)

---

## Cleanup Actions

### 1. Archive Old Documentation

Move to `docs/archive/`:
- `CHALLENGE_4_QUICK_FIXES.md`
- `CLEANUP_ANALYSIS.md`
- `MERGE_SCRIPT_FIXES.md`

### 2. Remove Old Model Files

Delete superseded models:
- `data/models/rf_win_model.pkl`
- `data/models/rf_win_model_enhanced.pkl`
- `data/models/rf_top5_model.pkl`
- `data/models/model_features.pkl`
- `data/models/enhanced_features_list.pkl`

Keep only:
- `data/models/win_model_final.pkl` ✅
- `data/models/top5_model_final.pkl` ✅
- `data/models/top10_model_final.pkl` ✅
- `data/models/top20_model_final.pkl` ✅
- `data/models/feature_importance.csv` ✅

### 3. Organize Field Files

Create `data/fields/archive/` and move:
- `american_express_2025_field.csv` (historical test)
- `american_express_2026.csv` (incomplete)
- `american_express_2026_espn.csv` (raw)
- `test_field_small.csv` (test)

Keep in `data/fields/`:
- `american_express_2026_clean.csv` ✅ (current tournament)

Remove duplicate location:
- `scripts/scrapers/data/fields/*` → delete entire folder

### 4. Clean Output Files

Create `outputs/archive/` and move:
- `american_express_predictions.csv` (old)
- `american_express_2026_predictions.csv` (incomplete)
- `THE_AMERICAN_EXPRESS_2026_PICKS.md` (superseded)

Keep in `outputs/`:
- `american_express_2026_predictions_final.csv` ✅
- `THE_AMERICAN_EXPRESS_2026_FINAL_PICKS.md` ✅
- `optimal_season_plan_2026.csv` ✅
- `weekly_picks_summary_2026.csv` ✅

### 5. Clean Processed Data

Create `data/processed/archive/` and move:
- `master_training_data_2020_2024.csv` (old version)
- `full_df.csv` (intermediate)
- `full_df_with_course_history.csv` (intermediate)
- `payout_model.csv` (not used)

Keep in `data/processed/`:
- `master_training_data_2020_2025.csv` ✅ (current)
- `course_history_2026.csv` ✅

### 6. Organize Utility Scripts

Move to `scripts/utils/`:
- `check_scraping_progress.sh`
- `organize_project.sh`
- `scrape_all_years.sh`

Move to `scripts/archive/`:
- `results_scaper.py` (old, has typo, not used)

---

## Recommended Directory Structure (After Cleanup)

```
golf_data/
├── README.md                           # Main project overview
├── PREDICTION_SYSTEM_COMPLETE.md       # System documentation
├── FIELD_SCRAPER_SOLUTION.md          # Weekly workflow guide
│
├── data/
│   ├── raw/                           # Original scraped data
│   │   ├── pgatour_stat_id_catalog.csv
│   │   ├── pgatour_strokes_gained_stat_ids.csv
│   │   ├── tournament_ids.csv
│   │   ├── tournament_leaderboards.csv
│   │   ├── schedule_2026.csv
│   │   └── pgatour_schedule_2025.csv
│   │
│   ├── historical/                    # Multi-year historical data
│   │   ├── leaderboards_2020.csv
│   │   ├── leaderboards_2021.csv
│   │   ├── leaderboards_2022.csv
│   │   ├── leaderboards_2023.csv
│   │   ├── leaderboards_2024.csv
│   │   ├── leaderboards_2025.csv
│   │   ├── tournament_stats_2020.csv
│   │   ├── tournament_stats_2021.csv
│   │   ├── tournament_stats_2022.csv
│   │   ├── tournament_stats_2023.csv
│   │   ├── tournament_stats_2024.csv
│   │   ├── tournament_stats_2025.csv
│   │   └── course_history_features.csv
│   │
│   ├── processed/                     # Merged/engineered features
│   │   ├── master_training_data_2020_2025.csv  ✅
│   │   ├── course_history_2026.csv              ✅
│   │   └── archive/                   # Old versions
│   │       ├── master_training_data_2020_2024.csv
│   │       ├── full_df.csv
│   │       └── full_df_with_course_history.csv
│   │
│   ├── models/                        # Trained models
│   │   ├── win_model_final.pkl        ✅
│   │   ├── top5_model_final.pkl       ✅
│   │   ├── top10_model_final.pkl      ✅
│   │   ├── top20_model_final.pkl      ✅
│   │   └── feature_importance.csv     ✅
│   │
│   └── fields/                        # Tournament fields
│       ├── american_express_2026_clean.csv  ✅ (current)
│       └── archive/                   # Old/test fields
│           ├── american_express_2025_field.csv
│           ├── american_express_2026.csv
│           ├── american_express_2026_espn.csv
│           └── test_field_small.csv
│
├── scripts/
│   ├── scrapers/                      # Data collection
│   │   ├── multi_year_scraper.py
│   │   ├── multi_year_stats_scraper_fixed.py
│   │   ├── fetch_tournament_field.py
│   │   └── fetch_field_from_espn.py   ✅ (recommended)
│   │
│   ├── features/                      # Feature engineering
│   │   ├── merge_all_historical_data.py
│   │   ├── course_history_features.py
│   │   └── merge_and_retrain.py
│   │
│   ├── validation/                    # Model training/validation
│   │   ├── train_final_models.py
│   │   └── outputs/
│   │       └── validation_report.txt
│   │
│   ├── predictions/                   # Prediction pipeline
│   │   ├── predict_tournament.py      ✅
│   │   └── prize_distributions.py     ✅
│   │
│   ├── utils/                         # Utility scripts
│   │   ├── check_scraping_progress.sh
│   │   ├── organize_project.sh
│   │   └── scrape_all_years.sh
│   │
│   └── archive/                       # Old/unused scripts
│       └── results_scaper.py
│
├── outputs/                           # Predictions and picks
│   ├── american_express_2026_predictions_final.csv  ✅
│   ├── THE_AMERICAN_EXPRESS_2026_FINAL_PICKS.md     ✅
│   ├── optimal_season_plan_2026.csv
│   ├── weekly_picks_summary_2026.csv
│   └── archive/                       # Old predictions
│       ├── american_express_predictions.csv
│       ├── american_express_2026_predictions.csv
│       └── THE_AMERICAN_EXPRESS_2026_PICKS.md
│
└── docs/                              # Documentation
    ├── PREDICTION_PIPELINE_GUIDE.md
    ├── PREDICTION_SCRIPT_SUMMARY.md
    ├── EV_CALCULATION_EXPLAINED.md
    ├── PLAYER_ID_MATCHING_EXPLAINED.md
    ├── CHALLENGE_4_IMPLEMENTATION.md
    ├── HOW_TO_GET_TOURNAMENT_FIELDS.md
    ├── STATS_SCRAPING_GUIDE.md
    ├── HISTORICAL_DATA_GUIDE.md
    └── archive/                       # Old docs
        ├── CHALLENGE_4_QUICK_FIXES.md
        ├── CLEANUP_ANALYSIS.md
        └── MERGE_SCRIPT_FIXES.md
```

---

## Cleanup Script

See `scripts/utils/cleanup_project.sh` (to be created)

---

## Files to Keep (Production System)

### Core Scripts
- `scripts/scrapers/fetch_field_from_espn.py` - Weekly field scraping
- `scripts/predictions/predict_tournament.py` - Main prediction engine
- `scripts/predictions/prize_distributions.py` - EV calculation
- `scripts/validation/train_final_models.py` - Model retraining

### Core Data
- `data/processed/master_training_data_2020_2025.csv` - Training data
- `data/models/win_model_final.pkl` - Win probability model
- `data/models/top5_model_final.pkl` - Top-5 model
- `data/models/top10_model_final.pkl` - Top-10 model
- `data/models/top20_model_final.pkl` - Top-20 model

### Documentation
- `README.md` - Project overview
- `PREDICTION_SYSTEM_COMPLETE.md` - Complete system guide
- `FIELD_SCRAPER_SOLUTION.md` - Weekly workflow
- `docs/PREDICTION_PIPELINE_GUIDE.md` - Learning guide
- `docs/PLAYER_ID_MATCHING_EXPLAINED.md` - Technical reference

---

## Estimated Space Savings

- Old models: ~50 MB
- Duplicate fields: ~5 MB
- Duplicate processed data: ~200 MB
- Old outputs: ~10 MB
- **Total savings: ~265 MB**

---

## Next Steps After Cleanup

1. **Update README.md** with clean structure
2. **Create `.gitignore`** for future version control
3. **Pipeline enhancements**:
   - Auto-update 2025 data as season progresses
   - Weekly automation scripts
   - Performance tracking/calibration
   - Tournament result comparison

---

*Created: January 19, 2026*