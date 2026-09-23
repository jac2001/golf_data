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

## Now (this week — Bank of Utah launch week)

The first complete production week. Nothing new ships that isn't
needed for it.

- [ ] **Watch DG roll over** to Bank of Utah (Presidents Cup ends
      Sunday; expect the flip Sun night/Mon — checked 9/23: field=PC,
      odds=stale Biltmore). Then: Tuesday pipeline green, model places
      weekly trio + fade trio + school + R1 automatically.
- [ ] **Start the euro model** (moved up from January — see Next):
      training-table builder scaffolded; Jack writes the rolling-form
      feature functions. A PC week has no PGA game ops — perfect
      build week.
- [ ] **Jack + Rick play the week** (weekly picks minimum; fades and
      a school make the boards interesting).
- [ ] **First real Sunday recap** renders, gets shared, recap push
      fires Monday. Fix whatever the first real settle exposes.
- [ ] **France settles** Sunday (euro --results Monday cron) — first
      graded euro week for the Round Game + weekly picks.
- [ ] Cross-group 403 check with Rick's session (60 seconds, closes
      the last untested auth path).

## Next (October)

1. **Euro model, built now** (rescheduled 2026-09-23 — Jack: "golf is
   always happening"; the DPWT plays weekly all fall, so an early
   model gets live DG-benchmark reps every week instead of launching
   cold in January). Data is banked; sequence: training table →
   train + walk-forward → live weekly benchmark vs DG → earns
   `source: "model"` for E-events. Building our own model on DG
   features matches existing live PGA practice; the licensing letter's
   clarifications remain pending but gate only DG-prediction DISPLAY.
2. **Phase 2 — Let It Ride, built now, shaken down this fall**: the
   customizable-season design means an October–December "Fall Series"
   league (PGA fall + DPWT) is the format's beta season before the
   family league's 2027 stakes. Design after the euro training table
   is underway.
3. **DataGolf licensing resolution.** Reply timing unknown; follow up
   after 2 weeks. It gates: euro DG-prediction display
   (`SHOW_DG_EURO_PREDS`) and any public growth — NOT our own model
   work. The hold on their displays stays until written permission.
2. **Season formats that need weeks to accumulate**: watch pick
   diversity (do real groups converge on chalk?) before inventing
   mechanics; College/Fade season boards earn their first real rows.
3. **Production checklist, pre-strangers tier** (from the compete
   assessment): ToS/privacy pages, Sentry, rate limiting on public
   endpoints, CRON_SECRET set, Render league endpoints behind a
   shared secret if anyone outside the family gets a link.
4. **Onboarding polish** driven by the next playtest: first-run
   pointers on the six tabs; invite-flow friction.

## Later

- **January retrain of the PGA model** (2025-26 data in, Tuesday trio
  wiring, calibration drift check) — this one genuinely waits for the
  season boundary.

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
