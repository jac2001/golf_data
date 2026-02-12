#!/bin/bash

echo "🧹 Organizing golf_data project..."

# Create organized directory structure
mkdir -p data/{raw,processed,models,historical}
mkdir -p notebooks/{analysis,modeling}
mkdir -p scripts/{scrapers,features,validation}
mkdir -p docs
mkdir -p outputs

# Move data files
echo "📁 Moving data files..."
mv *.csv data/raw/ 2>/dev/null || true
mv course_history_2026.csv data/processed/ 2>/dev/null || true
mv full_df_with_course_history.csv data/processed/ 2>/dev/null || true
mv payout_model.csv data/processed/ 2>/dev/null || true

# Move historical data
mv historical_data/* data/historical/ 2>/dev/null || true
rmdir historical_data 2>/dev/null || true

# Move models
echo "🤖 Moving models..."
mv *.pkl data/models/ 2>/dev/null || true

# Move notebooks
echo "📓 Moving notebooks..."
mv 0*.ipynb notebooks/analysis/ 2>/dev/null || true
mv PGA_STATS_EDA.ipynb notebooks/analysis/ 2>/dev/null || true

# Move scrapers
echo "🕷️ Moving scrapers..."
mv *scraper*.py scripts/scrapers/ 2>/dev/null || true
mv web_scraping.py scripts/scrapers/ 2>/dev/null || true

# Move feature engineering
echo "⚙️ Moving feature scripts..."
mv course_history_features.py scripts/features/ 2>/dev/null || true
mv merge_and_retrain.py scripts/features/ 2>/dev/null || true

# Move validation
echo "✅ Moving validation..."
mv proper_validation.py scripts/validation/ 2>/dev/null || true

# Move documentation
echo "📚 Moving documentation..."
mv *.md docs/ 2>/dev/null || true

# Move outputs
echo "📊 Moving outputs..."
mv optimal_season_plan_2026.csv outputs/ 2>/dev/null || true
mv weekly_picks_summary_2026.csv outputs/ 2>/dev/null || true
mv usage_tracker.json outputs/ 2>/dev/null || true

# Clean up debug files
echo "🗑️ Removing debug files..."
rm DEBUG_*.json 2>/dev/null || true
rm .DS_Store 2>/dev/null || true

echo "✅ Organization complete!"
echo ""
echo "New structure:"
tree -L 2 -d .

