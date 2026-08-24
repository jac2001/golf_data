# Golf Model — Season Context
_Updated: 2026-08-24 08:13_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **26**
- Tournaments with results: **26**
- Top pick finished top 10: **14/26** (54%)
- Top-5 predictions → top-10 rate: **38%** (expected: ~33%)
- Average rank of actual winner in our presets: **#24.9**
- Times our #1 pick won: **4**

## Recent Tournament Results (Last 4)

### BMW Championship (R2026028)
- **Winner**: Wyndham Clark
- Winner was our **#13** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #12
- Top-10 predictions hit: **4/10** finished inside top 10

### 3M Open (R2026525)
- **Winner**: Jackson Koivun
- Winner was our **#17** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #2
- Top-10 predictions hit: **3/10** finished inside top 10

### The Open Championship (R2026100)
- **Winner**: Ryan Fox
- Winner was our **#57** ranked player pre-tournament
- Our **#1 pick**: Rory McIlroy — finished #40
- Top-10 predictions hit: **4/10** finished inside top 10

### Genesis Scottish Open (R2026541)
- **Winner**: Tom Kim
- Winner was our **#28** ranked player pre-tournament
- Our **#1 pick**: Rory McIlroy — finished #7
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
- Tournaments with CLV data: **11**
- Average CLV: **+0.07pp** (percentage points vs closing line)
- % of picks with positive CLV: **71%**

**Best CLV picks this season:**
  - Scottie Scheffler (Cognizant Classic): +39.4pp
  - Rory McIlroy (Cognizant Classic): +32.9pp
  - Collin Morikawa (Cognizant Classic): +25.1pp

## Model Feature Importance (Win Probability)
What the model weighs most when ranking players this week:

| # | Feature | Importance |
|---|---|---|
| 1 | dg_fit_arg | 13.3% |
| 2 | recent_sg_arg_weighted | 9.6% |
| 3 | field_avg_season_sg_putt | 6.1% |
| 4 | recent_sg_trend | 4.5% |
| 5 | recent_sg_ott_weighted | 3.9% |
| 6 | field_avg_season_sg_ott | 2.9% |
| 7 | recent_par3_scoring_field_pct | 2.5% |
| 8 | hist_top5s | 2.3% |
| 9 | wind_mph_avg | 2.3% |
| 10 | dg_fit_putt | 2.2% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
