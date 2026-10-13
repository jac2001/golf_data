# CLAUDE.md — Golf Edge

Loaded into every session. Keep it true and short: when something here goes
stale, fix it in the same change. The working plan lives in `docs/ROADMAP.md`
(read it first; new ideas get sequenced there, not chased mid-session).

## What this is

**Golf Edge — playgolfedge.com.** A golf picks game for friend groups (Let It
Ride seasons, Round Game, Fade Game, College Game, the model plays as a member)
plus public PGA TOUR / DP World Tour predictions.

| Piece | Where | Notes |
|---|---|---|
| Web app | `web/` — Next.js 16 on **Vercel** | Clerk auth, Neon Postgres. Read `web/AGENTS.md`: this Next.js has breaking changes vs. training data. |
| API | `api/main.py` — FastAPI on **Render** (`golf-app-a3yw.onrender.com`) | Reads committed CSVs under `data/` + `outputs/`. Free tier sleeps: first call can be slow. |
| Pipeline | `scripts/` on **GitHub Actions** | `.github/workflows/data-refresh.yml` (cron slots), `tuesday-predictions.yml`. Commits data → Render redeploys. |
| Watchdog | `web/app/api/watchdog` — daily Vercel cron | Re-dispatches settlement/prediction runs GitHub's scheduler drops. |
| Legacy | `dashboard.py` (Streamlit, local only) | Not the product anymore; don't build new features there. |

Models: PGA = 4 XGBoost classifiers (`scripts/predictions/predict_tournament.py`,
`ProbabilityCalibrator.MAX_WIN_PROB = 0.20`); DPWT = `scripts/predictions/predict_euro.py`.
Spend/save advice = `scripts/predictions/advice_values.py` (values) + `web/lib/advice.ts`
(per-member verdicts, Jack's `golferVerdict`). Design notes: `docs/ADVICE_VIEW_DESIGN.md`.

## Domain rules — these encode judgment; enforce them even when not asked

1. **Event provenance.** Never use a week-specific file without checking the
   event it says it is (`scripts/scrapers/event_guard.names_match`, accent-folded).
   Prefer `{kind}_{tid}.csv` over `*_latest.csv`; a mismatch is skipped and logged,
   never merged under this week's name. This exact bug shipped four times
   (RBC Canadian, Biltmore, Baycurrent, España).
2. **Don't publish bad predictions.** `scripts/validation/prediction_integrity.py`
   (DG coverage ≥90%, model top-10 all covered, sim-vs-model rank corr ≥0.5) and
   `data_freshness.py` (event-less inputs ≤10 days, by the date INSIDE the file —
   CI mtimes are meaningless) run in run_pipeline's post-run checks. Don't loosen
   thresholds to make a run pass; find the input that's wrong.
3. **No leakage.** Training features use only what was known before the event
   (prior editions, pre-tournament snapshots). Benchmarks use the frozen pre-event
   copy (`euro_model_{tid}_pre.csv`), never mid-event overwrites.
4. **Fail closed** for anything that reveals or locks: picks hidden until lock
   (`web/lib/eventLocks.ts`), tour-local lock clocks (`web/lib/lockTime.ts`),
   cron routes refuse without `CRON_SECRET`, unknown lock state = locked.
5. **DataGolf is the only odds/stats source**, via `scripts/scrapers/dg_client.py`
   `dg_get()` (rate-limited). Never reintroduce DraftKings/FanDuel fetchers.
   PGA TOUR GraphQL is used only for on-demand scorecards, weather, power rankings
   (licensing: verbal "free while non-commercial", not yet in writing).
6. **Money is lineup earnings, not cash.** Golfers' real prize money is the score;
   live numbers are "estimated payouts if the tournament ended now", never
   "projected" on its own.

## Keys and IDs

- Tournament IDs: `R2026XXX` (PGA), `E2026XXX` (DPWT), uppercase. Live files use
  lowercase (`leaderboard_r2026527.csv`).
- Name keys: site = `web/lib/names.ts nameKey` (keeps accents); Python =
  `season_strategy._name_key` (strips them). Uses are stored under the SITE key.
- Neon tables: `leagues`, `league_picks` (`reason` = the model's saved why),
  `group_members`, `groups`, `fade_picks`, `round_picks`, `college_picks`, …
  Inspect with a throwaway script via `node --env-file=web/.env.local`; never
  `DELETE`/`UPDATE` real rows without the user saying so.

## Verify before you say it works

| Changed | Run |
|---|---|
| `web/lib/*.ts` | `cd web && npm test` (node:test, imports the real files) |
| any `web/` code | `cd web && npm run build` (also type-checks) |
| `scripts/validation`, `scripts/predictions` | `python3 scripts/validation/test_prediction_integrity.py` |
| pipeline behavior | dispatch the workflow (`gh workflow run …`) and read its log; check the API serves the new data |

Hooks run the fast checks automatically after edits (see `.claude/settings.json`).
Python: use `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` locally
(plain `python3` may resolve to an older interpreter without pandas).

## Deploy

- **git push only.** Vercel and Render deploy from `main`. Never `vercel deploy`.
- `git pull --rebase --autostash` before pushing (tracked `logs/` are always dirty).
- Pipeline auto-deploy commits and the friends-game feature commit→push loop are
  pre-authorized. Dashboard (`dashboard.py`) work: ask before committing.
- The repo lives in iCloud-synced `~/Desktop`: if git reports a bad ref or the
  Next build fails with `ENOTEMPTY`, look for `* 2` duplicate files (move aside,
  don't delete) — sync duplicates, not code bugs.

## Working with Jack

- No emojis. Concise. Explain the why before implementing.
- **Teaching mode:** Jack is learning data science / ML / TypeScript. Give him the
  interesting core logic as a scaffolded task (types + TODO + tests written
  first), then review what he writes; Claude does the plumbing.
- Plan first (short design note or plan mode) for multi-file changes, not for
  one-line fixes.
