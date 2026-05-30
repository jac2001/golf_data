# Golf Model — Season Context
_Updated: 2026-05-17 21:06_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **12**
- Tournaments with results: **12**
- Top pick finished top 10: **7/12** (58%)
- Top-5 predictions → top-10 rate: **45%** (expected: ~33%)
- Average rank of actual winner in our presets: **#20.8**
- Times our #1 pick won: **2**

## Recent Tournament Results (Last 4)

### Truist Championship (R2026480)
- **Winner**: Kristoffer Reitan
- Winner was our **#35** ranked player pre-tournament
- Our **#1 pick**: Rory McIlroy — finished #19
- Top-10 predictions hit: **4/10** finished inside top 10

### RBC Heritage (R2026012)
- **Winner**: Matt Fitzpatrick
- Winner was our **#2** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #2
- Top-10 predictions hit: **4/10** finished inside top 10

### Masters (R2026014)
- **Winner**: Rory McIlroy
- Winner was our **#3** ranked player pre-tournament
- Our **#1 pick**: Scottie Scheffler — finished #2
- Top-10 predictions hit: **5/10** finished inside top 10

### Valero Texas Open (R2026041)
- **Winner**: J.J. Spaun
- Winner was our **#13** ranked player pre-tournament
- Our **#1 pick**: Ludvig Åberg — finished #5
- Top-10 predictions hit: **4/10** finished inside top 10

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
- Tournaments with CLV data: **9**
- Average CLV: **+0.16pp** (percentage points vs closing line)
- % of picks with positive CLV: **75%**

**Best CLV picks this season:**
  - Scottie Scheffler (Cognizant Classic): +39.4pp
  - Rory McIlroy (Cognizant Classic): +32.9pp
  - Collin Morikawa (Cognizant Classic): +25.1pp

## Model Feature Importance (Win Probability)
What the model weighs most when ranking players this week:

| # | Feature | Importance |
|---|---|---|
| 1 | recent_r4_avg_field_pct | 10.4% |
| 2 | Putting (SG:PUTT season avg) | 7.2% |
| 3 | hist_top5s | 5.6% |
| 4 | season_sg_app_vs_field | 3.5% |
| 5 | recent_sg_ott_weighted | 2.9% |
| 6 | dg_win | 2.8% |
| 7 | Recent SG (weighted last 5 events) | 2.6% |
| 8 | World ranking (log-scaled) | 2.5% |
| 9 | has_course_history | 2.4% |
| 10 | recent_par4_scoring_field_pct | 2.4% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
