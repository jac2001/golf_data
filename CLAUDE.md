# CLAUDE.md — Golf Data Project

Instructions for Claude Code sessions. Read this before touching anything.

---

## What This Is

A Streamlit golf analytics + fantasy betting dashboard (~17,000 lines, `dashboard.py`).
It ingests data from DataGolf, DraftKings, FanDuel, PGA Tour, and manual scrapers,
runs XGBoost prediction models, and surfaces betting recommendations + season strategy
for a fantasy "Let It Ride" league (3 uses per player, 3 players/week, ~30-week season).

**Run the dashboard:**
```bash
streamlit run dashboard.py   # usually already running on port 8501
```

---

## Architecture

```
golf_data/
├── dashboard.py                  # Main Streamlit app (~17,000 lines)
├── data/
│   ├── datagolf/                 # DG API outputs (skill ratings, odds, matchups, field)
│   ├── fields/                   # field_R{tid}.csv — canonical field files
│   ├── odds/                     # DK/FanDuel odds, recommended bets, snapshots
│   ├── fantasy/                  # usage_tracker_2026.json, league standings/picks
│   ├── live/                     # leaderboard_r{tid}.csv + _meta.json (live only)
│   ├── historical/               # leaderboards_2026.csv — settled results
│   ├── processed/                # player_course_performance.csv, master training data
│   ├── models/                   # win/top5/top10/top20_model_final.pkl
│   ├── raw/                      # schedule_2026.csv, pgatour_schedule_2025.csv
│   └── prediction_tracking/      # prediction_history.csv, pred_R{tid}.csv
├── outputs/
│   ├── latest_predictions.csv    # PRIMARY: current week, ~139 cols, one row/player
│   ├── strategy_reasoning.json   # LLM-generated player narratives (when built)
│   └── {name}_{date}_predictions.csv  # archived per-tournament snapshots
├── scripts/
│   ├── run_pipeline.py           # Full weekly pipeline orchestrator
│   ├── scheduled_refresh.py      # Hourly background scheduler
│   ├── scrapers/                 # Data fetchers (DG, DK, FanDuel, PGA Tour)
│   ├── predictions/              # ML pipeline: predict_tournament.py, season_strategy.py
│   ├── features/                 # merge_all_historical_data.py, course SG weights
│   ├── models/                   # recommend_bets.py, train_final_models.py
│   ├── validation/               # calibration.py, walk-forward CV
│   └── database/                 # DuckDB schema/migration (db.py, schema.py)
└── data/golf_data.db             # DuckDB — backend only, dashboard reads CSVs
```

---

## Critical Patterns — Read These First

### Tournament IDs
Format: `R2026XXX` (R + year + 3-digit event number). Always uppercase.
- `current_event_row["tournament_id"]` → `"R2026480"`
- `TournamentInfo` objects have NO `tournament_id` attribute — use `.name`
- Field files: `data/fields/field_R2026480.csv` (canonical, always this format)
- Live files: `data/live/leaderboard_r2026480.csv` (lowercase r)

### Player Name Keys
`_name_key(name)` in `season_strategy.py` sorts lowercase tokens alphabetically:
- `"McIlroy, Rory"` → `"mcilroy rory"`
- `"Rory McIlroy"` → `"mcilroy rory"`

The fantasy tracker stores **last-name-only** keys (`"McIlroy"` → `"mcilroy"`).
Data maps use full-name keys (`"mcilroy rory"`).
**Resolution:** `_resolve_key()` in `season_strategy.py` builds a last-token → full-key
lookup to bridge the gap. Always use `_resolve_key(_name_key(x))` when looking up
tracker players in data maps.

### Predictions Data
`outputs/latest_predictions.csv` — always the current tournament's predictions.
`player_name` column uses `"Last, First"` format. `tournament_id` is the R-prefixed ID.
`preds_df` is loaded in the Betting page scope (~line 7616). `_preds` is the This Week page variable (~line 4972).

### Between-Tournament Gap
When today's date falls between tournaments, `current_event_row` falls back to the
**next** upcoming event (not None). This is intentional — `season_strategy.py` line ~555.
Do not revert this behavior.

### Streamlit Constraints
- **No nested expanders** — Streamlit throws an error. Use `st.markdown` + `st.dataframe` instead.
- `st.rerun()` on every render will freeze the app — avoid any `time.sleep()` in render paths.

---

## Data Flow

```
DataGolf API          DraftKings / FanDuel       PGA Tour / Manual
     │                       │                         │
  dg_client.py          fetch_dg_odds.py         fetch_*.py scrapers
     │                       │                         │
     └───────────── data/ (raw CSVs) ─────────────────┘
                             │
              merge_all_historical_data.py
              predict_tournament.py
              calibration.py / recommend_bets.py
                             │
                    outputs/latest_predictions.csv
                    outputs/recommended_bets_*.csv
                             │
                       dashboard.py
```

**DG API access:** Always use `scripts/scrapers/dg_client.py` → `dg_get()`. It handles
rate limiting. Never make raw requests to DataGolf endpoints.

---

## Weekly Pipeline

```bash
# TUESDAY — Full pipeline
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate

# THURSDAY–SUNDAY — Live refresh (runs via scheduler, or manually)
python3 scripts/scheduled_refresh.py --once

# Odds only
python3 scripts/scrapers/fetch_dg_odds.py --tournament-id R2026XXX --market all

# Bet recommendations
python3 scripts/models/recommend_bets.py --tournament-id R2026XXX

# SUNDAY NIGHT — Settle results
python3 scripts/post_tournament.py --tournament-id R2026XXX
```

The scheduler (`scheduled_refresh.py`) runs automatically every hour during tournament
weeks. It fetches live leaderboard, odds, DG data, and saves snapshots.

---

## Model Architecture

Four XGBoost classifiers: `win`, `top5`, `top10`, `top20`.
Training data: `data/processed/master_training_data_2016_2026.csv` (46K rows, 108 features).
Train script: `scripts/validation/train_final_models.py` — auto-selects newest master CSV.

**Key features:**
- `predictive_sg_weighted` — DG weights: OTT=1.2, APP=1.0, ARG=0.9, PUTT=0.6 (#2 feature)
- `world_rank_log` — log1p(world_rank) to reduce rank-1 dominance
- `dg_fit_total` — DataGolf predictive fit score

**Calibration:** `ProbabilityCalibrator.MAX_WIN_PROB = 0.20` — hard cap on win probability.

**Post-processing order:** Calibrate → course win boost → course perf → KFT → constraints
→ EV → odds + elite market blend (top-15, 25% max) → expert consensus blend (12%) → save.

---

## Season Strategy (`scripts/predictions/season_strategy.py`)

`get_season_strategy()` returns:
```python
{
  "current_event":   {"name", "week", "purse", "tier", "type"},
  "player_strategy": {player_name: {
      "uses_left", "world_rank", "eff_rank", "tier",
      "this_week_ev", "best_future_ev",
      "opportunity_cost_ev", "opportunity_cost_pct",
      "current_course_sg", "current_course_rounds", "current_course_sig",
      "use_this_week",   # bool — NOT "recommendation"
      "save_signal", "is_hot_streak",
      "best_events",     # list of future events with ev, course_sg, etc.
      "in_field",        # bool — is player in current week's field
      "reason",          # natural language string
  }},
  "weekly_lineup":   {"players": [...], "total_ev": int, "alt_lineups": {...}},
  "budget":          {"uses_remaining", "weeks_remaining", ...},
  "this_week_verdict": str,
  "season_plan":     {...},
  "plan_conflicts":  {...},
}
```

**Course fit dedup:** `player_course_performance.csv` has duplicate rows per (player, course).
The loader deduplicates by keeping the row with the most `course_sg_total_rounds`. This is
intentional — do not remove the dedup step.

---

## Dashboard Page Structure

| Tab | Notes |
|-----|-------|
| This Week | Main predictions, field table, weather, course layout |
| Scoring Engine | Detailed SG breakdown by player |
| Betting | Value Bets, Matchups (DG 3-ball + tournament H2H), Odds Explorer |
| Players | Search, H2H comparison, course history |
| Predictions | Full prediction table with filters |
| Live | Live leaderboard, scorecards, hole scores |
| My Picks | Fantasy usage tracker, weekly lineup log |
| Pipeline | Run scripts from dashboard, see scheduler status |
| Usage Strategy | Season strategy tab — optimal lineup card, roster table, season plan |
| Season Stats | Historical performance stats |

---

## Key Bugs Fixed (Don't Reintroduce)

**`stat_id` type mismatch:** DB returns stat_ids as strings (`'2567'`), stat_mapping used
int keys. Fixed with string keys everywhere.

**`player_id` type mismatch:** Field CSV has int64, DB returns str. Fixed with
`pid_str = str(int(player_id))` normalization.

**`_resolve_key` for tracker players:** Tracker stores last-name-only. Without this,
all season strategy players show blank data. Never bypass `_resolve_key()`.

**`current_event_row = None` between tournaments:** Without the fallback to next upcoming
event, the entire Usage Strategy tab goes blank. The fallback is intentional.

**`course_sg_total_rounds` dedup:** Multiple rows per (player, course) in
`player_course_performance.csv`. The single-round 2026 entry overwrites the full history
unless deduplicated. Fixed by sorting and keeping max-rounds row.

**Auto-refresh `time.sleep()` in Betting tab:** Removed — it blocked the entire Streamlit
process on every render.

---

## What NOT to Do

- Don't make raw HTTP requests to DataGolf — use `dg_get()` from `dg_client.py`
- Don't commit `.env` files or API keys
- Don't use `st.rerun()` in a render loop
- Don't nest `st.expander()` inside another `st.expander()`
- Don't reference deleted scripts: `fetch_live_tournament_stats.py`,
  `fetch_field_from_pgatour.py`, `fetch_betting_profile_articles.py` — they don't exist
- Don't look for `TournamentInfo.tournament_id` — the attribute doesn't exist
- Don't use `recommendation` as a key in `player_strategy` dicts — the key is `use_this_week`
- Don't bypass `_resolve_key()` when looking up tracker players in data maps

---

## DraftKings / Odds Access

- **Outright winner + Top 5/10/20:** DK main eventgroup endpoint — working
- **Matchups / 3-ball / make_cut subcategories:** 403 blocked
- **FanDuel `sbapi.fanduel.com`:** TLS JA3 fingerprint blocking — SSL handshake fails
- **DataGolf odds:** `fetch_dg_odds.py --market all` — preferred source for matchups
- **Manual odds:** `fetch_draftkings_props.py --input-json <devtools_export>` for blocked markets

---

## Fantasy League Rules

- **3 uses per player** for the entire season
- **3 players per weekly lineup**
- **~30 tournaments** in the season
- Data lives in `data/fantasy/usage_tracker_2026.json`
- Tracker uses last-name-only keys (e.g., `"McIlroy"`) — `_resolve_key()` bridges to full-name keys

---

## User Preferences

- No emojis unless asked
- Concise responses — don't summarize what you just did
- Don't auto-commit — always ask first
- Explain changes clearly before implementing
- Invite the user to apply changes themselves at natural learning moments
- User is actively learning data science, ML, AI — explain concepts as you go
