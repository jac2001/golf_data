# Weekly Tournament Workflow - Quick Start Guide

## Single-Command Predictions

Your complete weekly workflow is now automated into one script!

### Quick Start (3 minutes)

```bash
cd /Users/jacklegnon/Desktop/golf_data

# Run predictions for this week's tournament
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811929 \
    --name "American Express" \
    --purse 9600000
```

**That's it!** The script will:
1. ✅ Fetch the field from ESPN
2. ✅ Match player IDs to your database
3. ✅ Run predictions
4. ✅ Generate picks report
5. ✅ Save everything to outputs/

---

## How to Find ESPN Tournament ID

### Method 1: ESPN Schedule

1. Go to https://www.espn.com/golf/schedule
2. Click on this week's tournament
3. Copy ID from URL: `https://www.espn.com/golf/leaderboard?tournamentId=**401811929**`

### Method 2: Google Search

```
"[tournament name] 2026 ESPN"
```

Example: "Farmers Insurance Open 2026 ESPN" → Find ID in URL

---

## Common Tournament Types

Use `--type` parameter to specify:

### Standard Events (Most common)
- Purse: $8M - $9.6M
- Examples: American Express, Farmers Insurance, Valspar

```bash
--type Standard
```

### Signature Events (Elevated)
- Purse: $20M
- Examples: Genesis Invitational, Arnold Palmer, Memorial

```bash
--type Signature
```

### Majors
- Purse: $18M - $20M
- Examples: Masters, PGA Championship, US Open, Open Championship

```bash
--type Major
```

---

## Weekly Schedule

### Wednesday/Thursday (Before Tournament)

**Find tournament info**:
```bash
# Check PGA Tour schedule
# https://www.pgatour.com/schedule

# Or ESPN
# https://www.espn.com/golf/schedule
```

**Run predictions**:
```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id [ESPN_ID] \
    --name "[Tournament Name]" \
    --purse [PURSE_AMOUNT]
```

**Review picks**:
```bash
# Open the generated picks report
cat outputs/[tournament]_2026_picks.md
```

**Make your fantasy picks** before first tee time (usually Thursday morning)

---

### Sunday/Monday (After Tournament)

**Track your results**:
1. See how your picks performed
2. Update `outputs/season_log.csv` (manual for now)
3. Compare predictions to actual results

**Season log format**:
```csv
week,tournament,pick1,pick2,pick3,result1,result2,result3,points,notes
1,American Express,Scheffler,Brennan,Griffin,1st,T45,T18,150,"Scheffler won!"
```

---

## Examples for Upcoming Tournaments

### The American Express (Jan 22-25, 2026)
```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811929 \
    --name "American Express" \
    --purse 9600000 \
    --type Standard
```

### Farmers Insurance Open (Jan 29 - Feb 1, 2026)
```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811930 \
    --name "Farmers Insurance Open" \
    --purse 9300000 \
    --type Standard
```

### AT&T Pebble Beach Pro-Am (Feb 5-8, 2026)
```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811931 \
    --name "AT&T Pebble Beach Pro-Am" \
    --purse 9300000 \
    --type Standard
```

### The Genesis Invitational (Feb 12-15, 2026) - SIGNATURE
```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811932 \
    --name "Genesis Invitational" \
    --purse 20000000 \
    --type Signature
```

---

## Advanced Options

### Change SG Calculation Method

**Last 5 tournaments** (default, recommended):
```bash
--sg-method last_5
```

**Weighted recent form** (40%, 30%, 20%, 10%):
```bash
--sg-method weighted
```

**Season average**:
```bash
--sg-method season_avg
```

### Change Number of Recommendations

Default is 20 players. Adjust with:
```bash
--top-n 30  # Show top 30 picks
```

### Full Example with All Options

```bash
./scripts/predictions/weekly_predictions.sh \
    --espn-id 401811929 \
    --name "American Express" \
    --purse 9600000 \
    --type Standard \
    --sg-method weighted \
    --top-n 25
```

---

## Troubleshooting

### Error: "Failed to fetch field from ESPN"

**Cause**: Tournament hasn't started yet or ESPN ID is wrong

**Fix**:
1. Verify ESPN ID from tournament page
2. Try tomorrow (field usually posted Wednesday)
3. Use PGA Tour scraper as backup:
   ```bash
   python3 scripts/scrapers/fetch_tournament_field.py --tournament-id R2026002
   ```

### Error: "Unmatched players"

**Cause**: Some players not in 2020-2025 database (rookies)

**Impact**: Minor - predictions still run with median SG stats for rookies

**Fix**: Normal behavior, no action needed

### Error: "Tournament not found"

**Cause**: Tournament name doesn't match historical data

**Fix**: Use exact tournament name from master data:
```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/processed/master_training_data_2020_2025.csv')
tournaments = df['venue_clean'].unique()
print('\n'.join(sorted(set(tournaments))))
"
```

---

## Output Files

Each week generates 3 files:

### 1. Tournament Field
**Location**: `data/fields/[tournament]_2026.csv`

**Format**:
```csv
player_id,player_name
46046,Scottie Scheffler
35450,Patrick Cantlay
```

**Use**: Reference for who's in the field

---

### 2. Full Predictions
**Location**: `outputs/[tournament]_2026_predictions.csv`

**Columns**:
- player_id, player_name
- All 13 features (SG stats, course history, venue stats)
- win_prob, top5_prob, top10_prob
- expected_value

**Use**: Deep analysis, custom lineup building

---

### 3. Picks Report
**Location**: `outputs/[tournament]_2026_picks.md`

**Includes**:
- Top 3 recommended picks
- Top 20 players by EV
- Field analysis
- Strategy notes

**Use**: Quick decision making, copy to notes

---

## Time Savings

**Before automation**:
1. Find tournament ID: 2 min
2. Run field scraper: 2 min
3. Clean field data: 3 min
4. Run predictions: 2 min
5. Analyze results: 5 min
6. Format picks: 5 min

**Total**: ~20 minutes

**After automation**:
1. Find ESPN ID: 1 min
2. Run script: 1 min
3. Review picks: 2 min

**Total**: ~4 minutes

**Savings**: 16 minutes per week = **8+ hours per season!**

---

## Pro Tips

### 1. Create Tournament Aliases
Add to your `~/.bashrc` or `~/.zshrc`:

```bash
alias golf-predict="cd /Users/jacklegnon/Desktop/golf_data && ./scripts/predictions/weekly_predictions.sh"
```

Then run from anywhere:
```bash
golf-predict --espn-id 401811929 --name "American Express" --purse 9600000
```

### 2. Save Common Tournaments
Create a file `tournaments_2026.txt`:
```
401811929,American Express,9600000,Standard
401811930,Farmers Insurance Open,9300000,Standard
401811932,Genesis Invitational,20000000,Signature
```

### 3. Review Picks on Mobile
Generated markdown files render perfectly on GitHub, Notion, or any markdown viewer.

---

## Season-Long Tracking (Optional)

### Create Season Log

```bash
cat > outputs/season_log.csv << 'EOF'
week,date,tournament,pick1,pick2,pick3,result1,result2,result3,points,league_rank,notes
EOF
```

### Update After Each Tournament

Add a line with your results:
```csv
1,2026-01-25,American Express,Scheffler,Brennan,Griffin,1st,T45,T18,150,3/50,"Scheffler won!"
```

### Analyze at Mid-Season
```bash
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('outputs/season_log.csv')
print(f"Tournaments: {len(df)}")
print(f"Avg Points: {df['points'].mean():.1f}")
print(f"Avg Rank: {df['league_rank'].apply(lambda x: int(x.split('/')[0])).mean():.1f}")
EOF
```

---

## Next Enhancements (Future)

Planned additions to weekly workflow:
- ✅ Single-command predictions (DONE!)
- ⏳ Auto-scrape results after tournament
- ⏳ Compare predictions to actual results
- ⏳ Monthly model retraining
- ⏳ Calibration dashboard

See [docs/PIPELINE_ENHANCEMENTS.md](docs/PIPELINE_ENHANCEMENTS.md) for roadmap.

---

## Getting Help

```bash
./scripts/predictions/weekly_predictions.sh --help
```

Or check:
- [PREDICTION_SYSTEM_COMPLETE.md](PREDICTION_SYSTEM_COMPLETE.md) - System overview
- [FIELD_SCRAPER_SOLUTION.md](FIELD_SCRAPER_SOLUTION.md) - Field scraping details
- [docs/PREDICTION_PIPELINE_GUIDE.md](docs/PREDICTION_PIPELINE_GUIDE.md) - Technical details

---

**Ready for the PGA Tour season! 🏌️⛳**

*Last updated: January 19, 2026*