# CLAUDE.md — Golf Data Project

Instructions for Claude Code sessions. Read this before touching anything.
Deeper reference: `PROJECT_OVERVIEW.md` (architecture), `outputs/season_2026_retrospective.md`
(real season numbers), `web/app/methodology/page.tsx` (public write-up of the method).

---

## What This Is

A golf analytics + betting platform (~68K lines of Python in `scripts/`, a 6.6K-line FastAPI
backend, a Next.js frontend). It ingests DataGolf, DraftKings, PGA Tour GraphQL, Open-Meteo
weather, and a fantasy league site; trains calibrated Random Forest models for win/top5/top10/top20;
runs Monte Carlo simulations; recommends bets against sportsbook odds; and manages a season-long
fantasy "Let It Ride" league (3 uses per player, 3 players/week, ~30-week season).

The Streamlit `dashboard.py` is gone (deleted Sept 2026). Do not recreate it or reference it.

**Run locally:**
```bash
uvicorn api.main:app --reload --port 8000        # backend
cd web && npm run dev                            # frontend on :3000 (Node 20+)
```

**Deployed:** frontend on Vercel, backend on Render (`web/vercel.json` holds the API URL),
history mirrored to Supabase. Render has no DuckDB; it reads committed CSVs + Supabase.

---

## Architecture

```
golf_data/
├── api/main.py                   # FastAPI — every backend endpoint (~55 routes)
├── web/                          # Next.js 16 / React 19 / TypeScript, App Router
│   ├── app/{predictions,betting,live,players,mypicks,history,assistant,methodology}/page.tsx
│   ├── components/               # BetCard, Leaderboard, OddsExplorer, LineupCards, ...
│   └── lib/api.ts                # ALL fetch functions + TS types — pages never call fetch() directly
├── scripts/
│   ├── run_pipeline.py           # Full weekly pipeline orchestrator (writes logs/pipeline_status_*.json)
│   ├── scheduled_refresh.py      # Day/hour-aware scheduler; ends by committing data/ + outputs/ to main
│   ├── post_tournament.py        # Settlement steps (scrape, sync_db, stats, backfill, grade, tracker)
│   ├── config.py                 # SEASON detection + canonical per-season paths — use these helpers
│   ├── utils/tournament_context.py  # Schedule row resolution + tournament name matching
│   ├── scrapers/                 # dg_client.py (DataGolf), fetch_live_leaderboard.py, fetch_dg_odds.py, ...
│   ├── predictions/              # predict_tournament.py, calibration.py, season_strategy.py,
│   │                             #   live_update_predictions.py (10K-sim Monte Carlo), simulate_tournament.py
│   ├── models/                   # recommend_bets.py, grade_recommended_bets.py
│   ├── features/                 # merge_all_historical_data.py → master training CSV
│   ├── validation/               # train_final_models.py, walk_forward_cv.py, track_clv.py, calibration data
│   ├── strategy/                 # backtest_preseason_projection.py (2027 strategy-mode gate)
│   ├── chat/                     # golf_chatbot.py (context builder + streaming), build_assistant_context.py
│   ├── notifications/            # send_best_bet.py, check_bet_alerts.py, generate_recap.py
│   └── database/                 # db.py, schema.py (DuckDB), supabase_sync.py
├── data/
│   ├── datagolf/                 # DG outputs: outrights, matchups, skill ratings, decompositions, pre-tournament
│   ├── fields/                   # field_R{tid}.csv — canonical field files
│   ├── odds/                     # prop_lines, pga_odds, recommended_bets_R*.csv, recommended_bets_log.csv,
│   │                             #   closing_lines_R*.csv (CLV snapshots)
│   ├── fantasy/                  # usage_tracker_{SEASON}.json, league standings/picks
│   ├── live/                     # leaderboard_r{tid}.csv + _meta.json, tee_times_R*_r{n}.csv
│   ├── historical/               # leaderboards_{year}.csv, tournament_stats_{year}.csv, form_stats_{year}.csv
│   ├── processed/                # master_training_data_*.csv, player_course_performance.csv (gitignored)
│   ├── models/                   # win/top5/top10/top20_model_final.pkl, cut_model.pkl, score model
│   ├── raw/                      # schedule_{SEASON}.csv — source of truth for the calendar
│   ├── intel/, weather/, expert_picks/, betting_profiles/, prediction_tracking/
│   └── golf_data.db              # DuckDB — local only, gitignored
├── outputs/
│   ├── latest_predictions.csv    # PRIMARY: current tournament, one row/player, ~300 cols
│   ├── strategy_reasoning.json   # feeds GET /api/lineup
│   ├── best_bet.json             # feeds the featured card on /betting
│   ├── season_2026_retrospective.md, model_test_metrics.json, benchmark_vs_dg_summary.json
│   └── {name}_{date}_predictions.csv  # archived per-tournament snapshots
├── logs/                         # pipeline_status_*.json, retrain_log.json, *.done sentinels
└── .github/workflows/            # tuesday_pipeline.yml, live_refresh.yml (cloud copies of scheduler modes)
```

---

## Critical Patterns — Read These First

### The one-file contract
Everything upstream exists to write `outputs/latest_predictions.csv`; everything downstream reads it.
The API finds the current tournament from its `tournament_id` column (`_get_tournament_id()` in
`api/main.py`). Keep this contract: do not make the frontend or API depend on DuckDB for current-week data.

### Tournament IDs
Format: `R2026XXX` (R + year + 3-digit event number). Always uppercase.
- Field files: `data/fields/field_R2026480.csv`
- Live files: `data/live/leaderboard_r2026480.csv` (lowercase r — different convention, intentional)
- DG event id = the numeric part with leading zeros stripped (`R2026034` → `34`)
- `TournamentInfo` objects have NO `tournament_id` attribute — use `.name`

### Season-dependent paths
`scripts/config.py` detects `SEASON` from the newest `data/raw/schedule_*.csv` and exposes
`schedule_csv()`, `usage_tracker_json()`, `leaderboards_csv()`, etc. Use those helpers instead
of hardcoding `_2026`. (Some older modules still hardcode; migrate when you touch them.)

### Player name keys — three formats, one resolver
- `"Last, First"` — `latest_predictions.csv`, picks
- `"First Last"` — DuckDB leaderboards, DataGolf, PGA Tour
- `"Last"` only — fantasy usage tracker

`_name_key(name)` in `season_strategy.py` sorts lowercase tokens: both full formats → `"mcilroy rory"`.
The tracker's last-name-only keys are bridged by `_resolve_key()` (last token → full key lookup).
**Always use `_resolve_key(_name_key(x))` when looking up tracker players in data maps.** Frontend
equivalent is `normName()`; `post_tournament.py` has `_norm_name()`.

### Between-tournament gap
When today falls between tournaments, `current_event_row` falls back to the **next** upcoming event,
not None (`season_strategy.py` ~line 566). Without it the whole strategy view goes blank. Keep it.

### Course fit dedup
`player_course_performance.csv` has duplicate rows per (player, course). The loader keeps the row
with the most `course_sg_total_rounds`; otherwise a single-round 2026 entry overwrites full history.
Do not remove the dedup.

### Frontend rules
- All API calls go through `web/lib/api.ts`. Add the fetch function and TS type there first.
- Read `web/AGENTS.md`: this Next.js version differs from training data; check `node_modules/next/dist/docs/`.
- Inline CSS-in-JS, dark theme. Palette: `#0d1a30` bg, `#dde6f5` text, `#00c44f` green,
  `#e74c3c` red, `#4cb8ff` blue, `#f1c40f` gold.

---

## Data Flow

```
DataGolf (dg_client.py)   PGA Tour GraphQL   DraftKings   Open-Meteo   League site
        │                      │                 │            │            │
        └────────────── scrapers/ → data/*.csv ─────────────────────────────┘
                                  │
             merge_all_historical_data.py → data/processed/master_training_data_*.csv
             predict_tournament.py → outputs/latest_predictions.csv
             live_update_predictions.py (Monte Carlo) → live_* columns
             recommend_bets.py → data/odds/recommended_bets_R{tid}.csv + recommended_bets_log.csv
                                  │
             deploy_site() commits data/ + outputs/ → push main → Render redeploys
                                  │
             api/main.py (CSVs, Supabase fallback, CLOUD_FETCH refetch) → web/
```

**DG API access:** always `dg_get()` from `scripts/scrapers/dg_client.py`. It throttles. Never raw requests.

**Data ships through git.** `deploy_site()` in `scheduled_refresh.py` stages only `data/` and
`outputs/`, commits "Auto-deploy: ...", and pushes to `main`. It refuses to run on any other branch.

**Cloud freshness:** with `CLOUD_FETCH=1` (set on Render) live endpoints call `_freshen(kind)` and
refetch leaderboard (5 min TTL), DG odds (15 min), weather (3 h) straight from source when stale.
When `CLOUD_FETCH` is on, the leaderboard endpoint skips the Supabase read because the Supabase
copy can be staler than the freshly fetched CSV.

---

## Weekly Workflow (as `scheduled_refresh.py` actually runs it)

`determine_schedule()` picks a mode from day/hour; every mode ends with `deploy_site()`.

| Mode | When | What |
|---|---|---|
| `monday` | Mon | Player database only (rankings/stats are done post-tournament) |
| `tuesday-morning` | Tue AM | League picks, DG field, **WD check before predictions**, course info, power rankings, betting profiles, DG skill/decomp/pre-tourney, full pipeline, DG field merge, weather, tee times + draw advantage R1/R2 |
| `tuesday-evening` | Tue PM | DK odds, DG pre-tournament, DG odds (all markets), predictions rerun, recommend bets, best-bet email, bet alerts |
| `wednesday-morning` | Wed AM | WD check, expert picks, predictions rerun, recommend bets, pre-tournament validation |
| `wednesday-evening` | Wed PM | Same as tuesday-evening |
| `live` | Thu–Sun hourly | Closing-line snapshot (first run only, sentinel-guarded), then 3 parallel tiers: fetches → refresh odds + live predictions → recommend bets + live bets. Daily intel, R3/R4 tee times, DuckDB + Supabase sync |
| `post-tournament` | Sun 9pm | Final leaderboard, official check, past results, append historical + sync DuckDB, DG historical sync, stats/form/rankings, auto-record, backfill, grade bets, tracker, CLV, assistant context, calibration data, retrain check, report email |
| `record` | Sun 11pm | Final leaderboard, auto-record, grade bets |

Manual equivalents:
```bash
python3 scripts/run_pipeline.py --auto-weekly --lineup --calibrate
python3 scripts/scheduled_refresh.py --schedule live --dry-run
python3 scripts/scrapers/fetch_dg_odds.py --tournament-id R2026XXX --market all
python3 scripts/models/recommend_bets.py --tournament-id R2026XXX
python3 scripts/post_tournament.py --tournament-id R2026XXX [--step grade|tracker|sync_db] [--dry-run]
```

`run_pipeline.py` exits non-zero on failure and runs post-run sanity checks that fail the run if
artifacts are stale. This was added after a crashed prediction stage once logged as success.

**Retrain cadence:** every 4 settled tournaments (`TOURNAMENTS_PER_RETRAIN`, tracked in
`logs/retrain_log.json`): merge training data → train → SHAP → player explanations.

**GitHub Actions** (`tuesday_pipeline.yml`, `live_refresh.yml`) run the same scheduler modes in
the cloud and sync to Supabase. The Tuesday job intentionally does not run predictions.

---

## Model Architecture

Four binary classifiers: `win`, `top5`, `top10`, `top20`. Each is a **Random Forest wrapped in
`CalibratedClassifierCV`** (isotonic), not XGBoost. Shallow trees + high leaf minimums are the
overfitting control; `class_weight='balanced_subsample'` handles ~0.7% win rate.

Training: `scripts/validation/train_final_models.py` auto-selects the newest
`data/processed/master_training_data_*.csv`. Year-based split, walk-forward CV in
`walk_forward_cv.py`. Sept 2026 retrain: half-life recency sample weights, `field_size` and
`no_cut` features added, `dg_fit_*` dropped, 58 features.

**Key features:** `world_rank_log` (log1p of rank, #1), `predictive_sg_weighted`
(OTT 1.2 / APP 1.0 / ARG 0.9 / PUTT 0.6, #2), `season_sg_total`, `recent_sg_weighted`.

**Never use as features:** per-tournament `sg_*` (leakage), old `fit_*` / `course_fit_total`
(computed from leaky SG), `*_vs_field` SG variants (r ≈ 0.97 with raw).

**Calibration:** `ProbabilityCalibrator` scales toward base rates. `MAX_WIN_PROB = 0.20` still
exists but **no longer clamps** — it prints a loud warning. Do not reintroduce a silent cap.
Watch item: calibration factors drifted over-predicting after the retrain (win ~1.40x); they
re-learn from graded 2027 results.

**Post-processing order (predict_tournament.py):** calibrate → course win boost → course perf →
KFT penalty → monotonic constraints (win ≤ top5 ≤ top10 ≤ top20) → EV → odds + elite market blend
(top-15, 25% max) → expert consensus blend (12%) → save.

**Monte Carlo:** `live_update_predictions.py` runs 10,000 sims per refresh; `simulate_tournament.py`
is the pre-tournament version (uses DG `final_pred`/`std_deviation`, 0.06 round autocorrelation,
raises `InsufficientDGDataError` below 50% DG coverage and the pipeline skips it).

---

## Betting System

`recommend_bets.py` de-vigs book odds, computes `edge = model_prob - no_vig_prob`, ranks by
`confidence × EV`. Scheduler thresholds: min edge 0.75pp, min confidence 0.45, max 15 per market, top 40.

**Odds sources:** DG outrights/matchups (12+ books, preferred) → DK prop_lines CSV → PGA Tour GraphQL.
DK matchup/3-ball endpoints are 403-blocked; FanDuel blocks at TLS fingerprint level. Use DG for those.
Manual DK export: `fetch_draftkings_props.py --input-json <devtools_export>`.

**Bet log:** `data/odds/recommended_bets_log.csv` is authoritative (DuckDB copy has schema drift).
`append_log()` must actually write the CSV — a refactor once dropped the write and the log silently
stopped for four months.

**CLV:** grading reads only `snapshot_type='closing'` rows from `closing_lines_R{tid}.csv`, taken by
the first live refresh of the week. Missing snapshot → NaN, never a proxy. 2026 CLV is unrecoverable.

**2026 reality (776 graded bets, −20.9% ROI):** only `make_cut` (+52.9%) and R4 H2H (+4.1%) were
profitable. Outrights went 0/11. Any new betting work should start from that table in the retrospective.

---

## Season Strategy (`scripts/predictions/season_strategy.py`)

`get_season_strategy()` scores each player's remaining uses: `this_week_ev` (from real model probs)
vs `best_future_ev` (rank proxy × course-fit factor) → `use_this_week` bool, `opportunity_cost_ev`,
`best_events`, `reason`. Consumers: `generate_strategy_reasoning.py` (writes
`outputs/strategy_reasoning.json`, which `GET /api/lineup` serves) and the chatbot.

- The key is `use_this_week`, not `recommendation`.
- `backtest_preseason_projection.py` (Sept 2026) found per-player dollar earnings are unlearnable
  year to year (self-correlation 0.04); finish percentile is weakly learnable (0.09). 2027 strategy
  mode should weight attendance × purse × overall strength with only a small event-fit tilt.

---

## Web Pages and API

| Route | Page | Main endpoints |
|---|---|---|
| `/predictions` | This Week | `/api/tournament`, `/api/predictions`, `/api/course`, `/api/weather` |
| `/betting` | Value Bets | `/api/bets`, `/api/bets/best`, `/api/odds/comparison`, `/api/matchups`, `/api/3ball`, `/api/odds/explorer` |
| `/live` | Live | `/api/live/inplay`, `/api/live/hole-scores`, `/api/live/sg-stats`, `/api/live/pulse`, `/api/live/my-lineup` |
| `/players` | Players | `/api/players/profile` (current field only), `/api/players/career` (DuckDB/Supabase, any player) |
| `/mypicks` | My Picks | `/api/mypicks`, `POST/DELETE /api/picks`, `/api/lineup` |
| `/history` | History | `/api/history/tournaments`, `/api/history/tournament/{tid}`, `/api/history/bets` |
| `/assistant` | Assistant | `POST /api/chat` (SSE streaming) |
| `/methodology` | Methodology | static |

Chat: Claude Sonnet primary (prompt caching, tool use), Groq Llama fallback (no tools).
Live Pulse narrative caches 30 min and only narrates verified scores (`_round_recap_block`).

Known wart: `/api/model-comparison` is registered twice in `api/main.py`; FastAPI keeps the first.

---

## DuckDB (`data/golf_data.db`, local only)

`scripts/database/db.py` → `get_conn(read_only=False)`. Tables: leaderboards (with r1–r4),
tournament_stats (long format, string stat_ids: 2567 total, 2568 OTT, 2569 APP, 2564 PUTT),
form_stats, course_performance, players, dg_*, prediction_history, recommended_bets_log,
live_*, round_stats, picks, conversation_log.

- Pivot long stats with `AVG(CASE WHEN stat_id = '2567' ...)` — never JOIN per stat.
- Sort/count positions with `TRY_CAST(REGEXP_EXTRACT(position, '[0-9]+', 0) AS INTEGER)`;
  a bare `TRY_CAST(position AS INTEGER)` drops every `T3`-style row and undercounts top-10s 4x.
- `_canon_pid` at every merge join — a string/int player_id mismatch once erased course SG history for all years.

---

## Key Bugs Fixed (Don't Reintroduce)

- **`stat_id` type:** DB returns strings; use string keys everywhere.
- **`player_id` type:** field CSV int64 vs DB str; normalize with `str(int(pid))` / `_canon_pid`.
- **`_resolve_key` bypass:** tracker players show blank strategy data without it.
- **`current_event_row = None` between tournaments:** the fallback to next event is intentional.
- **Course perf dedup:** keep the max-rounds row.
- **Silent pipeline success:** `run_pipeline.py` must raise `SystemExit(1)` on failure.
- **`append_log` not writing:** verify the CSV write exists when touching `recommend_bets.py`.
- **Wire-to-wire misgrade:** qualified "to win X" card legs route to manual review, never auto-won.
- **In-play odds as closing lines:** CLV only from `snapshot_type='closing'`.
- **WD blocks "official" + Sunday off-by-one-week:** settlement bugs fixed Sept 2026; don't touch
  `is_tournament_official()` / `get_last_tournament()` without re-testing a Sunday-night run.
- **2026 training-data rot:** ID join bug + missing weather; `_export_stats_csv` is wired into
  `post_tournament.py` so DB stats reach the training CSV.

---

## What NOT to Do

- Don't make raw HTTP requests to DataGolf — use `dg_get()`.
- Don't commit `.env`, API keys, or `data/golf_data.db`.
- Don't reference `dashboard.py` or any Streamlit API — it no longer exists.
- Don't call `fetch()` in a page; add to `web/lib/api.ts`.
- Don't reference deleted scripts: `fetch_live_tournament_stats.py`, `fetch_field_from_pgatour.py`,
  `fetch_betting_profile_articles.py`, `fetch_odds_api.py`, `weight_optimizer.py`.
- Don't look for `TournamentInfo.tournament_id`.
- Don't use `recommendation` as a key in `player_strategy` — it is `use_this_week`.
- Don't bypass `_resolve_key()`.
- Don't run `deploy_site()` logic from a non-main branch (it refuses anyway).
- Don't silently clamp probabilities; warn.

---

## Environment

`.env` (gitignored): `DG_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, `PTFG_EMAIL`/`PTFG_PASSWORD` (league site), SMTP_* / NOTIFY_EMAIL_*
(best-bet + report emails). `CLOUD_FETCH=1` on Render only. Python deps in `requirements-api.txt`
(the canonical list; `requirements.txt` is the older Streamlit-era file).

---

## Fantasy League Rules

- 3 uses per player per season, 3 players per weekly lineup, ~30 tournaments.
- Data: `data/fantasy/usage_tracker_{SEASON}.json` with `picks` (per player), `weekly_lineups`,
  `summary`. `wrp` (weekly rank) is set manually from the league site.
- Tracker keys are last-name-only; `_resolve_key()` bridges to full-name keys.
- 2026 result: 3rd of 10.

---

## User Preferences

- No emojis unless asked
- Concise responses — don't summarize what you just did
- Don't auto-commit — always ask first
- Explain changes clearly before implementing
- Invite the user to apply changes themselves at natural learning moments
- User is actively learning data science, ML, AI — explain concepts as you go
