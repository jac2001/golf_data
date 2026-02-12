#!/bin/bash
# Weekly Tournament Prediction Automation Script
#
# This script automates the complete weekly workflow:
# 1. Fetch tournament field from ESPN
# 2. Match player IDs to master database
# 3. Run predictions with optimal settings
# 4. Generate picks report
# 5. Save outputs
#
# Usage:
#   ./weekly_predictions.sh --espn-id 401811929 --name "American Express" --purse 9600000
#   ./weekly_predictions.sh --espn-id 401811929 --name "American Express" --purse 9600000 --type Signature

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
PROJECT_ROOT="/Users/jacklegnon/Desktop/golf_data"
TOURNAMENT_TYPE="Standard"
SG_METHOD="last_5"
TOP_N=20

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --espn-id)
            ESPN_ID="$2"
            shift 2
            ;;
        --name)
            TOURNAMENT_NAME="$2"
            shift 2
            ;;
        --purse)
            PURSE="$2"
            shift 2
            ;;
        --type)
            TOURNAMENT_TYPE="$2"
            shift 2
            ;;
        --sg-method)
            SG_METHOD="$2"
            shift 2
            ;;
        --top-n)
            TOP_N="$2"
            shift 2
            ;;
        --help)
            echo "Weekly Tournament Predictions Automation"
            echo ""
            echo "Usage:"
            echo "  ./weekly_predictions.sh --espn-id ID --name NAME --purse AMOUNT [OPTIONS]"
            echo ""
            echo "Required:"
            echo "  --espn-id ID        ESPN tournament ID (from URL)"
            echo "  --name NAME         Tournament name (e.g., 'American Express')"
            echo "  --purse AMOUNT      Tournament purse in dollars"
            echo ""
            echo "Optional:"
            echo "  --type TYPE         Tournament type: Standard, Signature, or Major (default: Standard)"
            echo "  --sg-method METHOD  SG calculation: season_avg, last_5, or weighted (default: last_5)"
            echo "  --top-n N           Number of recommendations (default: 20)"
            echo ""
            echo "Examples:"
            echo "  ./weekly_predictions.sh --espn-id 401811929 --name 'American Express' --purse 9600000"
            echo "  ./weekly_predictions.sh --espn-id 401811930 --name 'Farmers Insurance' --purse 9300000 --type Standard"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$ESPN_ID" ] || [ -z "$TOURNAMENT_NAME" ] || [ -z "$PURSE" ]; then
    echo -e "${RED}Error: Missing required arguments${NC}"
    echo "Usage: ./weekly_predictions.sh --espn-id ID --name NAME --purse AMOUNT"
    echo "Use --help for more information"
    exit 1
fi

# Create safe filename from tournament name
SAFE_NAME=$(echo "$TOURNAMENT_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/ /_/g' | sed 's/[^a-z0-9_]//g')
YEAR=$(date +%Y)
WEEK=$(date +%U)

# File paths
FIELD_OUTPUT="$PROJECT_ROOT/data/fields/${SAFE_NAME}_${YEAR}.csv"
PREDICTIONS_OUTPUT="$PROJECT_ROOT/outputs/${SAFE_NAME}_${YEAR}_predictions.csv"
PICKS_OUTPUT="$PROJECT_ROOT/outputs/${SAFE_NAME}_${YEAR}_picks.md"

echo "========================================================================"
echo -e "${BLUE}  WEEKLY TOURNAMENT PREDICTIONS - AUTOMATED WORKFLOW${NC}"
echo "========================================================================"
echo ""
echo "Tournament: $TOURNAMENT_NAME"
echo "ESPN ID: $ESPN_ID"
echo "Purse: \$$(printf "%'d" $PURSE)"
echo "Type: $TOURNAMENT_TYPE"
echo "Date: $(date '+%B %d, %Y')"
echo ""

# Step 1: Fetch field from ESPN
echo "========================================================================"
echo -e "${GREEN}STEP 1: Fetching Tournament Field from ESPN${NC}"
echo "========================================================================"
echo ""

python3 "$PROJECT_ROOT/scripts/scrapers/fetch_field_from_espn.py" \
    --tournament-id "$ESPN_ID" \
    --output "${FIELD_OUTPUT}.raw" \
    --match-ids

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to fetch field from ESPN${NC}"
    exit 1
fi
echo ""

# Step 2: Clean field data
echo "========================================================================"
echo -e "${GREEN}STEP 2: Cleaning Field Data${NC}"
echo "========================================================================"
echo ""

python3 << EOF
import pandas as pd

# Load raw field
df = pd.read_csv('${FIELD_OUTPUT}.raw')

# Filter out noise - keep only rows with valid player_id
df_clean = df[df['player_id'].notna()].copy()
df_clean['player_id'] = df_clean['player_id'].astype(int)

# Remove any rows where player name looks suspicious
noise_keywords = ['weather', 'wind', 'precipitation', 'pga tour', 'champions',
                  'world', 'korn ferry', 'see all', 'tee time', 'opens', 'wins',
                  'trick shot', 'stuns', 'announcers']

def is_valid_player(name):
    name_lower = str(name).lower()
    return not any(keyword in name_lower for keyword in noise_keywords)

df_clean = df_clean[df_clean['player_name'].apply(is_valid_player)]

# Save clean field
df_clean.to_csv('${FIELD_OUTPUT}', index=False)

print(f"✓ Cleaned field: {len(df_clean)} players")
print(f"✓ Saved to: ${FIELD_OUTPUT}")
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to clean field data${NC}"
    exit 1
fi

# Remove raw file
rm "${FIELD_OUTPUT}.raw"
echo ""

# Step 3: Run predictions
echo "========================================================================"
echo -e "${GREEN}STEP 3: Running Predictions${NC}"
echo "========================================================================"
echo ""

python3 "$PROJECT_ROOT/scripts/predictions/predict_tournament.py" \
    --tournament "$TOURNAMENT_NAME" \
    --purse "$PURSE" \
    --field "$FIELD_OUTPUT" \
    --tournament-type "$TOURNAMENT_TYPE" \
    --sg-method "$SG_METHOD" \
    --top-n "$TOP_N" \
    --output "$PREDICTIONS_OUTPUT"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Prediction script failed${NC}"
    exit 1
fi
echo ""

# Step 4: Generate picks report
echo "========================================================================"
echo -e "${GREEN}STEP 4: Generating Picks Report${NC}"
echo "========================================================================"
echo ""

# Export variables for Python script
export PREDICTIONS_OUTPUT PICKS_OUTPUT TOURNAMENT_NAME TOURNAMENT_TYPE PURSE SG_METHOD SAFE_NAME YEAR

python3 << 'EOF'
import pandas as pd
from datetime import datetime
import os

# Get variables from environment
PREDICTIONS_OUTPUT = os.environ.get('PREDICTIONS_OUTPUT')
PICKS_OUTPUT = os.environ.get('PICKS_OUTPUT')
TOURNAMENT_NAME = os.environ.get('TOURNAMENT_NAME')
TOURNAMENT_TYPE = os.environ.get('TOURNAMENT_TYPE')
PURSE = int(os.environ.get('PURSE'))
SG_METHOD = os.environ.get('SG_METHOD')
SAFE_NAME = os.environ.get('SAFE_NAME')
YEAR = os.environ.get('YEAR')

# Load predictions
df = pd.read_csv(PREDICTIONS_OUTPUT)

# Get top picks
top_20 = df.nlargest(20, 'expected_value')
top_3 = top_20.head(3)

# Start markdown report
report = f"""# {TOURNAMENT_NAME} {YEAR} - Weekly Picks

**Generated**: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
**Purse**: ${PURSE:,}
**Type**: {TOURNAMENT_TYPE}
**Field Size**: {len(df)} players

---

## 🏆 YOUR TOP 3 PICKS (Recommended)

"""

# Add top 3 picks
for idx, (i, player) in enumerate(top_3.iterrows(), 1):
    stars = "⭐" * (4 - idx)  # 3 stars for 1st, 2 for 2nd, 1 for 3rd
    report += f"""### {idx}. {player['player_name']} {stars}
- **Expected Value**: \${player['expected_value']:,.0f}
- **Win**: {player['win_prob']*100:.2f}% | **Top-5**: {player['top5_prob']*100:.2f}% | **Top-10**: {player['top10_prob']*100:.2f}%
- **Recent Form**: SG Total: {player['sg_total']:+.3f}
"""
    if pd.notna(player['hist_times_played']) and player['hist_times_played'] > 0:
        report += f"- **Course History**: {int(player['hist_times_played'])} starts, {player['hist_avg_finish']:.1f} avg finish\n"
    else:
        report += "- **Course History**: No history at venue (rookie)\n"
    report += "\n"

# Add top 20 table
report += """---

## 📊 TOP 20 PICKS BY EXPECTED VALUE

| Rank | Player | EV | Win % | Top-5 % | Top-10 % | SG Total | Course Hist |
|------|--------|-------|-------|---------|----------|----------|-------------|
"""

for idx, (i, player) in enumerate(top_20.iterrows(), 1):
    hist = f"{int(player['hist_times_played'])}x" if pd.notna(player['hist_times_played']) and player['hist_times_played'] > 0 else "None"
    report += f"| {idx} | {player['player_name']} | \${player['expected_value']:,.0f} | {player['win_prob']*100:.1f}% | {player['top5_prob']*100:.1f}% | {player['top10_prob']*100:.1f}% | {player['sg_total']:+.2f} | {hist} |\n"

# Add stats summary
report += f"""

---

## 📈 FIELD ANALYSIS

**Total Players**: {len(df)}
**Average EV**: \${df['expected_value'].mean():,.0f}
**Max EV**: \${df['expected_value'].max():,.0f}

**Top Win Probabilities**:
"""

top_win = df.nlargest(5, 'win_prob')
for i, player in top_win.iterrows():
    report += f"- {player['player_name']}: {player['win_prob']*100:.2f}%\n"

report += f"""

**Players with Course History**: {df['hist_times_played'].notna().sum()} / {len(df)}
**Players with SG Data**: {df['sg_total'].notna().sum()} / {len(df)}

---

## 🎯 STRATEGY NOTES

### Conservative Approach
Pick the top 3 by EV - they have the best combination of win probability and consistency.

### Balanced Approach (Recommended)
- Pick #1: {top_3.iloc[0]['player_name']} (highest EV)
- Pick #2: Top-5 win probability player (higher upside)
- Pick #3: Player with best course history

### Aggressive Approach
Focus on players with high win % even if lower EV - go for tournament winner.

---

## 📁 FILES

- **Full Predictions**: [{SAFE_NAME}_{YEAR}_predictions.csv]({SAFE_NAME}_{YEAR}_predictions.csv)
- **Tournament Field**: [data/fields/{SAFE_NAME}_{YEAR}.csv](../data/fields/{SAFE_NAME}_{YEAR}.csv)
- **System Docs**: [PREDICTION_SYSTEM_COMPLETE.md](../PREDICTION_SYSTEM_COMPLETE.md)

---

**Model Version**: 2020-2025 Training Data
**SG Method**: {SG_METHOD}
**Prediction Engine**: Random Forest (Win/Top5/Top10 Models)

*Generated by automated weekly workflow*
"""

# Save report
with open(PICKS_OUTPUT, 'w') as f:
    f.write(report)

print(f"✓ Generated picks report: {PICKS_OUTPUT}")
EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to generate picks report${NC}"
    exit 1
fi
echo ""

# Step 5: Summary
echo "========================================================================"
echo -e "${GREEN}✅ WORKFLOW COMPLETE!${NC}"
echo "========================================================================"
echo ""
echo "Generated files:"
echo -e "  📊 Field:        ${BLUE}${FIELD_OUTPUT}${NC}"
echo -e "  📈 Predictions:  ${BLUE}${PREDICTIONS_OUTPUT}${NC}"
echo -e "  📝 Picks Report: ${BLUE}${PICKS_OUTPUT}${NC}"
echo ""
echo "Next steps:"
echo "  1. Review picks report: cat ${PICKS_OUTPUT}"
echo "  2. Make your fantasy picks before tournament starts"
echo "  3. Track results after tournament ends"
echo ""
echo "View top 3 picks:"
python3 << EOF
import pandas as pd
df = pd.read_csv('${PREDICTIONS_OUTPUT}')
top_3 = df.nlargest(3, 'expected_value')
print("")
for idx, (i, player) in enumerate(top_3.iterrows(), 1):
    print(f"  {idx}. {player['player_name']:<25} EV: \\\${player['expected_value']:>8,.0f}  Win: {player['win_prob']*100:>5.2f}%")
print("")
EOF

echo "========================================================================"
