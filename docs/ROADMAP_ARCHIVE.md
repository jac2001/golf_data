# Golf Edge — Roadmap archive

Sections retired from `docs/ROADMAP.md`, kept verbatim for the
history and the reasoning. Anything unfinished in them lives on as a
specific backlog item in the roadmap.

## Archived 2026-10-17 (Jack's roadmap review): the two big builds

Both shipped (euro model 2026-09-23, Phase 2 MVP 2026-09-30). The
unfinished optimizer work became backlog items under Later.

### The two big builds (moved to Next, 2026-09-23)

#### Euro model (data is banked)

Training data already in DuckDB (147,320 player-rounds with sg_total,
30,233 odds rows). Build: scoring-form + sg_total features, market
prior, walk-forward by season, live benchmark vs DG until it earns
`source: "model"` for E-events. Enables euro fade pool and full model
participation in euro weeks.

#### Phase 2 — Let It Ride as a hostable game

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

