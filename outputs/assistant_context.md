# Golf Model — Season Context
_Updated: 2026-10-12 11:06_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **32**
- Tournaments with results: **32**
- Top pick finished top 10: **18/32** (56%)
- Top-5 predictions → top-10 rate: **38%** (expected: ~33%)
- Average rank of actual winner in our presets: **#22.6**
- Times our #1 pick won: **7**

## Recent Tournament Results (Last 4)

### Baycurrent Classic (R2026527)
- **Winner**: Michael Brennan
- Winner was our **#11** ranked player pre-tournament
- Our **#1 pick**: Xander Schauffele — finished #4
- Top-10 predictions hit: **2/10** finished inside top 10

### Bank of Utah Championship (R2026554)
- **Winner**: Austin Smotherman
- Winner was our **#37** ranked player pre-tournament
- Our **#1 pick**: Jackson Koivun — finished #65
- Top-10 predictions hit: **1/10** finished inside top 10

### Biltmore Championship Asheville (R2026557)
- **Winner**: Jacob Bridgeman
- Winner was our **#1** ranked player pre-tournament
- Our **#1 pick**: Jacob Bridgeman — finished #1
- Top-10 predictions hit: **4/10** finished inside top 10

### TOUR Championship (R2026060)
- **Winner**: Scottie Scheffler
- Winner was our **#1** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #1
- Top-10 predictions hit: **5/10** finished inside top 10

## Bet Performance (Recommended Bets — Priced Only)
Season totals: **4181 bets**, **743 wins** (18%), ROI **-37.5%**

| Tournament | Bets | Wins | Win% | ROI |
|---|---|---|---|---|
| R2026527 | 10 | 7 | 70.0% | +49.3% |
| R2026554 | 29 | 21 | 72.4% | +26.4% |
| R2026557 | 11 | 9 | 81.8% | +40.2% |
| R2026060 | 8 | 6 | 75.0% | +403.9% |
| R2026028 | 3 | 0 | 0.0% | -100.0% |

Note: Most bets are outright/top-10/top-20 markets. High volume because the system prices many combinations; actual staked bets are a subset.

## Closing Line Value (CLV)
CLV measures whether our model priced players better than the closing market. Positive CLV = we got value; negative = we were wrong about the price.
- Tournaments with CLV data: **14**
- Average CLV: **+0.07pp** (percentage points vs closing line)
- % of picks with positive CLV: **72%**

**Best CLV picks this season:**
  - Scottie Scheffler (Cognizant Classic): +39.4pp
  - Rory McIlroy (Cognizant Classic): +32.9pp
  - Collin Morikawa (Cognizant Classic): +25.1pp

## Model Feature Importance (Win Probability)
What the model weighs most when ranking players this week:

| # | Feature | Importance |
|---|---|---|
| 1 | recent_sand_save | 18.8% |
| 2 | field_avg_season_sg_arg | 4.9% |
| 3 | recent_par4_scoring_field_pct | 4.4% |
| 4 | dg_top10 | 4.2% |
| 5 | recent_r4_avg_field_pct | 3.5% |
| 6 | field_median_rank | 3.3% |
| 7 | recent_sg_ott_weighted | 3.2% |
| 8 | temp_f_avg | 3.2% |
| 9 | recent_bounce_back | 2.8% |
| 10 | Total strokes gained | 2.8% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
