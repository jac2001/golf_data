# Field Scraper Solution - Lessons Learned

## Problem

The PGA Tour website HTML scraper ([fetch_tournament_field.py](scripts/scrapers/fetch_tournament_field.py)) was missing **30 key players** including:
- ❌ Scottie Scheffler (the tournament favorite!)
- ❌ Patrick Cantlay
- ❌ Wyndham Clark
- ❌ Rickie Fowler
- ❌ Ludvig Åberg

**Result**: 120 players instead of 150

---

## Root Cause

The PGA Tour website uses React/Next.js with dynamic JavaScript rendering. The embedded JSON data (`__NEXT_DATA__`) was incomplete or the player list was loaded via subsequent API calls after initial page load.

---

## Solution

Created **ESPN scraper** ([fetch_field_from_espn.py](scripts/scrapers/fetch_field_from_espn.py)) as a more reliable alternative.

### Why ESPN Works Better

1. **Static HTML**: ESPN's leaderboard page includes all players in the initial HTML
2. **No API authentication**: No x-api-key required
3. **Simpler structure**: Direct table/list format
4. **Complete data**: All 150+ players present

### Implementation

```bash
# Fetch field from ESPN
python3 scripts/scrapers/fetch_field_from_espn.py \
    --tournament-id 401811929 \
    --output data/fields/american_express_2026_espn.csv \
    --match-ids
```

**Results**:
- ✅ 150 players (complete field)
- ✅ Matched 150/167 to PGA Tour player IDs
- ✅ 17 noise items (headlines, navigation) filtered out

---

## Weekly Workflow (Updated)

### Option 1: ESPN Scraper (Recommended)

```bash
# 1. Find ESPN tournament ID from URL
# Go to: https://www.espn.com/golf/schedule
# Click tournament, copy ID from URL (e.g., 401811929)

# 2. Scrape field
python3 scripts/scrapers/fetch_field_from_espn.py \
    --tournament-id TOURNAMENT_ID \
    --output data/fields/this_week.csv \
    --match-ids

# 3. Clean any noise (if needed)
python3 << 'EOF'
import pandas as pd
df = pd.read_csv('data/fields/this_week.csv')
df_clean = df[df['player_id'].notna()].copy()
df_clean['player_id'] = df_clean['player_id'].astype(int)
df_clean.to_csv('data/fields/this_week_clean.csv', index=False)
EOF

# 4. Run predictions
python3 scripts/predictions/predict_tournament.py \
    --tournament "Tournament Name" \
    --purse 9600000 \
    --field data/fields/this_week_clean.csv \
    --tournament-type Standard \
    --sg-method last_5 \
    --top-n 20
```

### Option 2: PGA Tour Scraper (Backup)

```bash
# Try PGA Tour scraper (may miss players)
python3 scripts/scrapers/fetch_tournament_field.py \
    --tournament-id R2026002 \
    --output data/fields/this_week.csv

# Verify key players present
grep -i "scheffler\|mcilroy\|rahm" data/fields/this_week.csv
```

---

## Comparison: PGA vs ESPN

| Feature | PGA Tour Scraper | ESPN Scraper |
|---------|-----------------|--------------|
| **Completeness** | ❌ 120/150 (80%) | ✅ 150/150 (100%) |
| **Player IDs** | ✅ Native PGA IDs | ⚠️ Requires matching |
| **Reliability** | ⚠️ Depends on React rendering | ✅ Static HTML |
| **Speed** | Fast | Fast |
| **Maintenance** | ⚠️ Breaks if React changes | ✅ More stable |

**Recommendation**: Use ESPN scraper as primary, PGA Tour as backup.

---

## How to Find Tournament IDs

### ESPN Tournament ID

1. Go to https://www.espn.com/golf/schedule
2. Click on upcoming tournament
3. Copy ID from URL: `https://www.espn.com/golf/leaderboard?tournamentId=**401811929**`

### PGA Tour Tournament ID

1. Go to https://www.pgatour.com/tournaments
2. Click on tournament
3. Copy ID from URL: `https://www.pgatour.com/tournaments/2026/the-american-express/**R2026002**`

**Format**: `R[YEAR][TOURNAMENT_NUMBER]`
- Example: R2026002 = 2026, Tournament #2

---

## Field Matching Process

The ESPN scraper fetches player names but not PGA Tour IDs. We match names to our historical database:

```python
def clean_name(name):
    """Normalize for matching"""
    return re.sub(r'[^\w\s]', '', str(name).upper().strip())

# Match on cleaned names
player_map['name_clean'] = player_map['player_name'].apply(clean_name)
field_df['name_clean'] = field_df['player_name'].apply(clean_name)

matched = field_df.merge(player_map, on='name_clean', how='left')
```

**Typical Match Rate**: 145-150 out of 150 players (~97%)

**Unmatched players** are usually:
- Rookies not in 2020-2025 data
- International players with name variations
- Special characters (Åberg, González, etc.)

---

## Error Handling

### If ESPN Scraper Gets Noise

```python
# Filter out invalid rows
df_clean = df[df['player_id'].notna()]

# Remove headlines/navigation text
noise_keywords = ['weather', 'wind', 'pga tour', 'champions',
                  'tee time', 'opens', 'wins']
df_clean = df_clean[~df_clean['player_name'].str.lower().str.contains('|'.join(noise_keywords))]
```

### If Player IDs Don't Match

```bash
# Check historical database for player
python3 -c "
import pandas as pd
master = pd.read_csv('data/processed/master_training_data_2020_2025.csv')
player = master[master['player_name'].str.contains('PLAYER NAME', case=False)]
print(player[['player_id', 'player_name']].drop_duplicates())
"
```

---

## Files Generated

**From ESPN Scraper**:
1. `american_express_2026_espn.csv` - Raw ESPN data (167 rows, includes noise)
2. `american_express_2026_clean.csv` - Cleaned data (150 players, ready for predictions)

**Predictions**:
1. `american_express_2026_predictions_final.csv` - Full predictions (150 players)
2. `THE_AMERICAN_EXPRESS_2026_FINAL_PICKS.md` - Analysis and recommendations

---

## Key Takeaway

**Always verify your field includes the tournament favorite!**

A quick sanity check saved us from making predictions on an incomplete field and missing Scottie Scheffler's **36.7% win probability**.

---

## Future Improvements

### Short Term
- Add field validation check (compare expected field size to actual)
- Auto-detect missing top-10 ranked players
- Create hybrid scraper (try PGA first, fall back to ESPN)

### Long Term
- Build player name database with aliases (Ludvig Aberg vs Ludvig Åberg)
- Scrape fields earlier in the week (before tee times published)
- Add LIV Golf player tracking (if they play PGA events)

---

## Testing Your Scraper

```bash
# Test on completed tournament
python3 scripts/scrapers/fetch_field_from_espn.py \
    --tournament-id 401580332 \
    --output data/fields/test_field.csv \
    --match-ids

# Verify against known results
python3 -c "
import pandas as pd
field = pd.read_csv('data/fields/test_field.csv')
print(f'Field size: {len(field)}')
print(f'Players with IDs: {field[\"player_id\"].notna().sum()}')
print(f'Top 5 players:')
print(field.head())
"
```

---

**Bottom Line**: ESPN scraper is more reliable than PGA Tour scraper. Use it as your primary source for weekly fields.

*Last updated: January 19, 2026*