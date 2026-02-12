# Project Cleanup Analysis

Analysis of which files are actively used vs. obsolete in the golf prediction pipeline.

---

## ✅ **ACTIVELY USED FILES**

### Data Files (Keep)

**Historical Data (Critical for final pipeline):**
- `data/historical/leaderboards_2020.csv` - 3,341 records
- `data/historical/leaderboards_2021.csv` - 4,949 records
- `data/historical/leaderboards_2022.csv` - 4,858 records
- `data/historical/leaderboards_2023.csv` - 5,557 records
- `data/historical/leaderboards_2024.csv` - 4,613 records
- `data/historical/tournament_stats_2023.csv` - 48,944 records
- `data/historical/tournament_stats_2024.csv` - (scraping in progress)
- `data/historical/tournament_stats_2022.csv` - (scraping in progress)
- `data/historical/tournament_stats_2021.csv` - (scraping in progress)
- `data/historical/tournament_stats_2020.csv` - (scraping in progress)

**Production Data (Used by final pipeline):**
- `data/raw/schedule_2026.csv` - Used by season optimizer
- Will create: `data/processed/master_training_data_2020_2024.csv` - Final merged dataset

### Scripts (Keep)

**Active Scrapers:**
- `scripts/scrapers/multi_year_stats_scraper_fixed.py` ✅ Currently in use (scraping 2020-2024)

**Active Feature Engineering:**
- `scripts/features/merge_all_historical_data.py` ✅ Next step after scraping
- `scripts/features/course_history_features.py` ✅ Used by merge script

**Active Validation:**
- `scripts/validation/train_final_models.py` ✅ Final model training pipeline

### Notebooks (Keep - Learning Path)

**Educational/Tutorial Notebooks:**
- `notebooks/analysis/01_prize_money_analysis.ipynb` - Learning notebook
- `notebooks/analysis/02_win_probability_model.ipynb` - Learning notebook
- `notebooks/analysis/03_weekly_recommendation_engine.ipynb` - Learning notebook
- `notebooks/analysis/04_season_optimizer.ipynb` - Learning notebook
- `notebooks/analysis/05_enhanced_features.ipynb` - Learning notebook

### Models (Keep)

**Will be replaced by final models, but keep for now:**
- `data/models/rf_win_model.pkl`
- `data/models/rf_top5_model.pkl`
- `data/models/rf_win_model_enhanced.pkl`
- `data/models/model_features.pkl`
- `data/models/enhanced_features_list.pkl`

---

## ⚠️ **OBSOLETE / UNUSED FILES**

### Data Files (Can Delete)

**Intermediate/Debug Files:**
- ❌ `data/raw/pgatour_event_filters_debug.csv` - Debug file, not used
- ❌ `data/raw/player_stats_test.csv` - Test file, not used
- ❌ `data/raw/pgatour_players.csv` - Old scraper output, not used in pipeline
- ❌ `data/raw/pgatour_player_event_history.csv` - Old format, superseded by historical data
- ❌ `data/raw/pgatour_strokes_gained_long.csv` - Old format, superseded
- ❌ `data/raw/pgatour_tournament_strokes_gained_long.csv` - Old format, superseded

**Duplicate Schedule Files:**
- ❌ `data/raw/espn_schedule_2025.csv` - Not used (we use 2026)
- ❌ `data/raw/pgatour_schedule_2025.csv` - Not used (we use 2026)
- ❌ `data/raw/espn_schedule_2026.csv` - Duplicate of schedule_2026.csv

**Moved to Wrong Location (should be in processed/):**
- ⚠️ `data/raw/payout_model.csv` - Should be in processed/
- ⚠️ `data/raw/course_history_2026.csv` - Should be in processed/
- ⚠️ `data/raw/full_df.csv` - Should be in processed/
- ⚠️ `data/raw/full_df_with_course_history.csv` - Should be in processed/
- ⚠️ `data/raw/optimal_season_plan_2026.csv` - Should be in outputs/
- ⚠️ `data/raw/weekly_picks_summary_2026.csv` - Should be in outputs/

**Old Format Data (Superseded by historical/):**
- ❌ `data/raw/tournament_leaderboards.csv` - Old single-year data, use historical/ instead
- ❌ `data/raw/pgatour_tournament_stats_long.csv` - Old format, use tournament_stats_YYYY.csv

**Catalog Files (Keep only if scraping more):**
- ❓ `data/raw/pgatour_stat_id_catalog.csv` - Only needed for scraping
- ❓ `data/raw/pgatour_strokes_gained_stat_ids.csv` - Only needed for scraping
- ❓ `data/raw/tournament_ids.csv` - Only needed for scraping

### Scripts (Can Archive/Delete)

**Obsolete Scrapers:**
- ❌ `scripts/scrapers/multi_year_scraper.py` - **BROKEN VERSION** (replaced by _fixed.py)
- ❌ `scripts/scrapers/schedule_scraper.py` - Not used (schedule already scraped)
- ❌ `scripts/scrapers/web_scraping.py` - Old scraper, not used
- ❌ `results_scaper.py` - Old location, wrong directory (should be in scripts/)
- ❌ `scripts/scrapers/per_tournament_data_scraper.py` - Old format scraper

**Obsolete Feature Scripts:**
- ❌ `scripts/features/merge_and_retrain.py` - Superseded by merge_all_historical_data.py

**Obsolete Validation:**
- ❌ `scripts/validation/proper_validation.py` - Superseded by train_final_models.py

### Notebooks (Keep for Learning, but not pipeline-critical)

**Exploratory Notebook (Can archive after learning):**
- ❓ `notebooks/analysis/PGA_STATS_EDA.ipynb` - Original exploration, not part of learning path

---

## 📋 **RECOMMENDED CLEANUP ACTIONS**

### Option 1: Safe Cleanup (Move to archive/)

```bash
# Create archive directory
mkdir -p archive/{old_data,old_scripts,old_notebooks}

# Archive obsolete data files
mv data/raw/pgatour_event_filters_debug.csv archive/old_data/
mv data/raw/player_stats_test.csv archive/old_data/
mv data/raw/pgatour_players.csv archive/old_data/
mv data/raw/pgatour_player_event_history.csv archive/old_data/
mv data/raw/pgatour_strokes_gained_long.csv archive/old_data/
mv data/raw/pgatour_tournament_strokes_gained_long.csv archive/old_data/
mv data/raw/espn_schedule_2025.csv archive/old_data/
mv data/raw/pgatour_schedule_2025.csv archive/old_data/
mv data/raw/espn_schedule_2026.csv archive/old_data/
mv data/raw/tournament_leaderboards.csv archive/old_data/
mv data/raw/pgatour_tournament_stats_long.csv archive/old_data/

# Archive obsolete scripts
mv scripts/scrapers/multi_year_scraper.py archive/old_scripts/
mv scripts/scrapers/schedule_scraper.py archive/old_scripts/
mv scripts/scrapers/web_scraping.py archive/old_scripts/
mv scripts/scrapers/per_tournament_data_scraper.py archive/old_scripts/
mv results_scaper.py archive/old_scripts/
mv scripts/features/merge_and_retrain.py archive/old_scripts/
mv scripts/validation/proper_validation.py archive/old_scripts/

# Archive exploratory notebook
mv notebooks/analysis/PGA_STATS_EDA.ipynb archive/old_notebooks/
```

### Option 2: Move Files to Correct Locations

```bash
# Move processed data to correct directory
mv data/raw/payout_model.csv data/processed/
mv data/raw/course_history_2026.csv data/processed/
mv data/raw/full_df.csv data/processed/
mv data/raw/full_df_with_course_history.csv data/processed/

# Move outputs to correct directory
mv data/raw/optimal_season_plan_2026.csv outputs/
mv data/raw/weekly_picks_summary_2026.csv outputs/
```

---

## 📊 **SPACE SAVINGS ESTIMATE**

**Files to Archive:**
- Old data files: ~5-10 MB
- Old scripts: ~50 KB
- Old notebooks: ~2-3 MB

**Total savings: ~7-13 MB** (minimal, but better organization)

---

## 🎯 **FINAL PIPELINE FILES ONLY**

If you want to keep ONLY production files (delete everything not needed for 2026 predictions):

### Keep Only:
```
data/
├── historical/
│   ├── leaderboards_2020-2024.csv (5 files)
│   └── tournament_stats_2020-2024.csv (5 files when scraping done)
├── processed/
│   └── master_training_data_2020_2024.csv (created after merge)
├── models/
│   ├── win_model_final.pkl (created by train_final_models.py)
│   ├── top5_model_final.pkl
│   ├── top10_model_final.pkl
│   └── feature_importance.csv
└── raw/
    └── schedule_2026.csv

scripts/
├── scrapers/
│   └── multi_year_stats_scraper_fixed.py (for future years)
├── features/
│   └── merge_all_historical_data.py
└── validation/
    └── train_final_models.py

# Optional: Keep learning notebooks for reference
notebooks/analysis/
├── 01_prize_money_analysis.ipynb
├── 02_win_probability_model.ipynb
├── 03_weekly_recommendation_engine.ipynb
├── 04_season_optimizer.ipynb
└── 05_enhanced_features.ipynb
```

---

## ❓ **DECISION NEEDED**

**Catalog files - Keep or delete?**
- `pgatour_stat_id_catalog.csv`
- `pgatour_strokes_gained_stat_ids.csv`
- `tournament_ids.csv`

**Recommendation:**
- Keep if you plan to scrape 2025 data in the future
- Delete if you're done scraping (you have 2020-2024)

---

## ✅ **SAFE TO DELETE NOW**

These files are 100% not used anywhere:

1. `data/raw/pgatour_event_filters_debug.csv` - Debug file
2. `data/raw/player_stats_test.csv` - Test file
3. `scripts/scrapers/multi_year_scraper.py` - **BROKEN**, use _fixed.py instead
4. `results_scaper.py` - Wrong location, old file

---

**Summary:** Most files can be archived rather than deleted for safety. The pipeline will work with just ~15 files once scraping completes.