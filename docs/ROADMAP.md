# Golf Edge — Roadmap

The working plan. Sessions pick from **Now** unless production is
broken. New ideas land in the backlog here FIRST and get sequenced —
they don't hijack the current session. (Rule adopted 2026-09-23 after
we noticed we were steering by whatever was shiniest.)

## North star

The Sunday ritual, for one group chat at a time: make picks Thursday,
trash-talk a model that plays under the same rules, watch the rivalry
line all weekend, share the recap card Sunday night. Everything ships
in service of that loop or of trusting it (data integrity, security,
honest states).

---

## Now (week of Oct 12 — DPWT-only week: India Championship; PGA resumes Oct 22, Bermuda)

The production loop now runs itself: data refresh → Tuesday predictions
→ model picks → lock → live Match Center → settlement → Sunday recap,
with the Vercel watchdog re-dispatching anything GitHub drops and the
integrity + freshness gates refusing to publish bad predictions.

- [ ] **Watch the first fully hands-off week.** India (Thu) is the first
      event since the España fix; Bermuda (Oct 22) the first PGA week
      with the watchdog armed from the start. Check Sentry for any
      "Watchdog: … dispatched" alert and Monday's recap.
- [ ] **Get Rick (and others) playing** — every group member adds pick
      data the season-format work needs; Rick's session also closes the
      cross-group 403 check and drives onboarding polish.
- [x] **Clerk dashboard:** (done Oct 15) turn off Clerk's own "delete account" so
      deletion always runs our cleanup (Jack, 1 minute).

## Next (October)

1. **PGA retrain: step 4 left** (steps 1-3 done Oct 14-15).
   Done: season-aware event dates (Jack, `event_dates.py`); training
   table ordered by date (`MERGE_ORDER`, verified: 81 order-dependent
   columns change, nothing else; independent recompute 100%); serving
   ordered by date + Jack's par features, stats-reviewed and live from
   Bermuda (Oct 22); event list refreshed weekly.
   Step 4: retrain on the date-ordered table (incl. 2025 data, which the
   production models never saw: they fit years < 2025) and compare with
   the current models under one identical walk-forward protocol; stats
   review; ship only if it beats year-to-year noise, and the group
   decides on a mid-season model change. Open data checks first:
   `R2021535` "U.S. Open (2021)" lists the 2025 winner (likely
   mislabeled rows); 9 stats-only events carry the wrong season's id.
   Also known: serving blends season SG with the prior year, training
   doesn't (median 0.075 strokes now, larger early-season); weather
   trains on observed, serves forecast.
2. **Move off pgatour.com data** (Oct 15). PGA TOUR (Grant, Oct 15)
   paused free ShotLink data "while we formulate a strategy for 2027 and
   beyond" and encouraged us to keep building; the Oct 6 verbal "free
   while non-commercial" can no longer be relied on long term. We still
   read pgatour.com's GraphQL for a lot (since the Feb 2026 first commit,
   before DataGolf): the model's strokes-gained + form stats
   (`multi_year_stats_scraper_fixed`, `fetch_form_stats`), world
   rankings, player database, live leaderboard, results + official prize
   money (`auto_record_results`), tee times, hole scores, weather widget,
   power rankings, betting profiles, withdrawals, colleges.
   Plan: (a) training SG from DataGolf historical raw data (licensed,
   round-level SG by category; the euro model already trains on it); do
   it WITH the retrain, since the table is being rebuilt anyway.
   (b) live scores/positions → DG in-play; results → DG raw data.
   (c) Prize money: DG has none; the open question to PGA TOUR (draft
   reply to Grant asks: OK to keep using posted results/prize money
   non-commercially meanwhile? Is there a paid license that fits, and
   whom to ask?). Fallback: purse × standard payout table, labeled
   estimated (as euro does). (d) No new pgatour.com dependencies; stay
   strictly non-commercial. Check DG's terms for display use (open).
3. **Mobile-first Golf Edge** (decided direction, Oct 15): most players
   won't be golf fans, so make join → pick → follow work on a phone in
   a minute. Design: `docs/MOBILE_FIRST_DESIGN.md` (decisions A–D decided Oct 15).
   Starts right after the retrain. First: instrument the flows, then
   one-tap invite links (biggest drop-off: today a friend signs in via
   the link, then must type a separately-sent code). The installable
   app and push already exist; missing are install guidance (iOS only
   allows push once installed) and a phone shell (bottom nav, split the
   1,654-line friends page). Native app: not until people return weekly.
   Speed (measured Oct 15, This Week): HTML 0.27s, JS boots ~1.3s,
   board ~4.6s. Fixed: /api/predictions called DataGolf live on every
   request (2.4-3.4s → ms) and a second fetch wave queued behind it.
   Remaining for the mobile work: data fetches start only after the JS
   boots (fetch on the server / prefetch), 1.8MB of JS on first load.
   After the fix (re-measured live): all data in 3.3s (was ~5.5s), but
   /api/predictions alone is 0.3s yet 1.7s in a page that fires six
   calls at once: Render's free tier is a fraction of a CPU, so parallel
   requests queue. Done: Render Starter ($7/mo, Oct 15) + empty tee-times
   cached + course cache 1h. Re-measured This Week: all data at 1.5s on a
   first visit, 0.9s on a repeat (was ~5.5s). Left: data still starts
   only after the JS boots, /api/events/open fires twice, 1.8MB of JS.
4. **What is the euro model for?** Walk-forward win log-loss: model
   0.0403, market 0.0370, 50/50 blend 0.0379. The blend makes the
   market worse on win. Before the January retrain: tune the blend
   weight (walk-forward, not in-sample), or show the model only where
   it adds information (made cut?).
5. **Licensing:** DataGolf follow-up on euro displays (nudge was due
   ~Oct 6 — confirm it went out). PGA TOUR: verbal "free while
   non-commercial" from Grant (Oct 6); wait for written terms, then
   replace the scraped GraphQL scorecards/weather with the official API.
6. **Move the repo out of iCloud (#6)** — ~/Desktop sync broke git refs
   twice, duplicated data files, and corrupted the Next build cache.
7. **Season formats that need weeks to accumulate**: pick diversity,
   College/Fade season boards — once there are real rows.
8. **Ongoing:** badge colors for new schools (`web/lib/schoolBadges.ts`).

### Done from this list (moved up and shipped)
- [x] PGA serving fixes (2026-10-14): unknown features filled with
  training medians (was 0.0, e.g. 0°F); weather via Open-Meteo forecast
  + training's summarise_weather; field_size/no_cut; SG around-the-green
  (stat 2570). Baycurrent raw win ranking vs old: rank corr 0.922.
- [x] pandas check (2026-10-14): CI's pandas 3.0.6 vs local 2.2.3 give
  IDENTICAL features (241 cols) and predictions (260 cols) for all 72
  Baycurrent players (harness: predict_tournament's own steps, DuckDB
  hidden as on CI). No pin needed. Found the zero-fill skew instead.
- [x] Euro purses verified + settled weeks rescored, sklearn pinned
  (2026-10-14): purses checked against the 2026 calendar; France and
  Spain rescored $3M -> $3.75M (`scripts/maintenance/rescore_euro_purses.py`,
  idempotent); scikit-learn==1.6.1 and xgboost==3.2.0 pinned to match
  every committed model's pickle.
- [x] Full DPWT schedule (2026-10-13/14) — every event for this season
  and next, provisional ids for TBD rows (never pickable), one
  resolver for every reader (`euro_schedule.resolve_event`, Jack),
  purse table matched through sponsor renames (`purse_for`, Jack).
- [x] Euro pipeline gate (2026-10-13) — `scripts/validation/euro_integrity.py`
  (checks by Jack): blocks on missing/failed/stale history or a top-10
  player without history; notes coverage and market agreement. Same day:
  window-bounded euro features (training now matches serving), Tuesday
  workflow skips PGA off weeks.
- [x] Euro model (2026-09-23) — serving `source: "model"`.
- [x] Phase 2 MVP (2026-09-30) — seasons, picks + per-member lock,
  standings with stars and banked/live split, model member with
  capacity-aware saving, per-tour budgets, settings editor, navigator.
- [x] Timezone-aware locks (event + Round Game, DST-safe lib/lockTime).
- [x] Weekly 3 retired into Let It Ride (2026-09-30).
- [x] Group Match Center + Sunday recap upgrade (2026-10-01).
- [x] Review cleanups (2026-10-01/02): live scorecards on demand, one
  event navigator for all games, Awaiting field, honest recap/lineup/
  field-count states, safe hydration, Course Guide numbers.
- [x] Checklist, first three (2026-10-02): cron routes fail closed on
  CRON_SECRET (Vercel + Actions), API flood guard + scorecard upstream
  budget + whitelisted cache-key params, /terms + /privacy + footer.
- [x] Visual hierarchy pass (2026-10-02): Match Center leads during
  live events (home card + nav), yellow budget (one primary per
  screen, quiet tabs/toggles), type floors (13px/12px via max()) and
  phone-width fixes, verified with the console audit on every page.
- [x] Sentry error monitoring (2026-10-02): web (DSN in code, prod only)
  + API (/health reports `sentry`), collection locked down (no bodies,
  headers, cookies, user info, locals, or AI prompts). Test route:
  /api/debug/sentry-test, gated by CHAT_PROXY_SECRET.
- [x] Advice view steps 1-4 (2026-10-02): Jack's golferVerdict (10
  tests, `npm test` imports lib/ directly), /api/advice/values,
  per-member route, Spend / Save tags in the pick list.
- [x] Match Center cards, round 2 (2026-10-02/03, from external review):
  three layers (am I winning / who am I watching / details on request)
  for Let It Ride AND College; "Estimated payouts if the tournament
  ended now" replaces bare "projected"; golfer rows with to-par and
  round progress; "Scores updated <viewer's time>" (DG reports
  course-local time, converted to UTC server-side); school monogram
  badges (colors, deliberately no logos); fixed degree-suffixed schools
  splitting alumni (FSU Finance, OSU Education, UCLA PoliSci).
- [x] Pre-strangers loose ends (2026-10-03): self-serve account
  deletion (Settings; purge verified on Neon with throwaway users),
  admin@playgolfedge.com forwarding via ImprovMX (MX + SPF on Vercel
  DNS, delivery confirmed in ImprovMX logs).
- [x] Advice constants calibrated (Jack, 2026-10-03): play rate by world
  rank × event kind, decay 0.995 (notebooks/analysis/advice_calibration).
- [x] First real settlement week (2026-10-05): settle job fixed (the
  CI auto-retrain blew the 25-min budget and cancelled publishing),
  recap fetches settlement fresh, Sunday recap rebuilt as a WEEKLY card
  (both tours, a star per tour, lineup earnings, Golf Edge branding,
  "Decided it" only when true). Model switched to adviseSlate for
  per-tour seasons, reasons stored (league_picks.reason) and shown in
  Match Center after lock.
- [x] Week of Oct 5–12: integrity gate (DG coverage / top-10 / sim
  agreement — blocks RBC Canadian, Biltmore, Baycurrent-style failures),
  freshness gate, fetchers refuse wrong-event payloads, Vercel watchdog
  armed (GITHUB_DISPATCH_TOKEN), advice across both tours, Sentry
  winners-only rule, compact advice + compact This Week table, Jack's
  "top pick" reason fix, settlement fixes ("F*" finishers, accent-folded
  event names). Baycurrent: Jack $1.23M vs model $358K (Brennan won).
- [x] Tie-for-first headline (Jack, test-first). Follow-up idea: a
  real test runner that resolves `@/` so tests import lib/ directly.

## Later

- **January retrain of the PGA model** (2025-26 data in, Tuesday trio
  wiring, calibration drift check) — this one genuinely waits for the
  season boundary. NEW (2026-09-25): the DG plan verifiably includes
  `/historical-raw-data/rounds` (per-player round-level SG splits,
  2016+) — the "no historical access" note was about prediction
  archives only. The retrain can train on DG historical SG, and the
  old plan to replace fetch_tournament_stats/fetch_form_stats with DG
  feeds is unblocked.
- **January euro retrain: add course fit** (added 2026-09-24). The euro
  model is pure form; `data/euro_course_history/player_course.csv`
  already holds per-player course records (avg_vs_par, avg_sg, rounds),
  and the France course-horses table (Yannik Paul −2.67, Bradbury,
  Winther) is exactly who a course-fit feature would boost. Build it as
  a training-table feature keyed by normalized course name with the same
  leakage wall (prior editions only), then retrain and re-benchmark vs
  the market. Also consider a world-rank/class prior — the other gap the
  Gerard-vs-Åberg week exposed.

## The two big builds (moved to Next, 2026-09-23)

### Euro model (data is banked)

Training data already in DuckDB (147,320 player-rounds with sg_total,
30,233 odds rows). Build: scoring-form + sg_total features, market
prior, walk-forward by season, live benchmark vs DG until it earns
`source: "model"` for E-events. Enables euro fade pool and full model
participation in euro weeks.

### Phase 2 — Let It Ride as a hostable game

The family league's FORMAT becomes a platform game. **Design
constraints (Jack, 2026-09-23):** season length is per-league
(start/end dates or week count — golf runs year-round worldwide),
tour selection per league (PGA / DPWT / both), uses-per-player and
players-per-week configurable (default 3/3).

**THE OPTIMIZER WORK CARRIES FORWARD — nothing gets orphaned.** The
league zone's UI died in Phase 1; its brains are the whole point of
Phase 2. Asset-by-asset:

| Asset | What it is | Phase 2 role |
|---|---|---|
| `scripts/predictions/season_strategy.py` (`get_season_strategy`) | uses-left, opportunity cost, save signals, weekly lineup | THE per-player strategy engine. Refactor: it reads ONE global tracker JSON today — parameterize its inputs (usage state, season window, purse map) so it serves any league instance and any member. This refactor IS the preservation. |
| ILP optimizer (pulp/CBC, ~8K binary vars) | optimal season plan under uses/slots constraints | "Season plan" view per player; re-runs weekly as a rolling replay |
| `scripts/strategy/dg_proxy_replay.py` | rolling-replay evaluation harness | how we validate the optimizer against any league's season, incl. the $19.2M/$27.0M/$41.3M/$111M ladder methodology |
| `scripts/validation/walk_forward_cv.py` | Jack's CV harness | validates the euro model AND any strategy backtest |
| Miss ledger + ladder (now in `/history/league`) | you-vs-machine accounting | becomes a per-player in-game view: "you vs your own Tuesday suggestion" |
| Spend-now bias finding (Lessons doc) | rolling optimizers overspend early | a design input: the in-game advisor must price option value or say it can't |

**Schema sketch** (build in January, not before): `leagues` (config:
season_start, season_end, tours, uses_per_player, players_per_week),
`league_members`, `league_picks` (user, league, event, players[],
uses enforced by count-per-player-per-league ≤ config). The model
joins as a member with the same budget. Tuesday-Call advice becomes a
per-member view computed from the parameterized strategy engine.

## Parked (deliberately, with reasons)

- **College exclusivity/drafts** — v1 (shared schools, best-2) needs
  real weeks first.
- **Survivor mode, badges, luck-vs-skill splits** — retention layer
  after the core ritual proves itself.
- **Public launch anything** — gated on licensing + checklist above.
- **Old league-site scraping** (league_picks_raw.html etc.) — dies
  when the league moves on-platform.
- **My League vs Star Budget earnings discrepancy** — moot: both
  pages retired; the wrap computes from the tracker directly.

## Standing gates

1. **DataGolf licensing** → euro displays, public growth.
2. **A second real user (Rick)** → cross-group auth test, pick-
   diversity data, first true recap.
3. **January** → euro model + Phase 2 (designed together; both are
   season-2027 features).

## Process

- Session start: open this file. Work the top unchecked **Now** item.
- New idea mid-session → add it here under the right horizon, keep
  working. If it's genuinely urgent, it replaces a Now item visibly.
- Ship = deployed + verified on prod + this file updated.
