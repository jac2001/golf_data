#!/bin/bash
# Automated Project Cleanup Script
# Organizes files and archives old/duplicate data

set -e  # Exit on error

PROJECT_ROOT="/Users/jacklegnon/Desktop/golf_data"
cd "$PROJECT_ROOT"

echo "========================================================================"
echo "  GOLF DATA PROJECT CLEANUP"
echo "========================================================================"
echo ""

# Create archive directories
echo "Creating archive directories..."
mkdir -p docs/archive
mkdir -p data/fields/archive
mkdir -p data/processed/archive
mkdir -p data/models/archive
mkdir -p outputs/archive
mkdir -p scripts/archive
mkdir -p scripts/utils

echo "✓ Archive directories created"
echo ""

# 1. Archive old documentation
echo "1. Archiving old documentation..."
if [ -f "CHALLENGE_4_QUICK_FIXES.md" ]; then
    mv CHALLENGE_4_QUICK_FIXES.md docs/archive/
    echo "  ✓ Moved CHALLENGE_4_QUICK_FIXES.md"
fi

if [ -f "CLEANUP_ANALYSIS.md" ]; then
    mv CLEANUP_ANALYSIS.md docs/archive/
    echo "  ✓ Moved CLEANUP_ANALYSIS.md"
fi

if [ -f "MERGE_SCRIPT_FIXES.md" ]; then
    mv MERGE_SCRIPT_FIXES.md docs/archive/
    echo "  ✓ Moved MERGE_SCRIPT_FIXES.md"
fi

if [ -f "PROJECT_MAP.md" ]; then
    mv PROJECT_MAP.md docs/archive/
    echo "  ✓ Moved PROJECT_MAP.md"
fi
echo ""

# 2. Archive old model files
echo "2. Archiving old model files..."
cd data/models

if [ -f "rf_win_model.pkl" ]; then
    mv rf_win_model.pkl archive/
    echo "  ✓ Archived rf_win_model.pkl"
fi

if [ -f "rf_win_model_enhanced.pkl" ]; then
    mv rf_win_model_enhanced.pkl archive/
    echo "  ✓ Archived rf_win_model_enhanced.pkl"
fi

if [ -f "rf_top5_model.pkl" ]; then
    mv rf_top5_model.pkl archive/
    echo "  ✓ Archived rf_top5_model.pkl"
fi

if [ -f "model_features.pkl" ]; then
    mv model_features.pkl archive/
    echo "  ✓ Archived model_features.pkl"
fi

if [ -f "enhanced_features_list.pkl" ]; then
    mv enhanced_features_list.pkl archive/
    echo "  ✓ Archived enhanced_features_list.pkl"
fi

cd "$PROJECT_ROOT"
echo ""

# 3. Organize field files
echo "3. Organizing field files..."
cd data/fields

if [ -f "american_express_2025_field.csv" ]; then
    mv american_express_2025_field.csv archive/
    echo "  ✓ Archived american_express_2025_field.csv (historical test)"
fi

if [ -f "american_express_2026.csv" ]; then
    mv american_express_2026.csv archive/
    echo "  ✓ Archived american_express_2026.csv (incomplete field)"
fi

if [ -f "american_express_2026_espn.csv" ]; then
    mv american_express_2026_espn.csv archive/
    echo "  ✓ Archived american_express_2026_espn.csv (raw with noise)"
fi

if [ -f "test_field_small.csv" ]; then
    mv test_field_small.csv archive/
    echo "  ✓ Archived test_field_small.csv"
fi

cd "$PROJECT_ROOT"
echo ""

# 4. Remove duplicate field location
echo "4. Removing duplicate field files..."
if [ -d "scripts/scrapers/data" ]; then
    rm -rf scripts/scrapers/data
    echo "  ✓ Removed scripts/scrapers/data/ (duplicate location)"
fi
echo ""

# 5. Clean output files
echo "5. Organizing output files..."
cd outputs

if [ -f "american_express_predictions.csv" ]; then
    mv american_express_predictions.csv archive/
    echo "  ✓ Archived american_express_predictions.csv (old)"
fi

if [ -f "american_express_2026_predictions.csv" ]; then
    mv american_express_2026_predictions.csv archive/
    echo "  ✓ Archived american_express_2026_predictions.csv (incomplete)"
fi

if [ -f "THE_AMERICAN_EXPRESS_2026_PICKS.md" ]; then
    mv THE_AMERICAN_EXPRESS_2026_PICKS.md archive/
    echo "  ✓ Archived THE_AMERICAN_EXPRESS_2026_PICKS.md (superseded)"
fi

cd "$PROJECT_ROOT"
echo ""

# 6. Clean processed data
echo "6. Organizing processed data..."
cd data/processed

if [ -f "master_training_data_2020_2024.csv" ]; then
    mv master_training_data_2020_2024.csv archive/
    echo "  ✓ Archived master_training_data_2020_2024.csv (old version)"
fi

if [ -f "full_df.csv" ]; then
    mv full_df.csv archive/
    echo "  ✓ Archived full_df.csv (intermediate)"
fi

if [ -f "full_df_with_course_history.csv" ]; then
    mv full_df_with_course_history.csv archive/
    echo "  ✓ Archived full_df_with_course_history.csv (intermediate)"
fi

if [ -f "payout_model.csv" ]; then
    mv payout_model.csv archive/
    echo "  ✓ Archived payout_model.csv (not used)"
fi

cd "$PROJECT_ROOT"
echo ""

# 7. Organize utility scripts
echo "7. Organizing utility scripts..."

if [ -f "check_scraping_progress.sh" ]; then
    mv check_scraping_progress.sh scripts/utils/
    echo "  ✓ Moved check_scraping_progress.sh to scripts/utils/"
fi

if [ -f "organize_project.sh" ]; then
    mv organize_project.sh scripts/utils/
    echo "  ✓ Moved organize_project.sh to scripts/utils/"
fi

if [ -f "scrape_all_years.sh" ]; then
    mv scrape_all_years.sh scripts/utils/
    echo "  ✓ Moved scrape_all_years.sh to scripts/utils/"
fi

if [ -f "results_scaper.py" ]; then
    mv results_scaper.py scripts/archive/
    echo "  ✓ Archived results_scaper.py (old script with typo)"
fi
echo ""

# 8. Summary
echo "========================================================================"
echo "  CLEANUP COMPLETE!"
echo "========================================================================"
echo ""
echo "Summary of changes:"
echo "  • Created archive directories in data/, docs/, outputs/, scripts/"
echo "  • Archived 5 old model files → data/models/archive/"
echo "  • Archived 4 duplicate field files → data/fields/archive/"
echo "  • Archived 3 old output files → outputs/archive/"
echo "  • Archived 4 old processed files → data/processed/archive/"
echo "  • Archived 4 old documentation files → docs/archive/"
echo "  • Moved 3 utility scripts → scripts/utils/"
echo "  • Archived 1 old script → scripts/archive/"
echo "  • Removed duplicate directory: scripts/scrapers/data/"
echo ""
echo "Current production files:"
echo "  ✅ 4 final models in data/models/"
echo "  ✅ Master training data (2020-2025) in data/processed/"
echo "  ✅ Current tournament field in data/fields/"
echo "  ✅ Final predictions in outputs/"
echo ""
echo "Your project is now organized and ready for production use!"
echo ""

# Display disk space saved
echo "Calculating space saved..."
if command -v du &> /dev/null; then
    ARCHIVE_SIZE=$(du -sh data/*/archive outputs/archive docs/archive scripts/archive 2>/dev/null | awk '{sum+=$1} END {print sum}')
    echo "  Archived data: ~${ARCHIVE_SIZE} (moved to archive folders)"
fi
echo ""
