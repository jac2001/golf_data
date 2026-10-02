# Advice view — design (Phase 2 step 6)

Drafted 2026-10-02. Status: decided (A split, B verdicts only, C 15-event horizon, D switch the model). Build order at the bottom.

## Goal

Inside Let It Ride, before a slate locks, answer for *this member*:
"Who's worth spending a use on this week, and who should I save — for
which event, and why?" It's the last unbuilt Phase 2 piece, and it's
what keeps the season-strategy optimizer from orphaning in the old
Streamlit dashboard.

## What exists today

| | Python `season_strategy.py` | TS `modelLetItRidePick` (Jack) |
|---|---|---|
| Runs | Streamlit dashboard only | Production (the model's picks) |
| Player universe | A fixed tracker roster | The whole field |
| This-week EV | Calibrated probs (+40% DG blend) | Calibrated probs |
| Future-event EV | Rank proxy × field difficulty × course fit × qualification (2025 field) × form-trend decay | Same probs re-priced at the bigger purse |
| Spend rule | Spend if this week ≥ the L-th best future window × urgency threshold; hot-streak override | Score = now − (EV at the L-th bigger purse − now), elite-only, capacity gate |
| Explains itself | Yes (`reason` strings) | No |

The TS re-pricing assumes a golfer's odds at a $20M Signature event
equal his odds at a $6M opposite-field event. That's the overstatement
the Python `_field_difficulty_mult` exists to correct (a WR #145 at the
Masters is ~0.05% to win, not 5%).

## Proposal: split "how good is each golfer, each week" from "what should *I* do"

```
Render (Python, same for everyone, cached per event)
  GET /api/advice/values?tournament_id=R2026554
    → for this week's field (top ~60 by EV):
        now_ev                         calibrated probs × this purse
        future: [{tid, name, start_date, purse, ev, why}]   next ≤15 events, same tour
          ev = rank proxy × field difficulty × course fit × qualification
               (season_strategy helpers, extracted into a pure function)

Vercel (TS, per member, uses Neon)
  GET /api/leagues/[id]/advice?tid=R2026554
    → loads the member's uses left (scope-aware: per tour or shared),
      slots, the values table, runs adviseSlate(), returns verdicts

lib/advice.ts — adviseSlate()   ← Jack writes the core (scaffolded)
    per golfer: { verdict: "spend" | "save" | "spent", score, saveFor?, reason }
```

Why the split:
- **The expensive part is shared.** Golfer values don't depend on who's
  asking, so Render computes them once per event (10-minute cache), not
  once per member per page view.
- **The personal part is cheap and testable.** `adviseSlate` is a pure
  function of (values, uses left, slots) — the same shape as Jack's
  existing model brain, so it gets node:test coverage like
  `slateHeadline`.
- **The model takes its own advice.** model-sync calls `adviseSlate`
  for the model member, replacing the re-pricing heuristic. One brain,
  and the model's picks finally come with reasons (shown after lock).

### Python refactor (no behavior change for the dashboard)

Extract from `get_season_strategy` a pure
`golfer_values(field_probs, upcoming_events, maps) -> list[dict]` using
the existing `_player_expected_prize`, `_field_difficulty_mult`,
`_effective_rank`, course-fit and qualification lookups.
`get_season_strategy` calls it for its tracker roster; the new endpoint
calls it for the field. Name keys go through `_name_key`; tracker-only
`_resolve_key` stays in the dashboard path.

DPWT v1: rank proxy + field difficulty only. The euro course history
(`data/euro_course_history/`) is keyed by course name, not course_key;
wiring it in is the same January work as the euro retrain's course fit.

### The decision rule (what Jack's function decides)

For a golfer with L uses left and future EVs sorted high→low
(e1 ≥ e2 ≥ …):
- The use you'd give up by spending now is the **L-th best** future
  window: with 3 uses left and windows of $900K/$700K/$400K, spending
  one now costs the $400K one, not the $900K one.
- Spend-worthy if `now_ev ≥ e_L` (this week is one of his top-L
  windows). Score for filling the slate: `now_ev − max(e_L − now_ev, 0)`.
- **Capacity:** only `slots` golfers fit per week, so not every
  "save for the Masters" is real — if eight golfers all want the
  Masters, only three get it. v1 keeps Jack's capacity gate idea
  (only golfers who would actually win a future slot have saving
  value); a full season plan (`get_optimal_season_plan`) is v2.

## UI (Let It Ride slate, before lock)

Private to the member. Two parts:
1. **Per-golfer verdict inline** in the pick list: a small "Spend" /
   "Save → Masters" tag, tap for the one-line why:
   *"$410K now vs $1.2M at the Masters (his 2nd-best window). 1 use
   left — save."*
2. **Optional "Suggested three"** (see decision B).

After lock: the model's reasons appear in Match Center next to its
picks ("The Model spent Fitzpatrick: top-3 window, 2 uses left").

## Decisions for Jack

**A. Where it runs** — the split above (recommended), vs all-TS
(simpler, keeps the purse re-pricing flaw), vs all-Python (per-member
Neon reads move to Render).

**B. How much to tell people.** Everyone in a group gets advice from
the same model. If it hands each member a "Suggested three", groups may
converge on identical slates — the roadmap's pick-diversity concern,
made worse by us. Options:
  1. Verdicts only (recommended): per-golfer spend/save tags + reasons
     on the golfers you look at; no ready-made lineup. You still choose.
  2. Verdicts + suggested three, opt-in per member.
  3. Group setting the owner turns on ("strategy hints").

**C. Horizon.** Remaining events on this tour's schedule, capped at 15
(recommended), including the 2027 schedule once the 2026 one runs out —
seasons are open-ended, uses persist.

**D. The model.** Switch model-sync to `adviseSlate` once it's tested
(recommended), or keep Jack's current brain and run the two side by
side for a few weeks to compare.

## Decided (2026-10-02)

A: split. B: verdicts only — no suggested lineup. C: same tour, ≤15
events, spilling into the 2027 schedule. D: model-sync switches to
adviseSlate once its tests pass.

## Build order

1. **Jack:** `golferVerdict` in `web/lib/advice.ts` until
   `npm test` (from web/) is green. Scaffold + 8 tests are in place.
2. **Claude:** Python `golfer_values()` extraction + `GET
   /api/advice/values` on Render (cached per event).
3. **Claude:** `GET /api/leagues/[id]/advice` (scope-aware uses left,
   reveal rules: your own advice only, pre-lock only).
4. **Claude:** verdict tags + reasons in the Let It Ride pick list.
5. **Together:** model-sync → adviseSlate; model reasons in Match
   Center after lock.

## Step 2 notes (built 2026-10-02)

- `scripts/predictions/advice_values.py` + `GET /api/advice/values`.
  Future EV anchors on THIS week's calibrated EV (the dashboard's rank
  proxy gives a world #25 ~12% to win anywhere — comparing that with a
  calibrated "now" makes everyone a save). Adjustments: purse ratio,
  field strength (S_now/S_future)^k (k 0.6 top-10, 1.0 else),
  course-fit ratio (PGA), qualification (2025 field; new restricted
  events: world top 60). Constants are v1 judgment calls — calibrate
  against settled weeks.
- No `key` from Python: the site keys uses with its own nameKey.
- DPWT horizon is short (the euro schedule only lists events DG has
  published, ~2 weeks out), so DPWT advice leans "spend" until the
  schedule file covers more of the season.
