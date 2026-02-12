#!/bin/bash

# Quick Scraping Progress Checker
# =================================
# Shows status of all historical data files

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📊 SCRAPING PROGRESS CHECK"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

YEARS=(2020 2021 2022 2023 2024)

echo "LEADERBOARD FILES:"
echo "──────────────────────────────────────────────────────"
for year in "${YEARS[@]}"
do
    FILE="data/historical/leaderboards_$year.csv"
    if [ -f "$FILE" ]; then
        LINES=$(wc -l < "$FILE" | tr -d ' ')
        SIZE=$(du -h "$FILE" | cut -f1)
        echo "  ✅ $year: $SIZE, $LINES records"
    else
        echo "  ❌ $year: Not found"
    fi
done

echo ""
echo "TOURNAMENT STATS FILES:"
echo "──────────────────────────────────────────────────────"
for year in "${YEARS[@]}"
do
    FILE="data/historical/tournament_stats_$year.csv"
    if [ -f "$FILE" ]; then
        LINES=$(wc -l < "$FILE" | tr -d ' ')
        SIZE=$(du -h "$FILE" | cut -f1)
        echo "  ✅ $year: $SIZE, $LINES records"
    else
        echo "  ⏳ $year: Not yet scraped"
    fi
done

echo ""
echo "SUMMARY:"
echo "──────────────────────────────────────────────────────"

LB_COUNT=$(ls -1 data/historical/leaderboards_*.csv 2>/dev/null | wc -l | tr -d ' ')
STATS_COUNT=$(ls -1 data/historical/tournament_stats_*.csv 2>/dev/null | wc -l | tr -d ' ')

echo "  Leaderboards: $LB_COUNT/5 complete"
echo "  Stats: $STATS_COUNT/5 complete"

if [ "$STATS_COUNT" -eq 5 ]; then
    echo ""
    echo "  ✅ ALL DATA COLLECTED!"
    echo ""
    echo "  Next steps:"
    echo "    1. python scripts/features/merge_all_historical_data.py"
    echo "    2. python scripts/validation/train_final_models.py"
elif [ "$STATS_COUNT" -gt 0 ]; then
    REMAINING=$((5 - STATS_COUNT))
    echo ""
    echo "  ⏳ Scraping in progress... ($REMAINING years remaining)"
fi

echo ""
