# Golf Edge — Roadmap

The working plan. Sessions pick from **Now** unless production is
broken. New ideas land in the backlog here FIRST and get sequenced —
they don't hijack the current session. (Rule adopted 2026-09-23 after
we noticed we were steering by whatever was shiniest.)

## North star

**Golf Edge turns professional golf into a weekly rivalry among
friends: use your golf knowledge, or our guidance, to beat them.**
(Jack's launch plan, Oct 15: `docs/Audience_Product_Launch_Plan.pdf`.)

The main product question is **"Was this week fun enough to play
again?"** A more accurate model can help; so can a close matchup, an
understandable leaderboard, or a recap a friend shares. Keep improving
the model, but judge the product by repeat group play, not sign-ups.

The loop, for one group chat at a time: receive an invite → join the
right group → make picks → understand the matchup → see the result →
play again. The model plays under the same rules as an opponent people
enjoy beating. Everything ships in service of that loop or of trusting
it (data integrity, security, honest states, data rights).

**Development rule (before adding anything):** will this help someone
join, make picks, follow their friends, or return next week? If the
answer is unclear, it goes in the backlog until the next tournament
teaches us.

**Per game, three questions** (make the existing modes satisfying
before adding new ones): what makes choosing interesting? what makes
following the tournament exciting? what makes someone want a rematch,
even after losing? (College: school loyalty. Fade: rooting against a
favorite. Let It Ride: lineup strategy and season decisions.) The pilot
tells us which ones create conversation.

**First audience:** golf fans who enjoy fantasy sports and can bring a
few friends; the most valuable early user is the ORGANIZER. Beginners
are welcome but aren't the early growth plan.

**Postponed until the pilot shows a need:** new game formats, a native
app, paid marketing, more complex prediction displays, another major
redesign, subscriptions or monetization. (Reliability, privacy, scoring
accuracy and data permissions continue regardless.)

---

## Now (Oct 17; PGA resumes Oct 22, Bermuda)

The production loop runs itself: data refresh → Tuesday predictions →
model picks → lock → live Match Center → settlement → Sunday recap, with
the Vercel watchdog re-dispatching anything GitHub drops and the
integrity + freshness gates refusing to publish bad predictions. Jack's
review (Oct 17): don't wait on a long build list; get one group playing
and fix what watching them reveals.

1. [ ] **Verify the unattended cycle through settlement and recap.**
       Bermuda is the first PGA week with the watchdog armed from the
       start. Tuesday Oct 20: read the prediction run's log (first live
       "Weather (Open-Meteo forecast)", "Par-scoring percentiles", the
       "at this event" wording in the model's reasons, Bermuda's
       /api/golfer-form). Monday Oct 26: settlement + recap landed, no
       Sentry "Watchdog: … dispatched" alerts.
2. [ ] **Finish the mobile blockers and verify group isolation.** The
       "Before the first group" list below. Group isolation with
       CONTROLLED test accounts (two groups, two throwaway users): one
       group can't see another's members, picks, boards, invites or feed
       (every route through lib/gameScope.ts should 403). Not Rick's job.
3. [ ] **One place for data permissions.** What we use from DataGolf
       and PGA TOUR, what we have (subscription access vs confirmed
       permission for each use: public display, game scoring, derived
       outputs, any commercial use), and the open questions. See #2, #5.
4. [ ] **Recruit one organizer and watch their group play** (Rick is
       the natural first), using the plan's invitation. Tournament 1
       of the pilot: watch first use without coaching.
5. [ ] **Fix the largest obstacle that session reveals.**
6. [ ] **Move the repo out of iCloud** (~/Desktop sync broke git refs
       twice, duplicated data files, corrupted the Next build cache, and
       dropped unsaved edits more than once). Recurring disruption to
       everything else, so it moves up from Next.

## Pilot

The milestone: five organizers, each bringing three to six friends,
three tournaments (1: watch first use, 2: engagement, 3: repeat play
with less prompting); three of five groups active through all three
events with multiple players each. Start with ONE group; don't wait to
assemble all five. The distinction that matters: what must work before
someone plays, versus what we improve because we watched them play.

### Before the first group plays (required)

- [x] **Mobile joining** (Oct 15): one-tap invite links, phone tab bar,
      Friends page redesign (group bar + sheet, game picker, per-game
      tabs, one-line event bar), install card + reminders.
- [x] **Clear saved confirmation** (Oct 17, all four games): "You're in"
      sheet naming every pick and the lock; a "Saved" note per pick.
- [x] **Golfer why lines** (Oct 16): one true sentence per golfer on the
      Let It Ride cards and This Week (Jack's `web/lib/whyLine.ts`, facts
      from `/api/golfer-form`: real last-5 finishes and past editions of
      the event, "at this event" since venues before 2026 aren't known,
      no-cut editions excluded).
- [x] **Results reachable** (Oct 16): finished Let It Ride weeks show
      results and the field; Round/Fade/College keep past events.
- [ ] **Group isolation verified** with controlled test accounts (Now #2).
- [ ] **Trustworthy scoring and locks** confirmed on a real PGA week
      (Bermuda: locks fire on time, settlement matches official results).
- [ ] **Understandable matchup and results**: the Match Center check
      against the plan's questions (am I winning, who am I chasing,
      which golfers help or hurt, live estimate or final), answer first.
- [ ] **Data permissions fit what the pilot shows** (Now #3).
- [ ] Test: a first-time player joins and submits valid picks without
      anyone explaining the interface.

### Improve during the pilot (learn from watching, don't block on)

- [x] **"Help me pick"** (Oct 19, Let It Ride: Jack's
      `web/lib/helpMePick.ts`, spend golfers before save ones): an optional, editable suggested lineup
      that respects eligibility and remaining uses, one plain sentence
      per golfer (the why lines), clearly not a guaranteed outcome.
      Test: a beginner makes picks and can say what must happen to win.
- [ ] **The organizer's view**: who has joined and who still needs to
      pick, without revealing hidden picks; share the result and start
      the next week. Test: an organizer runs a second tournament alone.
- [ ] **Group chirps** (Jack, Oct 17): one thread per group per
      tournament (past weeks kept), "Send a chirp" ON the matchup and
      result cards, a few preset lines tied to what just happened ("Don't
      look now", "Check the leaderboard", "So much for the expert",
      "There's always next week") plus short custom messages, simple
      reactions, an unread badge inside the group. Always sent by the
      player, never automatic. Members only; report a message, organizer
      can remove it; a shared card never reveals hidden picks. Social
      notifications separate from game reminders, with mute. Skip for
      v1: DMs, images, alerts on every standings change. The question to
      test: will friends talk here when they already have a group text?
      The reason to would be the game context next to the message.
- [ ] **Recap check**: who won and by how much, the turning point the
      data supports, how the group did against the model, the next event
      with a way to play. Lineup earnings never read as cash.
- [ ] **Weekly scorecard** from `app_events` (logging since Oct 15):
      invited players who submit first picks; first-week players who
      pick again; groups with several active players across all three
      events; Match Center checks during play; invites sent unprompted;
      support needed per group. Optional golf-fan self-description.
- [x] Small (Oct 19): why lines on the Round and Fade pick lists; the
      event bar's live round ("Live · Round 2", fresh live data only).

## Next (alongside the pilot; the retrain stays January)

1. **PGA retrain: decided Oct 15, don't ship mid-season; January.**
   Steps 1-3 done and live (dates, date-ordered table + serving, Jack's
   par features, weekly event list). Step 4 compared, all models scored on
   the date-ordered features serving now produces
   (`scripts/validation/compare_retrain.py`, stats-reviewed; 3 fit seeds;
   fake 2021 U.S. Open dropped from both tables):
   - Same training years, clean 2026 test: date-ordered training better,
     top5 log-loss -2.6% on all 3 seeds (win mixed, top10 ~0).
   - Ship test (production fit <2025 vs candidate fit <2026, on 2026):
     candidate WORSE on all 3 seeds (win +1.8%, top5 +0.8%, top10 +0.6%).
     So ADDING 2025 hurt 2026. Unexplained: before January, inspect the
     2025 rows (feature coverage, e.g. DG-archive features; recency
     weighting leaning on an unusual year).
   - 2025 is in-sample for the production features (chosen on 2025 test
     AUC), so judge on 2026 (+2024 loosely).
   January: retrain on the date-ordered table with full 2026, ideally on
   DataGolf SG (#2), judged by compare_retrain.py.
   Known: serving blends season SG with the prior year, training doesn't;
   weather trains on observed, serves forecast.
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
   Plan: (a) training SG from DataGolf historical raw data (in our
   subscription; permission for each use, e.g. public display of derived
   numbers, still to confirm; round-level SG by category; the euro model already trains on it); do
   it WITH the retrain, since the table is being rebuilt anyway.
   (b) live scores/positions → DG in-play; results → DG raw data.
   (c) Prize money: DG has none; the open question to PGA TOUR (draft
   reply to Grant asks: OK to keep using posted results/prize money
   non-commercially meanwhile? Is there a paid license that fits, and
   whom to ask?). Fallback: purse × standard payout table, labeled
   estimated (as euro does). (d) No new pgatour.com dependencies; stay
   strictly non-commercial. Check DG's terms for display use (open).
3. **Mobile-first Golf Edge** (Oct 15). Recruit golf fans who organize
   groups; make joining easy for their less experienced friends. Design:
   `docs/MOBILE_FIRST_DESIGN.md`. What shipped is under Pilot; what's
   left here is speed: data fetches start only after the JS boots
   (fetch on the server / prefetch), /api/events/open fires twice, 1.8MB
   of JS on first load. (Re-measured Oct 15 after Render Starter: This
   Week's data at 1.5s first visit, 0.9s repeat, was ~5.5s.) Native app:
   not until people return weekly.
4. **What is the euro model for?** Walk-forward win log-loss: model
   0.0403, market 0.0370, 50/50 blend 0.0379. The blend makes the
   market worse on win. Before the January retrain: tune the blend
   weight (walk-forward, not in-sample), or show the model only where
   it adds information (made cut?).
5. **Licensing / data permissions** (see Now #3). PGA TOUR (Grant,
   Oct 15) paused free ShotLink data "while we formulate a strategy for
   2027 and beyond"; the Oct 6 verbal "free while non-commercial" can't
   be relied on, and nothing is in writing. Open with PGA TOUR: may we
   keep using posted results / prize money non-commercially meanwhile;
   is there a paid license that fits, and whom to ask (draft reply to
   Grant saved in Gmail, not yet sent). Open with DataGolf: display of
   derived numbers on a public site (euro displays nudge was due ~Oct 6;
   confirm it went out). Until answered: no new pgatour.com dependencies,
   strictly non-commercial.
6. (moved to Now: the iCloud move)
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

- **Season plan view per member** (from the archived Phase 2 plan): the
  ILP optimizer (pulp/CBC) as a "your season plan" view, re-run weekly
  as a rolling replay. Needs `season_strategy.get_season_strategy`
  parameterized (it reads ONE global tracker JSON today: usage state,
  season window, purse map per league/member).
- **"You vs your own Tuesday suggestion"**: the miss ledger + ladder
  (`/history/league`) as a per-member in-game view.
- **Optimizer validation per league** with `scripts/strategy/dg_proxy_replay.py`
  (and the spend-now bias finding: the advisor must price option value
  or say it can't).
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

## Parked (deliberately, with reasons)

- **College exclusivity/drafts** — v1 (shared schools, best-2) needs
  real weeks first.
- **Survivor mode, badges, luck-vs-skill splits** — retention layer
  after the core ritual proves itself.
- **Public launch anything** — gated on data permissions (Now #3) and the pilot.
- **Old league-site scraping** (league_picks_raw.html etc.) — dies
  when the league moves on-platform.
- **My League vs Star Budget earnings discrepancy** — moot: both
  pages retired; the wrap computes from the tracker directly.

## Standing gates

1. **Data permissions** (Now #3) → public growth, any commercial use,
   euro displays.
2. **One group playing through a tournament** (Now #4) → the rest of
   the pilot; learn before building more.
3. **January** → the PGA retrain and the euro course-fit retrain.

## Process

- Session start: open this file. Work the top unchecked **Now** item.
- New idea mid-session → add it here under the right horizon, keep
  working. If it's genuinely urgent, it replaces a Now item visibly.
- Ship = deployed + verified on prod + this file updated.
