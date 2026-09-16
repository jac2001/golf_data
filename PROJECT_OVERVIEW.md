# Golf Analytics & Betting Dashboard — Project Overview

A personal golf analytics platform that ingests real-time PGA Tour data, runs machine learning prediction models, generates betting recommendations, and manages a season-long fantasy "Let It Ride" league. Built across a Python/FastAPI backend and a Next.js web frontend.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Tech Stack](#tech-stack)
3. [Directory Structure](#directory-structure)
4. [Data Sources](#data-sources)
5. [The Full Prediction Pipeline](#the-full-prediction-pipeline)
6. [Machine Learning Models](#machine-learning-models)
7. [Monte Carlo Simulation](#monte-carlo-simulation)
8. [Betting System](#betting-system)
9. [Fantasy League System](#fantasy-league-system)
10. [Web Dashboard](#web-dashboard)
11. [Database (DuckDB)](#database-duckdb)
12. [Automation & Scheduler](#automation--scheduler)
13. [AI Features](#ai-features)
14. [Post-Tournament Pipeline](#post-tournament-pipeline)
15. [Critical Design Decisions](#critical-design-decisions)
16. [Known Limitations](#known-limitations)
17. [Weekly Workflow](#weekly-workflow)
18. [Running the Servers](#running-the-servers)

---

## What It Does

Each week of the PGA Tour season, the system:

1. **Fetches** field data, player stats, live odds, and course fit scores from DataGolf, DraftKings, and PGA Tour
2. **Builds** a feature matrix combining season SG, recent form, course history, and DataGolf course fit per player
3. **Runs** four XGBoost classifiers to predict win/top5/top10/top20 probabilities
4. **Simulates** the tournament 10,000 times using Monte Carlo to capture variance (boom-or-bust players)
5. **Compares** model probabilities to sportsbook lines to find positive expected-value bets
6. **Generates** a recommended weekly lineup for a fantasy "Let It Ride" league (3 uses per player, 3 picks per week)
7. **Tracks** live tournament scores and updates predictions hourly during rounds
8. **Notifies** via email + dashboard card with the best bet of the week
9. **Settles** results after the tournament: grades bets, logs P&L, updates fantasy tracker, syncs to DuckDB

The dashboard is a web app (Next.js + FastAPI) that surfaces everything in real time, with an AI chatbot for natural language Q&A.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (React, TypeScript) — App Router |
| Backend API | FastAPI (Python), port 8000 |
| ML Models | XGBoost (sklearn pipeline), Random Forest |
| Simulation | NumPy Monte Carlo (10,000 tournament sims) |
| Database | DuckDB — historical data, career stats, bet log |
| AI / LLM | Anthropic Claude (Haiku for speed, Sonnet for quality) |
| Web Search | Tavily / DuckDuckGo (injury news, storylines) |
| Scheduling | macOS cron + custom Python scheduler |
| Data Storage | CSV (live/current week), DuckDB (historical) |

---

## Directory Structure

```
golf_data/
├── api/
│   └── main.py                        # FastAPI app — all backend endpoints
├── web/                               # Next.js frontend
│   ├── app/                           # App Router pages
│   │   ├── live/page.tsx              # Live leaderboard + scorecards
│   │   ├── betting/page.tsx           # Value bets, matchups, odds explorer
│   │   ├── predictions/page.tsx       # Full field prediction table
│   │   ├── players/page.tsx           # Player lookup, H2H, career stats
│   │   ├── history/page.tsx           # Past results, tournament leaderboards
│   │   ├── mypicks/page.tsx           # Fantasy tracker + season strategy
│   │   └── assistant/page.tsx         # AI chatbot
│   └── lib/api.ts                     # All fetch functions + TypeScript types
├── scripts/
│   ├── run_pipeline.py                # Full weekly pipeline orchestrator
│   ├── scheduled_refresh.py           # Hourly background scheduler
│   ├── post_tournament.py             # Settlement: grade bets, sync DB, tracker
│   ├── scrapers/                      # Data fetchers
│   │   ├── dg_client.py               # DataGolf API (rate-limited — use this, never raw requests)
│   │   ├── fetch_live_leaderboard.py  # PGA Tour live scores
│   │   ├── fetch_hole_scores.py       # Hole-by-hole data via GraphQL
│   │   ├── fetch_past_results.py      # Settled tournament results
│   │   ├── fetch_dg_odds.py           # DG odds (12+ books) for all markets
│   │   └── fetch_expert_picks_pga.py  # DFS expert consensus picks
│   ├── features/
│   │   └── merge_all_historical_data.py  # Builds master training CSV
│   ├── predictions/
│   │   ├── predict_tournament.py      # Inference: runs models → latest_predictions.csv
│   │   ├── calibration.py             # ProbabilityCalibrator class
│   │   ├── season_strategy.py         # Fantasy lineup optimizer
│   │   └── simulate_tournament.py     # Monte Carlo simulation engine
│   ├── models/
│   │   └── recommend_bets.py          # Bet recommendation engine
│   ├── validation/
│   │   └── train_final_models.py      # Model training script
│   └── database/
│       ├── db.py                      # DuckDB connection helper
│       ├── schema.py                  # Table definitions (run once)
│       └── backfill_rounds.py         # One-time: populate r1-r4 from CSVs
├── data/
│   ├── datagolf/                      # DG API outputs (refreshed weekly)
│   ├── fields/                        # field_R{tid}.csv — current field
│   ├── live/                          # leaderboard_r{tid}.csv + _meta.json
│   ├── historical/                    # leaderboards_{year}.csv — settled results
│   ├── odds/                          # DK/DG odds, recommended bets, snapshots
│   ├── fantasy/                       # usage_tracker_2026.json, standings, picks
│   ├── processed/                     # master_training_data_2016_2026.csv, player_variance.csv
│   ├── models/                        # win/top5/top10/top20_model_final.pkl
│   └── golf_data.db                   # DuckDB file
└── outputs/
    ├── latest_predictions.csv         # PRIMARY: current tournament, ~140 players, 283 cols
    └── recommended_bets_*.csv         # Ranked bet list per tournament
```

---

## Data Sources

### DataGolf (`scripts/scrapers/dg_client.py`)

All DataGolf requests go through `dg_get()` — never make direct HTTP calls. It handles rate limiting.

| File | Updated | Content |
|------|---------|---------|
| `dg_outrights_R*.csv` | Tue/Thu | Win/top5/top10/top20/make_cut odds, 12+ books + DG model probs |
| `dg_matchups_R*.csv` | Tue/Thu | Round H2H matchup odds from 6+ books |
| `dg_pre_tournament_latest.csv` | Tue | DG pre-tournament predictions (baseline) |
| `dg_skill_ratings_latest.csv` | Weekly | Career skill ratings per player |
| `dg_approach_skill_l24.csv` | Weekly | Approach shot skill (last 24 rounds) |
| `dg_decompositions_latest.csv` | Tue | Course fit decomposition — `final_pred`, `std_deviation` |
| `dg_live_stats_R*_latest.csv` | Hourly | Live SG stats during rounds |
| `dg_course_fit_latest.csv` | Tue | Course fit scores per player |

**Key DG fields used in predictions:**
- `final_pred` — DG's full course-adjusted expected SG per round. Used as the primary `mu` in simulation when >50% field coverage.
- `std_deviation` — DG's per-round scoring SD. Used as `sigma` in simulation when available.
- `baseline_pred` — skill-only prediction (no course fit). Difference from `final_pred` is the course fit delta.

### DraftKings

- **Outright winner + Top 5/10/20:** Main eventgroup endpoint — working
- **Matchups / 3-ball / make_cut subcategories:** 403 blocked — use DataGolf odds instead
- **Manual export:** `fetch_draftkings_props.py --input-json <devtools_export>` for blocked markets

### PGA Tour

- **Live leaderboard:** Scrapes `__NEXT_DATA__` JSON from pgatour.com
- **Hole scores:** PGA Tour GraphQL API (`fetch_hole_scores.py`)
- **Weather:** Open-Meteo API (free) — 7-day forecast per course coordinates

### Other
- Expert picks: scrapes consensus DFS lineups (`fetch_expert_picks_pga.py`)
- Fantasy usage: league weekly picks from tracker JSON
- Course characteristics: par, yardage, hole difficulty per course

---

## The Full Prediction Pipeline

This is the most important section — how raw data becomes `outputs/latest_predictions.csv`.

### Step 1 — Build the Feature Matrix (`predict_tournament.py`)

`build_feature_matrix(tid)` assembles one row per player from multiple sources:

```
field_R{tid}.csv           →  player list (who's playing)
DuckDB: tournament_stats   →  season SG (OTT, APP, ARG, PUTT, T2G) from prior events
DuckDB: form_stats         →  recent form: scoring avg, birdie %, GIR %
DuckDB: course_performance →  per-player per-course history (starts, cuts, avg finish, course SG)
data/datagolf/*.csv        →  DG skill ratings, course fit, decompositions
outputs/latest_*           →  expert picks blend weight
```

**SG event count penalty** — Players with < 10 events of SG history have their season SG regressed toward the field mean. Confidence = events / 10. Applies to `season_sg_total`, `season_sg_arg`, `predictive_sg_weighted`. This prevents a player with 3 events of great golf from looking like a world-beater.

### Step 2 — Feature Groups

| Group | Features | Why Included |
|-------|----------|-------------|
| Season SG | `season_sg_total/ott/app/arg/putt` + field %ile variants | Best long-term skill signal |
| Predictive SG | `predictive_sg_weighted` (DG weights: OTT×1.2, APP×1.0, ARG×0.9, PUTT×0.6) | DataGolf-calibrated composite — #2 feature |
| Recent form | `recent_sg_weighted` (exp decay 0.85), `recent_sg_trend` | Captures hot/cold streaks |
| World rank | `world_rank_log` = log1p(rank) | #1 feature. Log transform reduces rank-1 dominance. |
| Course history | `hist_top10s`, `hist_made_cut_rate`, `venue_avg_finish` | Course familiarity edge |
| Course fit (DG) | `dg_fit_ott/app/arg/putt/total` | DG's model of how player's game matches course demands |
| Non-SG stats | Driving distance, accuracy, GIR%, scrambling, sand save | Situation-specific signals |
| Field context | Every stat expressed vs. field mean and percentile rank | Relative value, not absolute |

**Excluded features and why:**
- `sg_total`, `sg_ott` etc. (per-tournament SG) — DATA LEAKAGE. These are from the tournament being predicted.
- `fit_*`, `course_fit_total` (old course fit) — computed from per-tournament SG, so also leaky.
- `course_sg_*` — confirmed 0% feature importance across all models. Pure noise.
- `*_vs_field` SG variants — r=0.96–0.99 correlated with raw values. No new information, just redundant levers.

### Step 3 — XGBoost Inference

Four pre-trained models each call `predict_proba()` on the feature matrix:
- `win_model_final.pkl` → `win_prob_raw`
- `top5_model_final.pkl` → `top5_prob_raw`
- `top10_model_final.pkl` → `top10_prob_raw`
- `top20_model_final.pkl` → `top20_prob_raw`

### Step 4 — Post-Processing (order matters)

```
Raw XGBoost probabilities
  1. ProbabilityCalibrator.calibrate()
       Scales toward historical base rates.
       Hard cap: MAX_WIN_PROB = 0.20 (prevents 29%+ outliers)
       Multipliers: top5/10/20 ≈ 1.01–1.08x (excellent), win ≈ 1.34x (moderate)

  2. Course win boost
       Players with strong course history at this specific venue get a small uplift

  3. Course performance adjustment
       Applies course_sg_total_vs_avg signals from player_course_performance.csv
       Deduplication: keeps row with most course_sg_total_rounds (not a single 2026 entry)

  4. KFT penalty
       Lower-ranked / Korn Ferry Tour players get a small downward adjustment

  5. Probability constraints
       Ensures probabilities are monotone: win ≤ top5 ≤ top10 ≤ top20

  6. EV calculation
       expected_value = model_prob × payout - (1 - model_prob) × stake

  7. Odds + elite market blend (top-15 players, 25% max weight)
       Blends model probs 75% toward DK/DG implied probs for top-15 ranked players
       Prevents model from being wildly wrong on chalk

  8. Expert consensus blend (12% weight)
       Reads data/expert_picks/expert_picks_{tid}.csv
       Blends 12% toward expert distribution — catches model blind spots
       Name format handled: expert picks use "First Last", predictions use "Last, First"

  9. Save to outputs/latest_predictions.csv
```

### Step 5 — Monte Carlo Simulation (`simulate_tournament.py`)

Runs after predictions (see full section below). Adds `win_prob_sim`, `top10_prob_sim`, `make_cut_prob_sim` columns.

---

## Machine Learning Models

### Training (`scripts/validation/train_final_models.py`)

**Training data:** `data/processed/master_training_data_2016_2026.csv`
- 46,000 rows, one per player per tournament
- 108 features
- Built by `scripts/features/merge_all_historical_data.py`

**Algorithm:** Random Forest with isotonic regression calibration (`CalibratedClassifierCV`)

**Hyperparameters:**
- `n_estimators=100`, `max_depth=5`, `min_samples_split=50`, `min_samples_leaf=25`
- Shallow trees + high leaf minimums = the primary overfitting control
- `class_weight='balanced_subsample'` — handles severe class imbalance (wins ≈ 0.7% of rows)

**Train/test split:** Year-based (not random)
- Train: 2016–2024
- Test: 2025
- Year-based splitting is essential — random splits would leak future data into training

**Reported test AUC (2025):**
- Win: ~0.74, Top5: ~0.75, Top10: ~0.76, Top20: ~0.73

**Known validation limitation:** Step 3a in the training script uses 2025 (test) data to decide whether to keep `dg_fit_*` features. This makes the reported 2025 AUC mildly optimistic (estimated ~0.005–0.01). Not severe enough to fix before a major retrain, but a known issue. The correct fix is a 3-way split: train/val/test, where all feature decisions are made on val (2023–2024) and test (2025) is touched exactly once.

### Feature Importance (top features)

| Rank | Feature | Why |
|------|---------|-----|
| 1 | `world_rank_log` | Best single-number summary of player quality |
| 2 | `predictive_sg_weighted` | DG-weighted SG composite — captures game-type fit |
| 3 | `season_sg_total` | Long-run skill, stable |
| 4 | `recent_sg_weighted` | Hot/cold streaks that season avg misses |
| 5 | `dg_fit_total` | Course type fit — significant at course-specific events |

---

## Monte Carlo Simulation

### Why Simulation?

XGBoost predicts win probability by pattern-matching features. It cannot distinguish between two players with the same mean SG but different round-to-round consistency. A volatile player (high variance) wins more often than their average SG predicts, because golf rewards whoever gets hot that week. Simulation models this correctly.

### How It Works (`scripts/predictions/simulate_tournament.py`)

**Step 1 — Build player mu (expected round SG)**
```
Priority 1: DG's final_pred (course-adjusted expected SG per round) — used when >50% field coverage
Priority 2: predictive_sg_weighted × 0.70 + recent_sg_weighted × 0.30 + dg_fit_total

Field-normalised: mu = mu - mean(mu) so field_mean(mu) = 0
```

**Step 2 — Build player sigma (round-to-round variability)**
```
Priority 1: DG's std_deviation from decompositions
Priority 2: Historical round SD from player_variance.csv (computed from master training data)
Priority 3: World-rank tier defaults:
    Top 50:    sigma ≈ 2.85 strokes/round
    50–150:    sigma ≈ 3.05
    150+:      sigma ≈ 3.20
```

**Step 3 — Simulate 10,000 tournaments**
```python
for each simulation:
    R1 ~ Normal(mu, sigma)
    R2 ~ Normal(mu, sigma) + 0.06 × (R1 - mu)   # 0.06 autocorrelation: hot players stay slightly hot
    Cut: retain top 65 by R1+R2
    R3 ~ Normal(mu, sigma) + 0.06 × (R2 - mu)   # survivors only
    R4 ~ Normal(mu, sigma) + 0.06 × (R3 - mu)
    Count wins, top5, top10, top20, make_cut
```

**Output:** `win_prob_sim`, `top5_prob_sim`, `top10_prob_sim`, `top20_prob_sim`, `make_cut_prob_sim`
Written back to `outputs/latest_predictions.csv`.

**How it's used:**
- API sorts prediction table by `win_prob_sim` when available
- `make_cut_prob_sim` is the most accurate make-cut signal — feeds make_cut bet recommendations
- `win_prob_sim` vs `win_prob_xgb` gap reveals player type: sim >> xgb = volatile/boom-bust; sim << xgb = consistent grinder
- Intel agent uses `win_prob_sim` as primary sort when building player context

**Guard:** The simulation requires `final_pred` coverage > 50%. If DG data hasn't been fetched, it raises `InsufficientDGDataError` and the pipeline skips it gracefully without failing.

---

## Betting System

### Recommendation Engine (`scripts/models/recommend_bets.py`)

**Markets covered:**
- Outright winner, Top 5, Top 10, Top 20, Make Cut (pool markets)
- R1/R2/R3/R4 H2H matchups (from DG matchup odds)
- 3-ball group winner

**Edge calculation:**

For pool markets (win/top5/top10/top20/make_cut):
```
book_implied = 1 / decimal_odds
no_vig_prob  = de-vig the book's implied (normalize across all players)
edge         = model_prob - no_vig_prob
EV           = edge × decimal_odds
```

For H2H:
```
no_vig_prob = p1_implied / (p1_implied + p2_implied)   # removes vig by normalizing the pair
edge        = model_prob - no_vig_prob
```

**Odds source priority:**
1. DataGolf outrights (12 books: Pinnacle, Bet365, BetMGM, Caesars, DK, FanDuel, Bovada...)
2. DraftKings prop_lines CSV
3. PGA Tour GraphQL (outright winner + movement direction ▲/▼/→)

**Output:** `data/odds/recommended_bets_R{tid}.csv` — ranked by `confidence × EV`

**Thresholds (Tuesday run):** min edge 0.75pp, min confidence 0.45, max 40 recommendations

### Best Bet Notification (`scripts/notifications/send_best_bet.py`)

1. Load recommendations, filter to ≤+2500 odds (removes longshot outliers)
2. Rank by `confidence × EV`
3. Call Claude Haiku to generate 3–4 sentence reasoning
4. Save to `outputs/best_bet.json`
5. Send email via Gmail SMTP

**Dashboard card:** The `/betting` page shows a featured green card at the top with the best bet + reasoning. Stale check: card is hidden if `best_bet.json` is from a different tournament than current.

### Bet Grading (`post_tournament.py` → `step_grade_bets`)

After tournament settlement:
- Pool markets: grade by final position vs. threshold (top10 = pos ≤ 10, make_cut = pos ≠ 999)
- H2H: compare final positions (or round scores for `h2h_r1` etc.)
- 3-ball / group winner: marked manual — require pairing data
- P&L computed: won → `stake × (decimal_odds - 1)`, lost → `-stake`
- Results written to `data/odds/recommended_bets_log.csv` + `recommended_bets_log` DuckDB table

---

## Fantasy League System

### Rules
- **3 uses per player** for the entire season (~30 tournaments)
- **3 players per weekly lineup**
- Track earnings per player use
- Data lives in `data/fantasy/usage_tracker_2026.json`

### Season Strategy (`scripts/predictions/season_strategy.py`)

`get_season_strategy()` optimizes each player's remaining use allocation:

1. Compute `this_week_ev` — expected value of using this player this week
2. Compute `best_future_ev` — best EV across all their remaining future events
3. Compute `opportunity_cost_ev` — what you give up by using them now
4. Signal `use_this_week` (bool) based on: EV, course fit, uses remaining, hot streak, opportunity cost

**Name resolution:** Fantasy tracker stores last-name-only keys (`"McIlroy"`). Predictions use `"Last, First"` format. `_resolve_key()` in `season_strategy.py` builds a last-token → full-key lookup. **Never bypass `_resolve_key()`** — without it, all strategy players show blank data.

### Fantasy Data Files

| File | Content |
|------|---------|
| `usage_tracker_2026.json` | Per-player use counts, remaining uses, results per tournament |
| `league_weekly_picks.csv` | All picks across all weeks |
| `league_standings.csv` | Season standings |
| `league_player_usage.csv` | Usage frequency across league members |

---

## Web Dashboard

### Pages

| Route | Page | Key Features |
|-------|------|-------------|
| `/live` | Live Leaderboard | Real-time scores, scorecards, hole-by-hole, movement arrows, cut line, Live Pulse AI narrative |
| `/betting` | Value Bets | Best Bet card, bet cards by market, matchups (DG 3-ball + H2H), odds explorer, book comparison |
| `/predictions` | Predictions Table | Full field, win/top10/top20/sim probs, filter + sort |
| `/players` | Player Search | Profile, career history (by year + recent starts), H2H comparison, course history, MY PICK badges |
| `/history` | Season History | Past tournaments, clickable rows expand to full leaderboard with r1–r4 |
| `/mypicks` | My Picks | Fantasy usage tracker, weekly lineup log, season strategy card |
| `/assistant` | AI Chatbot | Natural language Q&A, streaming, full tournament context |

### Players Page — Career Stats

The Players page pulls from two separate sources:

- **Current week profile** (`/api/players/profile`) — reads `latest_predictions.csv` + DG data. Only works for players in the current field.
- **Career history** (`/api/players/career`) — reads from DuckDB `leaderboards` + `tournament_stats`. Works for any of the 1,747 players in the database going back to 2016.

The career card has two views:
- **By Year:** Starts, wins, top10s, top25s, cuts made, avg SG total/OTT/APP/PUTT per year
- **Recent Starts:** Last 50 tournaments with r1–r4 round scores. Rows are expandable — clicking shows the full tournament leaderboard (lazy loaded, MY PICK highlighted).

### History Page — Tournament Detail

Clicking a past tournament expands to a full leaderboard table: position, player, R1/R2/R3/R4, total, earnings. Sorted by position using `REGEXP_EXTRACT(position, '[0-9]+')` to correctly handle T-prefix formats like "T3", "T14".

Reads from DuckDB `leaderboards` table, not CSVs.

### Frontend Architecture

- **All API calls:** `web/lib/api.ts` — single source of truth for fetch functions and TypeScript types
- **Styling:** Inline CSS-in-JS, no framework. Dark theme throughout.
- **Color palette:** `#0d1a30` bg, `#dde6f5` text, `#00c44f` green, `#e74c3c` red, `#4cb8ff` blue, `#f1c40f` gold
- **No nested `<Suspense>` in expanders** — Streamlit-era rule carried forward: no nested expanders

### Name Normalisation Across Formats

Player names appear in three formats across data sources:
- `"Last, First"` — `latest_predictions.csv`, picks tracker
- `"First Last"` — DuckDB leaderboards, DataGolf, PGA Tour
- `"Last"` only — fantasy usage tracker

**Solution — sorted-token key:**
```
normName("McIlroy, Rory")  →  "mcilroy rory"
normName("Rory McIlroy")   →  "mcilroy rory"
```
Frontend: `normName()` in `page.tsx`. Backend: `_name_key()` in `season_strategy.py` and `_norm_name()` in `post_tournament.py`.

For the fantasy tracker (last-name-only), `_resolve_key()` builds a last-token → full-key lookup as an extra bridging step.

### Backend API (`api/main.py`)

Key endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/tournament` | Current tournament info + phase |
| `GET /api/predictions` | Full prediction table |
| `GET /api/bets` | Recommended bets (filterable by market) |
| `GET /api/bets/best` | Best bet of the week |
| `GET /api/live/inplay` | Live leaderboard with win/top10 probs |
| `GET /api/live/pulse` | AI tournament narrative (cached 30min) |
| `GET /api/live/hole-scores` | Hole-by-hole scorecard data |
| `GET /api/matchups` | DG H2H matchup odds |
| `GET /api/odds/comparison` | Multi-book odds table |
| `GET /api/players/list` | Players in current field (~140) |
| `GET /api/players/all` | All players in DuckDB (~1,747) |
| `GET /api/players/profile` | Full player profile (current week) |
| `GET /api/players/career` | Career history from DuckDB |
| `GET /api/history/tournaments` | All settled 2026 tournaments |
| `GET /api/history/tournament/{tid}` | Full leaderboard for one tournament |
| `GET /api/lineup` | Season strategy recommendation |
| `POST /api/chat` | AI chatbot (streaming SSE) |

---

## Database (DuckDB)

**File:** `data/golf_data.db`
**Connection:** `scripts/database/db.py` → `get_conn(read_only=False)`
**Schema:** `scripts/database/schema.py` — run once to create/verify tables

**Key principle:** DuckDB is backend only. The dashboard reads CSVs. DuckDB serves historical queries, career stats, and the leaderboard detail endpoints.

### Tables

| Table | Rows | Content |
|-------|------|---------|
| `leaderboards` | ~48,000 | Final results per player per tournament, 2012–2026. Includes r1/r2/r3/r4 round scores. |
| `tournament_stats` | ~452,000 | Per-tournament per-player SG stats (long format: one row per stat). Stat IDs: 2567=SG Total, 2568=OTT, 2569=APP, 2564=PUTT |
| `form_stats` | ~618,000 | Rolling/seasonal form stats (stat_id 120=scoring_avg, 108=birdie_pct, 103=GIR%) |
| `course_performance` | ~9,900 | Historical per-player per-course metrics (SG avg, cut rate, top10 rate) |
| `players` | ~2,000 | Player master table with world rank |
| `dg_players` | ~3,400 | DataGolf player registry |
| `dg_rankings` | — | Weekly DG ranking snapshots |
| `dg_decompositions` | — | Per-tournament prediction decomposition |
| `prediction_history` | ~2,000 | Model predictions per player per tournament + actual results |
| `recommended_bets_log` | ~760 | All bet recommendations with graded outcomes + P&L |
| `live_leaderboard` | — | Latest live snapshot per player per tournament |
| `live_stats` | — | DG live SG stats per player per round |
| `live_pulse` | — | Cached AI narratives per round |
| `conversation_log` | ~115 | Chatbot Q&A history |
| `picks` | — | Weekly fantasy lineup picks + results |

### Round Scores in DuckDB

The `leaderboards` table has `r1`, `r2`, `r3`, `r4` columns (DOUBLE). These were backfilled from historical CSVs via `scripts/database/backfill_rounds.py` (46,747 rows updated across 2012–2026).

**Data gaps:** 5 tournaments in 2026 have no round scores in DuckDB because the source CSVs never had them (PLAYERS Championship, RBC Heritage, Texas Children's Houston Open, Valspar, Arnold Palmer Invitational). Total score and position are correct for these — only round-by-round data is missing.

### Key SQL Patterns

**Pivot long-format stats to wide (avoid JOIN multiplication):**
```sql
SELECT player_id, tournament_id,
    AVG(CASE WHEN stat_id = '2567' THEN stat_value END) AS sg_total,
    AVG(CASE WHEN stat_id = '2568' THEN stat_value END) AS sg_ott,
    AVG(CASE WHEN stat_id = '2569' THEN stat_value END) AS sg_app,
    AVG(CASE WHEN stat_id = '2564' THEN stat_value END) AS sg_putt
FROM tournament_stats
GROUP BY player_id, tournament_id
```

**Position sorting (handles T-prefix):**
```sql
ORDER BY TRY_CAST(REGEXP_EXTRACT(position, '[0-9]+', 0) AS INTEGER) NULLS LAST
```
`TRY_CAST(position AS INTEGER)` returns NULL for "T3", "T14" etc. — always use REGEXP_EXTRACT first.

**Top10/wins counting (same fix):**
```sql
SUM(CASE WHEN TRY_CAST(REGEXP_EXTRACT(position, '[0-9]+', 0) AS INTEGER) = 1 THEN 1 ELSE 0 END) AS wins,
SUM(CASE WHEN TRY_CAST(REGEXP_EXTRACT(position, '[0-9]+', 0) AS INTEGER) <= 10 THEN 1 ELSE 0 END) AS top10s
```
Direct `TRY_CAST(position AS INTEGER) <= 10` undercounts by 4x (misses all T-prefixed positions).

---

## Automation & Scheduler

### Schedule (`scripts/scheduled_refresh.py`)

| Schedule | When | What it does |
|----------|------|-------------|
| `monday` | Mon 6am | World rankings, field update, early odds |
| `tuesday-morning` | Tue 6am | Full pipeline: field, course info, DG data, predictions, simulation |
| `tuesday-evening` | Tue 6pm | Odds refresh, DG betting odds, re-run predictions, recommend bets, best bet email |
| `wednesday-morning` | Wed 6am | Tee times, final field confirmation |
| `live` | Thu–Sun hourly | Live leaderboard, hole scores, live SG stats, weather, live pulse narrative |
| `post-tournament` | Sun night | Settle results, grade bets, update fantasy tracker, sync DuckDB |

### Cron Setup

```cron
0 6  * * 1   cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule monday
0 6  * * 2   cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-morning
0 18 * * 2   cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule tuesday-evening
0 6  * * 3   cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule wednesday-morning
0 *  * * 4,5,6,0  cd /Users/jacklegnon/Desktop/golf_data && python3 scripts/scheduled_refresh.py --schedule live
```

### Full Pipeline (`scripts/run_pipeline.py`)

```bash
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate
```

Pipeline steps (in order): fetch field → fetch DG data → fetch odds → merge features → predict → simulate → recommend bets → SHAP analysis → player similarity.

---

## AI Features

### Live Pulse (`GET /api/live/pulse`)

LLM-generated tournament narrative, cached 30 minutes during rounds.

Prompt uses two-layer Anthropic prompt caching:
- **System block (cached):** Static format instructions — stable for the whole round
- **User block (not cached):** Live leaderboard + SG data + fantasy picks — changes every refresh

Output sections: `headline`, `leaders`, `on_fire` (list), `to_watch` (list), `your_picks`, `round_story`

Hard guards prevent hallucination: `_round_recap_block()` only injects verified score data; fabricated round summaries (e.g. Cameron Young shooting 65) fixed by requiring explicit score verification before any narrative claim.

### AI Chatbot (`GET /api/chat`, streaming SSE)

Context builder (`build_context()`) detects query intent and injects the right data:

| Intent | Context injected |
|--------|-----------------|
| Player question | Player profile, SG breakdown, course history, odds movement, web intel |
| Bet question | Value bets, odds comparison, model edge table, weather |
| Live question | Live leaderboard, cut projection, hole scores |
| Lineup question | Fantasy picks, usage, season strategy |
| H2H question | Both players' profiles + head-to-head stats |
| General | Full tournament overview |

Web intel (`scripts/intel/fetch_tournament_intel.py`) — searches the web for player news, injury reports, and course conditions. Output cached at `data/intel/tournament_intel_R{tid}.json`. Auto-runs when file is missing or >48h old.

**Betting philosophy baked into chatbot:**
- Player case first (SG + course fit + form), odds confirm the price — never work backwards from edge%
- At majors: tournament markets (top10/top20/outright) over R1 matchups
- High-edge plays with zero course history = model noise, treat as warning not signal

**Models:** Claude Sonnet 4.6 (primary), Groq Llama 3.3 70B (free fallback)

### Strategy Reasoning (`scripts/predictions/generate_strategy_reasoning.py`)

Generates player-specific narrative reasoning for the season strategy page. Runs Tuesday pipeline. Output: `outputs/strategy_reasoning.json`.

---

## Post-Tournament Pipeline

Run after the tournament ends (Sunday night or Monday):

```bash
python3 scripts/post_tournament.py --tournament-id R2026XXX
```

### Steps

**Step 1 — Scrape final leaderboard** (`step_scrape`)
Fetches settled results from PGA Tour → appends to `data/historical/leaderboards_{year}.csv`

**Step 1b — Sync to DuckDB** (`step_sync_db`)
Upserts all leaderboard rows (including r1–r4 round scores) into DuckDB `leaderboards` table.
This keeps DuckDB as the source of truth going forward — the career endpoint and history detail read from DB, not CSVs.
```bash
python3 scripts/post_tournament.py --tournament-id R2026XXX --step sync_db
```

**Step 2 — Re-fetch form/SG stats** (`step_form_stats`)
SG stats finalize after the tournament ends. Re-fetch ensures DuckDB has the official numbers.

**Step 3 — Backfill prediction history** (`step_backfill`)
Matches `outputs/prediction_history.csv` rows to actual finishes. Sets `actual_position`, `actual_won`, `actual_top10` etc.

**Step 4 — Grade bets** (`step_grade_bets`)
Grades all ungraded bets for the tournament. Computes P&L per bet, writes `outcome_status`, `pnl_per_1`, `roi_pct` to the bets log.

**Step 5 — Update fantasy tracker** (`step_update_tracker`)
Matches each fantasy lineup player to the leaderboard, logs result + earnings to `usage_tracker_2026.json`. `wrp` (weekly rank) is set manually from the league site.

### Individual Steps

```bash
python3 scripts/post_tournament.py --tournament-id R2026XXX --step scrape
python3 scripts/post_tournament.py --tournament-id R2026XXX --step sync_db
python3 scripts/post_tournament.py --tournament-id R2026XXX --step grade
python3 scripts/post_tournament.py --tournament-id R2026XXX --step tracker
python3 scripts/post_tournament.py --tournament-id R2026XXX --dry-run    # preview all steps
```

---

## Critical Design Decisions

### Why CSV-first, DB-second?

The dashboard reads from `outputs/latest_predictions.csv` rather than DuckDB for the current week. This was a deliberate choice:
- CSVs are fast to read, easy to inspect in a spreadsheet, and human-readable
- The prediction pipeline writes one file and the dashboard reads one file — simple dependency
- DuckDB is used where it adds real value: historical range queries, career aggregations, multi-table joins

### Why DuckDB over Postgres/SQLite?

- Columnar storage — analytical queries (AVG over 46K rows of SG stats) are much faster
- `read_csv_auto()` lets you query CSVs as tables in-SQL without loading them into Python
- `TRY_CAST` converts bad values to NULL instead of erroring — critical for dirty historical data

### Why Not Use Per-Tournament SG as Features?

`sg_total`, `sg_ott` etc. from the tournament being predicted are the strongest possible predictors — and therefore the worst features to train on. Including them would be like training a "who wins the game?" model with the final score as a feature. The model would ace training accuracy and be useless for actual predictions. This is why only `season_sg_*` (prior tournaments) and `recent_sg_*` (rolling averages from prior events) are used.

### Why Log-Transform World Rank?

`world_rank_log = log1p(world_rank)` compresses the top of the ranking. The raw difference between rank 1 and rank 2 is not the same as between rank 50 and rank 51. Without the transform, rank 1 dominated the feature — the model was essentially just "is this Scheffler?" The log transform gives a more linear relationship between rank and expected performance.

### Why the Autocorrelation in Simulation?

The 0.06 round carry-over in Monte Carlo isn't arbitrary — it comes from DataGolf's finding that 1 stroke better in R1 approach SG predicts +0.06 strokes in R2. Golf has real momentum effects (confidence, reading greens) even though they're small. Ignoring this makes the simulation slightly too random.

---

## Known Limitations

### Model Limitations

1. **Injuries and withdrawals not in features.** The model doesn't know if a player is nursing a wrist injury. If a player WDs Thursday morning, the model had already predicted them. Manual monitoring + `fetch_withdrawals.py` partially addresses this.

2. **Test set leakage (mild).** Step 3a in `train_final_models.py` uses 2025 test data to decide whether to keep `dg_fit_*` features. Estimated effect: ~0.005–0.01 AUC optimism. Not severe, but the fix (3-way train/val/test split) should be applied at the next major retrain.

3. **2026-only form_stats.** The SG event count penalty (regress toward mean for < 10 events) was calibrated assuming multi-year history in `form_stats`. Since `form_stats` only covers 2026 events, all players show 2–7 events, meaning everyone gets a moderate penalty. This is conservative (good) but slightly depresses confidence for well-established players.

4. **Simulation sigma fallbacks.** Players without 20+ historical rounds get a tier default (2.85–3.20). New tour members and LIV returnees often land here. The fallback is reasonable but less accurate than a player-specific SD.

### Data Limitations

5. **5 tournaments in 2026 have no round scores.** PLAYERS Championship, RBC Heritage, Texas Children's Houston Open, Valspar, Arnold Palmer Invitational — source CSVs never had r1–r4 data. Total score and position are correct.

6. **DK matchup/3-ball odds are 403 blocked.** Only DG odds are available for these markets. This means matchup bet edges are relative to DG's line, not an independent book.

7. **FanDuel TLS blocked.** SSL handshake fails with Python/OpenSSL from macOS. FanDuel odds only available via DataGolf's aggregated feed.

---

## Weekly Workflow

### Tuesday — Prep Day

```bash
# Full pipeline (or let cron handle it at 6am)
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate

# Manual odds + bets (or wait for 6pm cron)
python3 scripts/scrapers/fetch_dg_odds.py --tournament-id R2026XXX --market all
python3 scripts/models/recommend_bets.py --tournament-id R2026XXX

# Best bet card + email
python3 scripts/notifications/send_best_bet.py --send-email
```

### Thursday–Sunday — Live Days

```bash
# Runs automatically hourly via cron. Manual trigger:
python3 scripts/scheduled_refresh.py --schedule live

# Individual fetches:
python3 scripts/scrapers/fetch_live_leaderboard.py --tournament-id R2026XXX
python3 scripts/scrapers/fetch_hole_scores.py --tournament-id R2026XXX
python3 scripts/scrapers/fetch_dg_live_stats.py --tournament-id R2026XXX
```

### Sunday Night — Settlement

```bash
python3 scripts/post_tournament.py --tournament-id R2026XXX
```

Runs all 5 steps: scrape → sync DuckDB → stats refresh → prediction backfill → grade bets → fantasy tracker.

---

## Running the Servers

```bash
# API (port 8000)
cd /Users/jacklegnon/Desktop/golf_data
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (port 3000)
cd /Users/jacklegnon/Desktop/golf_data/web
PATH="/opt/homebrew/bin:$PATH" npm run dev
```

Node.js must be v20+. Use Homebrew node at `/opt/homebrew/bin/node`.

### Tournament ID Format

- Format: `R2026XXX` — R + year + 3-digit event number, always uppercase
- Field files: `data/fields/field_R2026XXX.csv`
- Live files: `data/live/leaderboard_r2026XXX.csv` (lowercase r — different convention)
- Source of truth for current tournament: `outputs/latest_predictions.csv` → `tournament_id` column

---

*Last updated: June 2026*
