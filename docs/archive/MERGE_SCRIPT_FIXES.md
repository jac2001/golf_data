# Merge Script Debugging Summary

## Issues Found and Fixed

### 1. **stat_id Data Type Mismatch**
**Problem:** Script expected stat_id as string ('02567'), but actual data has it as int (2567)
```python
# BEFORE (wrong):
stat_mapping = {'02567': 'sg_total', ...}

# AFTER (fixed):
stat_mapping = {2567: 'sg_total', ...}
```

### 2. **Wrong Column Name for Stats**
**Problem:** Script tried to pivot on 'value' column, but actual column is 'stat_value'
```python
# BEFORE (wrong):
stats_pivot = tournament_stats.pivot_table(..., values='value', ...)

# AFTER (fixed):
stats_pivot = stats_avg.pivot_table(..., values='stat_value', ...)
```

### 3. **Multiple Stat Components**
**Problem:** Stats data has multiple components per stat (Avg, Total SG:OTT, Measured Rounds, etc.)
```python
# ADDED:
stats_avg = tournament_stats[tournament_stats['stat_component'] == 'Avg'].copy()
```
This filters to just the "Avg" values we want for modeling.

### 4. **Missing 'date' Column**
**Problem:** Leaderboard files don't have a 'date' column
**Actual columns:** tournament_id, year, player_id, player_name, position, total_score, to_par, fedex_points, earnings, rounds_played, tournament_name

**Solution:** Sort by year instead of date for temporal ordering
```python
# BEFORE (wrong):
merged['date'] = pd.to_datetime(merged['date'])
merged = merged.sort_values('date')

# AFTER (fixed):
merged = merged.sort_values(['year', 'tournament_id'])
```

### 5. **Missing 'course_name' Column**
**Problem:** Leaderboard files don't have course_name, only tournament_name

**Solution:** Use tournament_name as proxy for venue
```python
# BEFORE (wrong):
merged['course_clean'] = merged['course_name'].str.upper()...

# AFTER (fixed):
merged['venue_clean'] = merged['tournament_name'].str.upper()...
```

### 6. **Course History Logic Updated**
**Problem:** Can't use date-based lookback without dates

**Solution:** Use year-based lookback
```python
# BEFORE:
history = merged[(merged['player_id'] == player) &
                 (merged['course_clean'] == course) &
                 (merged['date'] < current_date)]

# AFTER:
history = merged[(merged['player_id'] == player) &
                 (merged['venue_clean'] == venue) &
                 (merged['year'] < current_year)]
```

## Key Findings About Your Data Structure

### Leaderboard Files
**Columns:**
- tournament_id, year, player_id, player_name
- position, total_score, to_par
- fedex_points, earnings, rounds_played
- tournament_name

**Missing:**
- ❌ date
- ❌ course_name
- ❌ made_cut flag
- ❌ world_rank

### Stats Files
**Columns:**
- player_id, player_name, rank
- stat_id (int), stat_name, stat_component, stat_value
- tournament_id, tournament_name, year

**Stat Components:**
- Avg (what we use for modeling)
- Measured Rounds
- Total SG:OTT, Total SG:APP, etc. (not used)

**Available SG Stats (stat_id):**
- 2567: Strokes Gained: Total
- 2568: Strokes Gained: Off-the-Tee
- 2569: Strokes Gained: Approach
- 2564: Strokes Gained: Putting
- 2674: Strokes Gained: Tee-to-Green
- (2570: Strokes Gained: Around-the-Green - may be missing/sparse)

## Data Coverage

Based on your scraping:
- ✅ **Leaderboards:** 2020-2024 (23,313 records total)
- ⚠️  **Stats:** 2021-2024 only (no 2020 stats)
  - 2021: 46,104 records
  - 2022: 42,721 records
  - 2023: 48,943 records
  - 2024: 44,370 records

**Impact:** 2020 leaderboard data will have no SG stats, only course history and target variables.

## Expected Merge Results

After running the fixed script:
- ~23,000 total records (all years with leaderboards)
- SG stats coverage: ~82% (only for 2021-2024)
- Course history coverage: ~40-50% (players with prior years at same venue)
- 6 SG stat features
- 6 course history features
- 2 venue difficulty features
- 4 target variables (won, top5, top10, top20)

**Total features:** ~30-35 columns

## Next Steps

Once merge completes successfully:
1. Check data quality report for missing values
2. Run train_final_models.py for proper validation
3. Expect 0.72-0.78 ROC-AUC with this dataset

---

**Script is now ready to run:** `python3 scripts/features/merge_all_historical_data.py`