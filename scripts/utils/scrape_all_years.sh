#!/bin/bash

# Scrape All Historical Years
# ============================
# This script scrapes tournament stats for 2020-2024
# Run time: ~1.5-2 hours total

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📊 MULTI-YEAR STATS SCRAPER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will scrape PGA Tour stats for 2020-2024"
echo "Estimated time: 1.5-2 hours"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Cancelled."
    exit 1
fi

# Years to scrape (2023 already done)
YEARS=(2024 2022 2021 2020)

echo ""
echo "Will scrape years: ${YEARS[@]}"
echo "Output: data/historical/tournament_stats_YYYY.csv"
echo ""

# Scrape each year
for year in "${YEARS[@]}"
do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  🏌️  YEAR $year"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    START_TIME=$(date +%s)

    python3 scripts/scrapers/multi_year_stats_scraper_fixed.py \
        --year $year \
        --output-dir data/historical \
        --sleep 0.7

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    MINUTES=$((ELAPSED / 60))
    SECONDS=$((ELAPSED % 60))

    echo ""
    echo "✅ Completed $year in ${MINUTES}m ${SECONDS}s"

    # Show file info
    if [ -f "data/historical/tournament_stats_$year.csv" ]; then
        LINES=$(wc -l < "data/historical/tournament_stats_$year.csv")
        SIZE=$(du -h "data/historical/tournament_stats_$year.csv" | cut -f1)
        echo "📁 File: $SIZE, $LINES records"
    fi

    # Small delay between years
    if [ "$year" != "2020" ]; then
        echo ""
        echo "Pausing 10 seconds before next year..."
        sleep 10
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ ALL YEARS COMPLETE!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Data collected:"
ls -lh data/historical/tournament_stats_*.csv
echo ""
echo "Next steps:"
echo "  1. Update course history: python scripts/features/course_history_features.py"
echo "  2. Merge data: python scripts/features/merge_and_retrain.py"
echo "  3. Validate: python scripts/validation/proper_validation.py"
echo ""