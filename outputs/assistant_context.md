# Golf Model — Season Context
_Updated: 2026-10-05 16:15_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **31**
- Tournaments with results: **31**
- Top pick finished top 10: **17/31** (55%)
- Top-5 predictions → top-10 rate: **37%** (expected: ~33%)
- Average rank of actual winner in our presets: **#23.0**
- Times our #1 pick won: **7**

## Recent Tournament Results (Last 4)

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

### BMW Championship (R2026028)
- **Winner**: Wyndham Clark
- Winner was our **#13** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #12
- Top-10 predictions hit: **4/10** finished inside top 10

## Bet Performance (Recommended Bets — Priced Only)
Season totals: **4171 bets**, **736 wins** (18%), ROI **-37.7%**

| Tournament | Bets | Wins | Win% | ROI |
|---|---|---|---|---|
| R2026554 | 29 | 21 | 72.4% | +26.4% |
| R2026557 | 11 | 9 | 81.8% | +40.2% |
| R2026060 | 8 | 6 | 75.0% | +403.9% |
| R2026028 | 3 | 0 | 0.0% | -100.0% |
| R2026027 | 9 | 3 | 33.3% | -40.6% |

Note: Most bets are outright/top-10/top-20 markets. High volume because the system prices many combinations; actual staked bets are a subset.

## Closing Line Value (CLV)
CLV measures whether our model priced players better than the closing market. Positive CLV = we got value; negative = we were wrong about the price.
- Tournaments with CLV data: **13**
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
| 1 | recent_sand_save | 19.9% |
| 2 | field_avg_season_sg_ott | 4.9% |
| 3 | field_avg_season_sg_arg | 4.5% |
| 4 | recent_par4_scoring_field_pct | 4.3% |
| 5 | Total strokes gained | 3.4% |
| 6 | temp_f_avg | 3.4% |
| 7 | recent_bounce_back | 3.1% |
| 8 | dg_top10 | 3.0% |
| 9 | recent_r4_avg_field_pct | 3.0% |
| 10 | recent_sg_ott_weighted | 2.7% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
