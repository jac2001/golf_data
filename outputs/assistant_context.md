# Golf Model — Season Context
_Updated: 2026-04-20 08:05_

## Season Summary (2026 PGA Tour)
- Tournaments tracked: **11**
- Tournaments with results: **11**
- Top pick finished top 10: **7/11** (64%)
- Top-5 predictions → top-10 rate: **45%** (expected: ~33%)
- Average rank of actual winner in our presets: **#19.5**
- Times our #1 pick won: **2**

## Recent Tournament Results (Last 4)

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

### Texas Children's Houston Open (R2026020)
- **Winner**: Gary Woodland
- Winner was our **#56** ranked player pre-tournament
- Our **#1 pick**: Chris Gotterup — finished #6
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
- Tournaments with CLV data: **8**
- Average CLV: **+0.13pp** (percentage points vs closing line)
- % of picks with positive CLV: **73%**

**Best CLV picks this season:**
  - Scottie Scheffler (Cognizant Classic): +39.4pp
  - Rory McIlroy (Cognizant Classic): +32.9pp
  - Collin Morikawa (Cognizant Classic): +25.1pp

## Model Feature Importance (Win Probability)
What the model weighs most when ranking players this week:

| # | Feature | Importance |
|---|---|---|
| 1 | Approach play (SG:APP season avg) | 12.4% |
| 2 | Recent form trend | 9.1% |
| 3 | season_sg_app_field_pct | 5.9% |
| 4 | Has SG history at this course | 5.3% |
| 5 | has_made_cut_here | 3.9% |
| 6 | season_sg_ott_vs_field | 3.8% |
| 7 | Recent SG (weighted last 5 events) | 3.7% |
| 8 | recent_par3_scoring_field_pct | 3.3% |
| 9 | Off-the-tee (SG:OTT season avg) | 2.9% |
| 10 | hist_times_played | 2.6% |

## Model Architecture Notes
- 4 XGBoost models: win, top-5, top-10, top-20 probability
- Trained on 2016-2026 PGA Tour data (~46K tournament-player rows)
- Calibrated with isotonic regression; win prob capped at 20%
- Post-processing: course win boost → elite market blend (top-15, 25% max) → expert consensus blend (12%)
- SHAP values computed on this week's field to explain each player's ranking
- Retrain trigger: every 4 tournaments (auto via scheduled_refresh.py)
