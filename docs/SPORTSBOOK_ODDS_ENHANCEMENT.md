# Sportsbook Odds Integration - Enhancement Plan

## Overview

Add sportsbook betting odds as a feature in your prediction system. Compare your model's predictions against Vegas odds to find value and improve accuracy.

---

## Why Add Sportsbook Odds?

### 1. Market Information
- **Vegas odds reflect** collective wisdom of bettors + bookmaker models
- **Your edge**: When your model disagrees significantly with odds
- **Example**: Model says 10% win chance, odds imply 5% → Potential value bet

### 2. Model Calibration
- Compare your probabilities to implied probabilities from odds
- Identify where your model is over/under confident
- Adjust predictions based on market

### 3. Additional Features
Use odds as model inputs:
- **Implied win probability** from outright odds
- **Market consensus** on player strength
- **Recent form reflected in odds** (line movement)

### 4. Value Detection
Find discrepancies:
```
Your Model: Scheffler 35% win
Odds Imply: Scheffler 25% win
→ Your model is more bullish (potential value if you're right)
```

---

## Data Sources

### Option 1: The Odds API (Recommended)
**Website**: https://the-odds-api.com

**Pros**:
- ✅ Free tier (500 requests/month)
- ✅ Clean API, well-documented
- ✅ Multiple sportsbooks (DraftKings, FanDuel, BetMGM, etc.)
- ✅ Historical odds available
- ✅ Python client library

**Cons**:
- ⚠️ Requires API key (free)
- ⚠️ Rate limited (25 requests/day on free tier)

**Endpoints**:
```python
# Get golf tournaments
GET https://api.the-odds-api.com/v4/sports/golf_pga/events

# Get odds for specific tournament
GET https://api.the-odds-api.com/v4/sports/golf_pga/events/{event_id}/odds
```

**Example Response**:
```json
{
  "id": "abc123",
  "sport_key": "golf_pga",
  "sport_title": "PGA",
  "commence_time": "2026-01-23T10:00:00Z",
  "home_team": "The American Express",
  "bookmakers": [
    {
      "key": "draftkings",
      "title": "DraftKings",
      "markets": [
        {
          "key": "h2h",
          "outcomes": [
            {
              "name": "Scottie Scheffler",
              "price": 400  // +400 American odds = 20% implied prob
            },
            {
              "name": "Jon Rahm",
              "price": 1200  // +1200 = 7.7% implied prob
            }
          ]
        }
      ]
    }
  ]
}
```

---

### Option 2: ESPN Betting Odds
**Website**: ESPN embeds odds in their golf pages

**Pros**:
- ✅ Free, no API key
- ✅ Already scraping ESPN for fields
- ✅ Simple scraping

**Cons**:
- ⚠️ Less reliable (HTML can change)
- ⚠️ Only one book (usually Caesars)
- ⚠️ No historical data

**Example URL**:
```
https://www.espn.com/golf/tournament/odds/_/id/401811929
```

---

### Option 3: DraftKings API (Direct)
**Website**: https://sportsbook.draftkings.com/golf

**Pros**:
- ✅ Free
- ✅ Real-time odds
- ✅ Good data quality

**Cons**:
- ⚠️ Unofficial API (could break)
- ⚠️ More complex scraping
- ⚠️ May violate ToS

---

## Recommended Approach: The Odds API

### Step 1: Sign Up & Get API Key

1. Go to https://the-odds-api.com
2. Sign up (free)
3. Get API key
4. Store in environment variable:
   ```bash
   export ODDS_API_KEY="your_key_here"
   ```

### Step 2: Create Odds Scraper

**File**: `scripts/scrapers/fetch_sportsbook_odds.py`

```python
import requests
import pandas as pd
import os
from datetime import datetime

def fetch_pga_odds(api_key, tournament_name=None):
    """
    Fetch PGA Tour odds from The Odds API

    Args:
        api_key: The Odds API key
        tournament_name: Optional filter for specific tournament

    Returns:
        DataFrame with player names and odds from multiple books
    """

    # Get events
    url = "https://api.the-odds-api.com/v4/sports/golf_pga/events"
    params = {
        'apiKey': api_key,
        'regions': 'us',
        'markets': 'h2h'
    }

    events = requests.get(url, params=params).json()

    # Find tournament
    if tournament_name:
        event = [e for e in events if tournament_name.lower() in e['home_team'].lower()]
        if not event:
            raise ValueError(f"Tournament '{tournament_name}' not found")
        event_id = event[0]['id']
    else:
        # Get next tournament
        event_id = events[0]['id']

    # Get odds for tournament
    odds_url = f"https://api.the-odds-api.com/v4/sports/golf_pga/events/{event_id}/odds"
    odds_data = requests.get(odds_url, params=params).json()

    # Parse odds
    players = []
    for bookmaker in odds_data.get('bookmakers', []):
        book_name = bookmaker['key']
        for market in bookmaker['markets']:
            for outcome in market['outcomes']:
                players.append({
                    'player_name': outcome['name'],
                    'bookmaker': book_name,
                    'odds_american': outcome['price'],
                    'odds_decimal': american_to_decimal(outcome['price']),
                    'implied_prob': american_to_probability(outcome['price'])
                })

    df = pd.DataFrame(players)
    return df

def american_to_decimal(american_odds):
    """Convert American odds to decimal"""
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1

def american_to_probability(american_odds):
    """Convert American odds to implied probability"""
    if american_odds > 0:
        return 100 / (american_odds + 100)
    else:
        return abs(american_odds) / (abs(american_odds) + 100)
```

### Step 3: Integrate with Prediction Pipeline

**Modify**: `scripts/predictions/predict_tournament.py`

Add odds as feature:
```python
def add_sportsbook_odds(predictions_df, odds_df):
    """
    Add sportsbook odds to predictions

    Args:
        predictions_df: Your model predictions
        odds_df: Sportsbook odds data

    Returns:
        DataFrame with odds added
    """
    # Average odds across multiple books
    avg_odds = odds_df.groupby('player_name').agg({
        'implied_prob': 'mean',
        'odds_decimal': 'mean'
    }).reset_index()

    # Merge with predictions
    merged = predictions_df.merge(
        avg_odds,
        on='player_name',
        how='left'
    )

    # Calculate value
    merged['value'] = merged['win_prob'] - merged['implied_prob']
    merged['value_pct'] = (merged['value'] / merged['implied_prob']) * 100

    return merged
```

### Step 4: Add to Dashboard

**New dashboard page**: "💰 Odds Comparison"

Shows:
- Your prediction vs Vegas odds
- Value opportunities (where you disagree most)
- Consensus vs contrarian plays
- Odds movement tracking

---

## Implementation Plan

### Phase 1: Basic Integration (2-3 hours)

**Tasks**:
1. ✅ Sign up for The Odds API
2. ✅ Create `fetch_sportsbook_odds.py`
3. ✅ Test API connection
4. ✅ Parse and store odds data
5. ✅ Add to prediction output

**Files to Create**:
- `scripts/scrapers/fetch_sportsbook_odds.py`
- `data/odds/american_express_2026_odds.csv`

**Output Example**:
```csv
player_name,draftkings_odds,fanduel_odds,betmgm_odds,avg_implied_prob,model_win_prob,value
Scottie Scheffler,+400,+425,+380,0.215,0.367,0.152
Patrick Cantlay,+2500,+2800,+2200,0.036,0.039,0.003
```

---

### Phase 2: Value Detection (1-2 hours)

**Features**:
- Identify +EV opportunities
- Flag large discrepancies (>5% difference)
- Show "Vegas agrees" vs "Vegas disagrees"
- Calculate Kelly Criterion bet sizing

**Example Output**:
```
🎯 VALUE PLAYS (Model > Vegas by 5%+)
1. Scottie Scheffler: Model 36.7%, Vegas 21.5% → +15.2% edge
2. Kurt Kitayama: Model 7.1%, Vegas 3.2% → +3.9% edge

⚠️ VEGAS DISAGREES (Vegas > Model by 5%+)
1. Rory McIlroy: Model 2.1%, Vegas 8.3% → Model undervalues by 6.2%
```

---

### Phase 3: Historical Tracking (2-3 hours)

**Features**:
- Store odds over time (Monday vs Wednesday vs Thursday)
- Track line movement
- Analyze where sharp money is going
- Compare to actual results

**Schema**: `data/odds/historical_odds.csv`
```csv
tournament,date,player_name,bookmaker,odds,implied_prob,model_prob,actual_result
American Express,2026-01-20,Scheffler,draftkings,+400,0.200,0.367,1
American Express,2026-01-22,Scheffler,draftkings,+350,0.222,0.367,1
```

**Analysis**:
- Did odds move toward your model?
- Are you consistently finding value?
- Which bookmaker has best/worst odds?

---

### Phase 4: Odds as Model Feature (4-6 hours)

**Use odds to improve predictions**:

Add features:
- `vegas_implied_prob` - Market consensus
- `odds_model_diff` - Your edge
- `odds_std` - Disagreement between books
- `line_movement` - Change from opening to closing

**Retrain models** with odds as input:
```python
features = [
    'sg_total', 'sg_ott', 'sg_app', 'sg_putt', 'sg_t2g',
    'hist_times_played', 'hist_avg_finish', 'hist_best_finish',
    'hist_wins', 'hist_top5s', 'hist_top10s',
    'venue_avg_finish', 'venue_finish_std',
    'vegas_implied_prob',  # NEW
    'odds_std'             # NEW
]
```

**Expected improvement**: 2-5% better ROC-AUC (especially for win probability)

---

## Comparison Framework

### Your Model vs Vegas

**Metrics to track**:

1. **Correlation**
   ```python
   correlation = df['win_prob'].corr(df['implied_prob'])
   # Good: 0.7-0.9
   # Excellent: 0.9+
   ```

2. **Calibration**
   - Do your 10% predictions match Vegas 10% lines?
   - Are you consistently over/under confident?

3. **Value Finding**
   ```python
   # Find where you disagree by 5%+
   value_plays = df[abs(df['win_prob'] - df['implied_prob']) > 0.05]
   ```

4. **Accuracy**
   - Who's more accurate: You or Vegas?
   - Compare Brier scores after tournament

---

## Example Output

### Enhanced Prediction Table

```
| Player | Model Win % | Vegas Win % | Diff | Value | EV |
|--------|-------------|-------------|------|-------|-----|
| Scheffler | 36.7% | 21.5% | +15.2% | 🔥 | $868K |
| Brennan | 5.5% | 4.8% | +0.7% | ✓ | $333K |
| Cantlay | 3.9% | 8.2% | -4.3% | ⚠️ | $243K |
```

**Interpretation**:
- 🔥 **Strong value** - Model much higher than Vegas (15%+ edge)
- ✓ **Slight value** - Model slightly higher (0-5% edge)
- ⚠️ **Vegas favors** - Vegas odds imply higher win rate than your model

---

## Advanced Features

### 1. Optimal Bankroll Management

Use Kelly Criterion:
```python
def kelly_criterion(edge, odds_decimal):
    """
    Calculate optimal bet size

    edge: Your probability - Implied probability
    odds_decimal: Decimal odds (e.g., 4.00 for +300)
    """
    kelly = edge / (odds_decimal - 1)
    return max(0, kelly)  # Never negative

# Example
edge = 0.367 - 0.215  # Model 36.7%, Vegas 21.5%
odds = 5.00  # +400
kelly_pct = kelly_criterion(edge, odds)  # = 3.8% of bankroll
```

### 2. Line Shopping

Compare odds across books:
```python
# Find best odds for each player
best_odds = odds_df.loc[odds_df.groupby('player_name')['odds_decimal'].idxmax()]
```

### 3. Closing Line Value (CLV)

Track if you beat the closing line:
```python
# Opening line: +400 (20% implied)
# Your bet: +400
# Closing line: +350 (22.2% implied)
# CLV: +2.2% (you got better odds than market settled on)
```

---

## Implementation Checklist

### Week 1: Basic Setup
- [ ] Sign up for The Odds API
- [ ] Get API key, add to environment
- [ ] Create `fetch_sportsbook_odds.py`
- [ ] Test with American Express
- [ ] Store odds CSV

### Week 2: Integration
- [ ] Modify `predict_tournament.py` to include odds
- [ ] Add odds comparison to output
- [ ] Calculate value metrics
- [ ] Update dashboard with odds tab

### Week 3: Analysis
- [ ] Track odds for 2-3 tournaments
- [ ] Compare predictions to Vegas
- [ ] Measure calibration
- [ ] Identify value patterns

### Week 4: Model Enhancement
- [ ] Add odds as features
- [ ] Retrain models
- [ ] Validate improvement
- [ ] Document results

---

## Cost Analysis

### The Odds API Free Tier
- **500 requests/month**
- Each tournament = 2 requests (events + odds)
- **250 tournaments per month** (way more than needed)
- Cost: **$0**

### If You Need More
**Paid tiers**:
- $25/month: 2,500 requests
- $50/month: 10,000 requests

**For PGA Tour** (40 tournaments/year):
- 80 requests/year
- Free tier is plenty!

---

## Risk Management

### Don't Over-Rely on Odds

**Remember**:
1. ✅ Use odds for **comparison**, not gospel
2. ✅ Your model has **your edge** (course history, recent form)
3. ✅ Vegas has **their edge** (more data, more bettors)
4. ⚠️ Large edges (>10%) might mean **you're wrong**, not smart

### When to Trust Your Model Over Vegas

✅ **Good reasons**:
- You have better course history data
- You're using last 5 tournaments (more recent than odds)
- Player returning from injury (odds slow to adjust)
- Small fields (less liquidity in betting markets)

⚠️ **Bad reasons**:
- "I just know this player will win"
- Ignoring large sample of bettor wisdom
- Cherry-picking only +EV bets

---

## Expected Benefits

### Calibration
- **Better probabilities** by learning from market
- **Identify biases** in your model
- **Validate assumptions**

### Value Detection
- **Find edges** where you disagree with Vegas
- **Avoid traps** where Vegas knows more than you
- **Improve picks** by combining both

### Model Improvement
- **Additional features** (odds as inputs)
- **Better predictions** (2-5% expected improvement)
- **Market validation** of your approach

---

## Next Steps

**Immediate** (this week):
1. Sign up for The Odds API
2. Test API with American Express
3. Save odds CSV alongside predictions

**Short-term** (next 2 weeks):
1. Integrate into weekly workflow
2. Add odds comparison to dashboard
3. Track for 2-3 tournaments

**Long-term** (next month):
1. Use odds as model features
2. Retrain with historical odds data
3. Measure improvement

---

## Files to Create

```
scripts/scrapers/
  └── fetch_sportsbook_odds.py       # Main odds scraper

data/odds/
  ├── american_express_2026_odds.csv # Per-tournament odds
  └── historical_odds.csv             # All historical odds

scripts/analysis/
  └── compare_model_to_vegas.py      # Analysis script

docs/
  └── ODDS_INTEGRATION_RESULTS.md    # Track performance
```

---

## Questions to Answer

After implementing, track:

1. **Correlation**: How closely do your predictions match Vegas?
2. **Calibration**: Are you over/under confident vs market?
3. **Value**: Where do you consistently find edges?
4. **Accuracy**: Who's more accurate after tournament ends?
5. **Improvement**: Does adding odds as features help?

---

**Ready to implement? Let me know and I'll create the odds scraper script!** 💰📊

*Created: January 19, 2026*
*Status: Enhancement Proposal*
*Estimated Time: 8-12 hours over 4 weeks*