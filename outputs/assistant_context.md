# Golf Model — Season Context
_Updated: 2026-07-06 12:19_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **19**
- Tournaments with results: **19**
- Top pick finished top 10: **10/19** (53%)
- Top-5 predictions → top-10 rate: **40%** (expected: ~33%)
- Average rank of actual winner in our presets: **#26.5**
- Times our #1 pick won: **3**

## Recent Tournament Results (Last 4)

### Travelers Championship (R2026034)
- **Winner**: Viktor Hovland
- Winner was our **#1** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #1
- Top-10 predictions hit: **2/10** finished inside top 10

### U.S. Open (R2026026)
- **Winner**: Wyndham Clark
- Winner was our **#67** ranked player pre-tournament
- Our **#1 pick**: Rory McIlroy — finished #32
- Top-10 predictions hit: **1/10** finished inside top 10

### The Memorial Tournament (R2026023)
- **Winner**: J.T. Poston
- Winner was our **#50** ranked player pre-tournament
- Our **#1 pick**: Rory McIlroy — finished #12
- Top-10 predictions hit: **1/10** finished inside top 10

### Charles Schwab Challenge (R2026021)
- **Winner**: Russell Henley
- Winner was our **#4** ranked player pre-tournament
- Our **#1 pick**: Justin Thomas — finished #13
- Top-10 predictions hit: **3/10** finished inside top 10

## Bet Performance (Recommended Bets — Priced Only)
Season totals: **4069 bets**, **674 wins** (17%), ROI **-39.6%**

| Tournament | Bets | Wins | Win% | ROI |
|---|---|---|---|---|
| R2026014 | 28 | 14 | 50.0% | +27.2% |
| R2026041 | 641 | 143 | 22.3% | -34.6% |
| R2026020 | 235 | 56 | 23.8% | -33.7% |
| R2026475 | 363 | 64 | 17.6% | -64.0% |
| R2026011 | 934 | 155 | 16.6% | -21.1% |

Note: Most bets are outright/top-10/top-20 markets. High volume because the system prices many combinations; actual staked bets are a subset.

## Closing Line Value (CLV)
CLV measures whether our model priced players better than the closing market. Positive CLV = we got value; negative = we were wrong about the price.
- Tournaments with CLV data: **10**
- Average CLV: **+0.11pp** (percentage points vs closing line)
- % of picks with positive CLV: **72%**

**Best CLV picks this season:**
  - Scottie Scheffler (Cognizant Classic): +39.4pp
  - Rory McIlroy (Cognizant Classic): +32.9pp
  - Collin Morikawa (Cognizant Classic): +25.1pp

## Model Feature Importance (Win Probability)
What the model weighs most when ranking players this week:

| # | Feature | Importance |
|---|---|---|
| 1 | recent_r4_avg_field_pct | 12.1% |
| 2 | season_sg_ott_field_pct | 7.7% |
| 3 | field_avg_season_sg_ott | 6.1% |
| 4 | dg_top10 | 5.0% |
| 5 | Off-the-tee (SG:OTT season avg) | 4.5% |
| 6 | recent_par5_scoring_field_pct | 4.4% |
| 7 | hist_avg_finish | 4.4% |
| 8 | Recent form trend | 3.9% |
| 9 | wind_mph_avg | 3.5% |
| 10 | recent_sg_ott_weighted | 3.2% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
