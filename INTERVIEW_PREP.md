# Project: Golf Analytics & Fantasy Betting Platform

**One-line pitch:** A full-stack data platform that ingests live golf data from 4+ sources, runs a calibrated ML ensemble to predict tournament outcomes, and turns those predictions into actionable betting edges and season-long fantasy strategy — built and operated solo, in production, with real money on the line.

---

## Resume Bullets (current version)

> **Golf Outcome Prediction Platform** — end-to-end ML system, built solo
> - Trained and calibrated 4 XGBoost classifiers (win/top-5/10/20) on 46K rows with 100+ engineered features and temporal CV; benchmarked against DataGolf (industry leader) — within ~5% log loss with better probability calibration on all four markets.
> - Built automated pipelines from 5 live data sources into a DuckDB backend (2,000+ players, 2016–2026), a 10,000-run in-tournament Monte Carlo simulator, and an EV-based bet recommender with hourly scheduling and automated settlement; live-tracked recommendations returned +27% ROI at the 2026 Masters.

Every number above is verifiable in the repo — be ready to name the 5 sources (DataGolf, DraftKings, FanDuel, PGA Tour GraphQL, weather API), point to the Monte Carlo (`scripts/predictions/live_update_predictions.py`, `N_SIMS = 10_000`), and explain the DataGolf benchmark methodology.

---

## Problem

Two related decision problems, both season-long and sequential:
1. **Betting**: given a sportsbook's odds, is the market mispricing a player's chance to win/top-5/top-10/top-20? By how much, and is the edge big enough to bet?
2. **Fantasy ("Let It Ride")**: a league format where each player can only be used **3 times all season** (~30 tournaments). Using your best player in week 2 burns a use you might want for a major in week 14. This is a constrained resource-allocation problem, not just "who's good this week."

## Architecture

```
DataGolf API / DraftKings / FanDuel / PGA Tour GraphQL / web search (Claude)
                              │
                  Python ingestion + feature pipeline
                              │
                    DuckDB (6 tables, ~1M+ rows)
                              │
              4x XGBoost classifiers (win/top5/top10/top20)
                              │
            Calibration → market blending → EV → bet sizing
                              │
                  FastAPI backend  ──────────  Next.js 16 / React 19 frontend
                  (api/main.py, ~6.4K LOC)      (TypeScript, ~12.7K LOC)
```

- **Original version**: a single ~17K-line Streamlit app (`dashboard.py`) — fast to build, hit its ceiling on render performance and UI flexibility once the feature set grew.
- **Current version**: migrated to a decoupled **FastAPI backend + Next.js/TypeScript frontend**, deployed Vercel (frontend) → Render (backend). This is a good interview story on its own: *why* you outgrew a notebook-adjacent tool (Streamlit) and moved to a real client/server split.
- **Data/ML layer**: ~68K lines of Python across `scripts/` (scrapers, feature engineering, model training, calibration, validation).

## Data Pipeline

- **DataGolf** is the primary stats/odds source, accessed exclusively through a rate-limited client (`dg_client.py`) — every other script is required to go through it rather than hitting the API directly.
- **DraftKings / FanDuel / PGA Tour** are scraped directly (no official API). This means dealing with real anti-bot defenses: DK blocks sub-market endpoints (matchups/3-balls) with 403s, FanDuel blocks at the TLS/JA3 fingerprint level before HTTP even completes. Worked around by using DataGolf's odds feed as the matchup-market source and falling back to manual DevTools-export ingestion for the markets that stay blocked.
- **Storage**: migrated historical data (2016–2026, ~442K player-round rows, ~591K form-stat rows) from flat CSVs into **DuckDB** for query performance, while keeping the model-facing output as CSV (`outputs/latest_predictions.csv`) so the frontend/dashboard layer doesn't need a DB driver.
- **Identity resolution**: the hardest unglamorous problem in the whole project. Player names arrive in different formats from different sources ("Rory McIlroy" vs "McIlroy, Rory" vs fantasy tracker's last-name-only keys), with accents, suffixes (Jr/Sr/III), and nicknames. Solved with a canonical normalization function (`_name_key`) plus a resolver that bridges last-name-only fantasy records to full-name data keys.

## ML Model

- **4 independent XGBoost binary classifiers**: win / top5 / top10 / top20 — not a single multiclass model, because the label boundaries aren't mutually exclusive in a way that's useful for betting (you bet each market separately against its own odds).
- **~48K training rows, 108 features**, trained on 2016–2026 data.
- **Notable feature engineering**:
  - `predictive_sg_weighted` — DataGolf's strokes-gained categories aren't equally predictive; reweighted (Off-the-tee ×1.2, Approach ×1.0, Around-the-green ×0.9, Putting ×0.6) rather than averaged, based on which categories are more stable/predictive year-over-year. This became the #2 most important feature.
  - `world_rank_log` — raw world rank caused the model to overweight rank #1 specifically (a step-function-like effect at the top of a long-tailed distribution); `log1p(rank)` smoothed that out and dropped that feature's dominance from #1 (8.3% importance) to #9 (4.4%), spreading signal to other features instead of overfitting to "is this player ranked #1."
- **Calibration**: raw XGBoost probabilities are not well-calibrated for rare events (win probability) — added a calibration layer with a hard cap (`MAX_WIN_PROB = 0.20`) because the uncalibrated model would occasionally output ~30% win probability for a 156-player field, which is not a believable number no matter how good a player is.
- **Post-processing pipeline order matters**: calibrate → course-fit boost → recent-form adjustment → fantasy-constraint adjustment → expected-value calc → blend toward market odds (top-15 players only, max 25% weight) → blend toward expert-consensus picks (12% weight) → save. Blending toward the market is a deliberate "the market knows things my model doesn't (late scratches, course-specific intangibles) — meet it partway" decision, not a concession that the model is wrong.
- **Validation**: walk-forward cross-validation (not k-fold — would leak future tournament information into training for a time-series problem) plus tracking Spearman rank-correlation against live market odds as an external sanity check (improved 0.545 → 0.669 after the feature/calibration fixes above).

## LLM/Agent Integration

- A **web-search intel agent** (using Claude's web_search tool) pulls per-player injury/news/sentiment context before each tournament — this is *pre-computed* and cached, not a live RAG call during chat, which keeps the chatbot fast and avoids hallucination risk from unverified live search results.
- A **golf chatbot** answers natural-language betting questions, with hard-coded guardrails after an early incident where it fabricated a player's round score during a recap (a real lesson in why LLM outputs over live sports data need deterministic verification, not just better prompting).

## Notable Engineering Decisions (good interview talking points)

1. **Streamlit → Next.js/FastAPI migration** — talk about *why*: Streamlit reruns the entire script top-to-bottom on every interaction, which doesn't scale once a dashboard has dozens of interdependent tabs and live-refreshing data; a proper client/server split lets the frontend be reactive without re-fetching everything.
2. **Rate-limiting discipline** — one client (`dg_client.py`) owns all calls to the paid API; every scraper is required to go through it. This is a "don't get your API key rate-limited or banned" lesson generalized into an enforced architectural rule.
3. **Calibration over raw model output** — a model's probabilities are a starting point, not the final number, especially for rare/extreme events.
4. **Walk-forward validation for time-series ML** — standard k-fold CV would have looked great and been wrong, because it would let the model "see the future."
5. **Treating identity resolution as a first-class problem** — most of the actual bugs in this project's history were name-matching edge cases, not model accuracy. Worth a story about debugging why "the entire fantasy strategy tab went blank" turned out to be a key-format mismatch, not a data problem.

## Scale / Results (concrete numbers to cite)

- ~68K lines of Python (data/ML pipeline), ~12.7K lines of TypeScript (frontend), ~6.4K lines of Python (API backend)
- DuckDB: 442K tournament-stat rows, 591K form-stat rows, 46K leaderboard rows, spanning 2016–2026
- Training set: ~48K rows × 108 features
- Model correlation with market odds improved 0.545 → 0.669 (Spearman) after feature engineering fixes
- Real-money tracked results: e.g. +27.2% ROI across bet types for the 2026 Masters week, with make-cut bets at ~48% ROI overall across the season

---

*Use this as a script outline, not a verbatim answer — pick 2-3 of the "decisions" above to go deep on based on what the interviewer's role emphasizes (ML-heavy → calibration/validation section; backend-heavy → migration/rate-limiting section; data-heavy → identity resolution/pipeline section).*
