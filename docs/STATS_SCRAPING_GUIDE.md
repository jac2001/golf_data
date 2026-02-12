# Multi-Year Stats Scraping Guide

## 🎯 What We're Fixing

**Problem**: The original scraper got leaderboards but no tournament stats.

**Solution**: New robust scraper with:
- ✅ Better error handling
- ✅ Progress tracking with percentages
- ✅ Checkpoint saving (resume if interrupted)
- ✅ Focused on KEY strokes gained stats
- ✅ Verbose logging

---

## 📊 Stats Being Scraped

### Key Strokes Gained Stats (6 total):

| Stat ID | Stat Name | Why It Matters |
|---------|-----------|----------------|
| 02567 | SG: Total | Overall performance - THE most important |
| 02568 | SG: Off-the-Tee | Driving performance |
| 02569 | SG: Approach | Iron play - critical for scoring |
| 02570 | SG: Around-the-Green | Short game |
| 02564 | SG: Putting | Putting performance |
| 02674 | SG: Tee-to-Green | Ball striking (OTT + Approach + ARG) |

These 6 stats give you everything you need for modeling!

---

## 🚀 Usage

### Test on Single Year (Recommended First)
```bash
# Test with 2023 data (~15-20 min)
python multi_year_stats_scraper_fixed.py --year 2023
```

### Scrape Multiple Years
```bash
# Scrape 2022
python multi_year_stats_scraper_fixed.py --year 2022

# Scrape 2021
python multi_year_stats_scraper_fixed.py --year 2021

# Etc.
```

### All Stats (Slow!)
```bash
# Scrape ALL stats from catalog (~2-3 hours per year)
python multi_year_stats_scraper_fixed.py --year 2023 --all-stats
```

---

## ⏱️ Time Estimates

| Task | Time | Records |
|------|------|---------|
| 1 year, KEY stats (6 stats) | 15-20 min | ~15,000-20,000 |
| 1 year, ALL stats (~100 stats) | 2-3 hours | ~250,000+ |
| 5 years, KEY stats | 1.5-2 hours | ~75,000-100,000 |

**Recommendation**: Start with KEY stats for 2023, verify it works, then do other years.

---

## 📁 Output Files

### During Scraping:
```
historical_data/
├── checkpoint_stats_2023.csv  ← Progress checkpoint (auto-deleted when done)
```

### After Completion:
```
historical_data/
├── tournament_stats_2023.csv  ← Final output
├── tournament_stats_2022.csv
├── tournament_stats_2021.csv
└── ...
```

---

## 🔧 Features

### 1. Progress Tracking
```
[123/246 (50.0%)] THE PLAYERS Championship                ✓ 78 rows
[124/246 (50.4%)] Masters Tournament                      ✓ 91 rows
[125/246 (50.8%)] Wells Fargo Championship                ⊘
```
- `✓` = Success
- `⊘` = No data (stat not available for this tournament)
- `✗` = Error

### 2. Checkpoint/Resume
If scraping is interrupted:
```bash
# Just run the same command again - it will resume!
python multi_year_stats_scraper_fixed.py --year 2023
```

Output will show:
```
📁 Found checkpoint file, loading...
   Resuming from 123/246 requests
```

### 3. Error Handling
- Retries on network errors (3 attempts)
- Graceful handling of missing stats
- Continues on errors instead of crashing

---

## 📊 What You'll Get

### Sample Output Data:
```csv
player_id,player_name,rank,stat_id,stat_name,stat_component,stat_value,tournament_id,tournament_name,year
48081,Scottie Scheffler,1,02567,Strokes Gained: Total,Avg,3.872,R2023013,THE PLAYERS Championship,2023
48081,Scottie Scheffler,1,02567,Strokes Gained: Total,Total SG:Total,15.488,R2023013,THE PLAYERS Championship,2023
48081,Scottie Scheffler,1,02567,Strokes Gained: Total,Measured Rounds,4,R2023013,THE PLAYERS Championship,2023
```

### Data Structure:
- **player_id**: Unique player identifier
- **player_name**: Player name
- **stat_id**: Stat identifier (02567 = SG:Total)
- **stat_name**: Human-readable stat name
- **stat_component**: Avg, Total, Measured Rounds
- **stat_value**: The actual value
- **tournament_id**: Tournament identifier
- **tournament_name**: Tournament name
- **year**: Year

---

## 🎯 Monitoring Progress

### Check Live Progress:
```bash
# In another terminal, watch the output file grow
watch -n 5 'wc -l historical_data/checkpoint_stats_2023.csv'
```

### Check Completion:
```bash
# See if final file exists
ls -lh historical_data/tournament_stats_2023.csv
```

---

## 🐛 Troubleshooting

### "No tournaments found"
- API key might be expired
- Check internet connection
- Try different stat_id

### "Too many errors"
- Increase sleep time: `--sleep 1.0`
- API might be rate-limiting

### Scraping is slow
- Normal! 6 stats × 40 tournaments = 240 requests
- Each request takes ~0.7s = ~3 minutes per stat
- Total: ~15-20 minutes for 6 stats

### Want to speed up?
**Don't!** Going too fast will get you rate-limited.
- Min sleep: 0.5s
- Recommended: 0.6-0.7s
- Conservative: 1.0s

---

## 📈 After Scraping All Years

Once you have stats for 2020-2024:

```
historical_data/
├── leaderboards_2020.csv       ← Already have
├── leaderboards_2021.csv       ← Already have
├── leaderboards_2022.csv       ← Already have
├── leaderboards_2023.csv       ← Already have
├── leaderboards_2024.csv       ← Already have
├── tournament_stats_2020.csv   ← Need to scrape
├── tournament_stats_2021.csv   ← Need to scrape
├── tournament_stats_2022.csv   ← Need to scrape
├── tournament_stats_2023.csv   ← Scraping now!
└── tournament_stats_2024.csv   ← Need to scrape
```

### Next Steps:
1. Merge stats with leaderboards
2. Create complete player-tournament dataset
3. Calculate rolling averages of SG metrics
4. Add course history features
5. Retrain models with full feature set

---

## 💡 Pro Tips

1. **Start small**: Test with 2023 first
2. **Monitor first stat**: Watch the first stat scrape to ensure it's working
3. **Don't interrupt**: Let it finish - checkpoints help but complete runs are better
4. **Check data quality**: After scraping, verify record counts match expectations
5. **One year at a time**: Don't try to do all 5 years in parallel

---

## 🎯 Expected Final Dataset

After merging leaderboards + stats for all years:

**Rows**: ~23,000 (player-tournament combinations)
**Columns**: ~30-40 features including:
- Finish position
- Earnings
- SG: Total, OTT, App, ARG, Putting
- Course history features
- Rolling averages
- Cut rates

**Expected Model Performance** with this data:
- ROC-AUC: **0.72-0.78** (properly validated)
- Feature importance: **0.35-0.45** for top features
- **Much better** than current 0.57!

---

Ready to run? Start with:
```bash
python multi_year_stats_scraper_fixed.py --year 2023
```

Then grab a coffee ☕ - it'll take ~15-20 minutes!