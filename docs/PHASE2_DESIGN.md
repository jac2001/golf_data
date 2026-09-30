# Phase 2 — Let It Ride as a hostable game

Design doc. Started 2026-09-28. Decisions marked **(Jack)** are settled;
**OPEN** items need a call before the build step that depends on them.

## Settled decisions

- **A league is a mode on a group (Jack).** A group starts a Let It Ride
  season; same members, same invite flow, same group scoping. A group
  can run many seasons over time, one active at a time.
- **Game first (Jack).** MVP = picks, uses enforcement, standings, and the
  model playing as a member. The per-member advice view (the
  parameterized strategy engine) is the fast follow, not a launch gate.
- **Budget: 3 uses per golfer, 3 golfers per week (Jack, "I like 3").**
  Both configurable per league; these are the defaults.
- **Scoring: real prize money**, summed across the season — the family
  league's DNA. Graded by the same `/api/results/earnings` every other
  game uses (settled Monday, projected live during the weekend).
- **Reveal at lock, locks on the tour's clock** — inherited from the
  existing games (events/open `locked`, now timezone-aware).

## The Fall Series (beta season)

Opens the week of **Oct 8** (the week after Bank of Utah).

| Week of | PGA | DPWT |
|---|---|---|
| Oct 8 | Baycurrent Classic | Open de España |
| Oct 15 | — (off week) | TBD (DG publishes ~2 wks ahead) |
| Oct 22 | Bermuda Championship | TBD |
| Oct 29 | Mexico Open | TBD |
| Nov 5 | World Wide Technology | TBD |
| Nov 12 | Austin Championship | TBD |
| Nov 19 | RSM Classic | TBD |
| Dec 3 | Hero World Challenge (20-man) | — |

## Schema (Neon)

```sql
CREATE TABLE leagues (
  id               serial PRIMARY KEY,
  group_id         int  NOT NULL REFERENCES groups(id),
  name             text NOT NULL,
  season_start     date NOT NULL,
  season_end       date,                 -- NULL = open-ended season
  tours            text[] NOT NULL DEFAULT '{pga,euro}',
  uses_per_player  int  NOT NULL DEFAULT 3,
  players_per_week int  NOT NULL DEFAULT 3,
  status           text NOT NULL DEFAULT 'active',   -- active | complete
  created_by       text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);
-- one active season per group
CREATE UNIQUE INDEX one_active_league ON leagues (group_id) WHERE status = 'active';

CREATE TABLE league_picks (
  id            serial PRIMARY KEY,
  league_id     int  NOT NULL REFERENCES leagues(id),
  user_id       text NOT NULL,          -- 'model' for the model member
  tournament_id text NOT NULL,
  player_name   text NOT NULL,
  player_key    text NOT NULL,          -- nameKey(): sorted lowercase tokens
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (league_id, user_id, tournament_id, player_key)
);
```

The UNIQUE constraint stops double-picking one golfer in one week.
The two budget rules (uses per golfer ≤ `uses_per_player`, golfers per
week ≤ `players_per_week`) are count checks enforced in the pick route
inside the same transaction as the insert — server-side, like every
other game rule. The client only ever displays them.

## Routes (Next.js, Clerk-authed, membership-checked)

| Route | Does |
|---|---|
| `POST /api/leagues` | group owner creates a season (config above) |
| `GET /api/leagues?group_id=` | the group's active league + config |
| `GET/POST/DELETE /api/leagues/[id]/picks` | my picks this week; add/remove with enforcement; others' picks hidden until lock |
| `GET /api/leagues/[id]/standings` | season earnings per member, projected during live weeks |
| `GET /api/leagues/[id]/uses` | my uses-left per golfer (the pick screen's budget meter) |

## The model as a member

Joins every league automatically (`user_id = 'model'`), same budget,
same locks. Its picks come from a new `modelLetItRidePick()` in
`web/lib/modelBrain.ts`, called by model-sync alongside the other
games. This is the interesting function — the spend-vs-save decision:
a golfer's expected payout this week against the value of keeping a use
for a better week later. The Lessons doc's spend-now bias finding is the
design input: a greedy picker burns elite golfers in October.

## The fast follow — advice view

`get_season_strategy()` reads one hardcoded tracker file today. The
refactor makes it stateless: `(usage_state, season_events, purse_map)`
in, strategy out. Render runs the engine; the Vercel route passes each
member's usage state from Neon in the request (Render never touches
Neon). That refactor is the whole preservation plan for the optimizer.

## Build sequence

1. **DDL + create-season flow** — plumbing (Claude).
2. **Pick route with enforcement** — `validateLeaguePick()` scaffolded;
   **Jack writes the rule logic** (a good TypeScript lesson: counts,
   early returns, typed errors).
3. **Standings** — reuse results/earnings (Claude).
4. **Model member** — **Jack writes `modelLetItRidePick()`** from a
   scaffold; Claude wires model-sync.
5. **Friends Game UI tab** — pick screen with budget meter, standings.
6. *Fast follow:* stateless strategy engine + per-member advice view.

Target: steps 1–5 live before the Oct 8 lock.

## Resolved (Jack, 2026-09-30)

1. **The tours are separate slates.** Each week a member makes one set
   of picks for the PGA event and a separate set for the DPWT event —
   3 golfers per slate. Since the two events have different
   `tournament_id`s, "golfers per week" is enforced per tournament, and
   standings show a PGA total, a DPWT total, and the combined total.
2. **No season end yet.** `season_end` is nullable; the Fall Series runs
   open-ended and the owner closes the season when the group decides.
3. **A use belongs to the golfer, across tours.** Uses are counted per
   `(league, member, golfer)` over every tournament — picking Åberg in
   Spain spends the same budget as picking him at a PGA event.
