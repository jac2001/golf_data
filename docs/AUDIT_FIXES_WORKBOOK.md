# Audit fixes: Jack's implementation workbook

October 24, 2026. Start with recommendation freshness, then work through the
remaining audit fixes in small, independently reviewable changes.

## What is scaffolded, and what is not

`web/lib/recommendationState.ts` contains the types, your TODO, and a safe placeholder.
`web/lib/recommendationState.test.ts` contains executable acceptance examples.
The helper is deliberately NOT connected to the site. Completing it alone does
not fix stale recommendations on the live Betting Board. The API and producer
must supply real timing metadata before integration.

The Fade market-pool work is already in commit `499bf96`. Keep that work separate;
this exercise does not change its pool, model, or scoring.

## 1. Understand the decision

A recommendation should only be offered as current when we can verify its event,
market, cutoff, generation time, and underlying odds time. A recently rewritten
file does not make an old Round 1 market available again.

Three results:

- `current`: verified, fresh, and before the market cutoff.
- `archive`: known to belong to another event, be closed, have started, or be stale.
- `unavailable`: missing or contradictory information; cannot verify availability.

This contract covers PRE-START recommendations. Do not apply it unchanged to
in-play recommendations. They need their own market lifecycle rules.

## 2. Read the TypeScript

`number | null` means the time may be unknown. Zero is a number, so use explicit
null checks rather than `if (!timestamp)`. `Number.isFinite()` rejects NaN and
Infinity. `kind` is a discriminant: checking it tells TypeScript which result
variant you have. `reason` explains that result without inventing a user-facing
sentence inside the logic.

Both objects are inputs. Supplying `nowMs` instead of calling `Date.now()` makes
this a pure function: the same inputs always produce the same output. Tests can
jump to a deadline without actually waiting.

Read the tests, implement one return branch, run them, and repeat. From `web/`:

```sh
node --test lib/recommendationState.test.ts
npm test
```

The scaffold intentionally has failing tests until you implement the function.
Do not deploy or commit it as a completed fix while they are red.

## 3. Worked solution

Replace only the function body in `recommendationState.ts` with the body below.
Try it yourself first; use this as a reference when stuck.

```ts
export function classifyRecommendation(
  recommendation: RecommendationTiming,
  context: RecommendationContext,
): RecommendationState {
  const { eventId, marketId, generatedAtMs, oddsAtMs, startsAtMs, marketState } = recommendation;
  const { nowMs, maxAgeMs } = context;

  // Validate context first: without it, we cannot compare events or time.
  if (!eventId?.trim() || !context.eventId.trim() ||
      !Number.isFinite(nowMs) || !Number.isFinite(maxAgeMs) || maxAgeMs <= 0) {
    return { kind: "unavailable", reason: "unverified" };
  }
  if (eventId !== context.eventId) {
    return { kind: "archive", reason: "wrong-event" };
  }
  // A definite closure is useful even if other metadata is absent.
  if (marketState === "closed") {
    return { kind: "archive", reason: "closed" };
  }
  if (!marketId?.trim() || generatedAtMs === null || oddsAtMs === null ||
      startsAtMs === null || !Number.isFinite(generatedAtMs) ||
      !Number.isFinite(oddsAtMs) || !Number.isFinite(startsAtMs)) {
    return { kind: "unavailable", reason: "unverified" };
  }
  // At the cutoff is already too late. Fresh output cannot reopen a market.
  if (nowMs >= startsAtMs) {
    return { kind: "archive", reason: "started" };
  }
  if (marketState !== "open" || generatedAtMs > nowMs || oddsAtMs > nowMs ||
      oddsAtMs > generatedAtMs) {
    return { kind: "unavailable", reason: "unverified" };
  }
  // Both the recommendation and the quote it used must be fresh.
  if (nowMs - generatedAtMs > maxAgeMs || nowMs - oddsAtMs > maxAgeMs) {
    return { kind: "archive", reason: "stale" };
  }
  return { kind: "current", reason: "verified" };
}
```

Why this order? An explicitly closed market stays archived even when a timestamp
is missing. Once all timestamps exist, a passed cutoff is enough to archive an
unknown-state market. For a future cutoff, unknown state is still unverified.
This keeps definite closure separate from uncertainty. The early `return`
statements also let TypeScript narrow nullable timestamps to numbers below.

Your extra test: prove that an unknown-state market with a passed cutoff is
archived, but one with a future cutoff is unavailable. Use `check()` in the test
file. Explain in a comment why those cases should differ.

Study questions:

1. Why does `>=` matter at the start time, but `>` at the freshness limit?
2. Why must old odds fail even if generation happened a minute ago?
3. Why would using page-load time disguise stale source data?
4. Why is a fantasy game's midnight pick deadline not a betting market cutoff?

## 4. Connect real data only after the helper passes

The current `Bet`/`BetsResponse` contracts in `web/lib/api.ts` do not carry all of
this metadata. `BestBet` has `generated_at`, but that alone is insufficient.
Do not fabricate missing values from the page clock, file modification time, or
current round label. Fifteen minutes in the tests is a fixture, not an approved
production freshness policy.

Implement in this order:

1. Find the producer of each recommendation artifact. Persist the canonical
   event and market identity, original generation time, quote observation time,
   and actual market cutoff with it. Define the supported market types and how
   each obtains a trustworthy cutoff. Store UTC instants; format for users later.
2. In `api/main.py`, validate the saved artifact's event and market lifecycle.
   The server must enforce the same availability policy, including requests to
   act on a recommendation. A disabled browser button alone is not enforcement.
   Unknown or unsupported market metadata must not become actionable by default.
3. Extend `web/lib/api.ts` to reflect the response. Validate external payloads at
   the boundary: TypeScript declarations do not validate runtime JSON. Preserve
   unknown times as null. Do not pretend a refreshed quote was used by an older
   recommendation; recomputation needs a new version with traceable inputs.
4. Make the hero and list read the SAME recommendation version and quote snapshot.
   Give that version a stable identity so the hero cannot show +137 while the
   matching list row shows +133 for the same supposed recommendation.
5. In `web/app/betting/page.tsx`, render current suggestions, archive labels, and
   unavailable states separately. Remove Tail from non-current suggestions. Show
   the source timestamp and market/round label; refresh classification at cutoff
   and when returning to the tab, with server validation as the final authority.
6. Check old R1 during R3, wrong event, missing odds, exact cutoff, refresh failure,
   and hero/list agreement. Confirm existing saved user history remains visible.
   Run the full tests and production build before connecting or shipping.

Do not clear a user's existing tails/history merely because a recommendation
expires. Archiving availability is different from deleting a historical choice.

## 5. Remaining audit work, in order

These are implementation tasks, not claims that the fixes have shipped.

| Order | Change | Acceptance check |
|---|---|---|
| 2 | Pair model probabilities with odds from the same prediction snapshot. Separate current market prices from pre-event comparisons. | A live quote cannot produce an apparent model edge against a frozen pre-event forecast. Missing matching snapshot shows unavailable. |
| 3 | Sort player recent results by canonical event dates, not tournament IDs. | Events with out-of-order IDs still display chronologically; unknown dates have an explicit fallback. Cover both recent and career results. |
| 4 | Limit weather and course-guide weather prose to event-local tournament dates. | No following-week forecast enters this week's narrative; partial coverage is labeled rather than filled in. |
| 5 | Distinguish last scored round from upcoming round across pages. | Round 2 completed / Round 3 upcoming is consistent on This Week, Live, and Betting; freshness refers to source data. |
| 6 | Keep WD/DQ status separate from numerical model-vs-finish movement. | A withdrawn golfer shows WD and no fabricated rank delta. Decide CUT treatment separately. |
| 7 | Put the next Round pick above reminders and organizer details on phones. | A member can find the next available pick immediately at 390px width. |
| 8 | Simplify player profiles: identity and useful recent form first, advanced detail later. | Remove repeated win/top-10 summaries; check selected controls in both themes. |
| 9 | Simplify mobile Live header and leader display. | Event title and refresh control fit without squeezing into many lines; tied leaders are represented honestly. |
| 10 | Label tee-time timezone, model rank, and pre-event probabilities. | A new user can explain the time and the meaning of the number beside a golfer. |
| 11 | Align How to Play with settlement and Round missed-cut rules. | Instructions explain pending/final states and do not imply a completed round is penalized retroactively. Verify against actual scoring. |
| 12 | Give Home's loading card a meaningful skeleton and failure state. | Slow/offline requests do not leave an unexplained empty outlined box. |

Before each task, recheck the current code and live page: concurrent fixes may
already have addressed it. Record source evidence and a reproduction, implement
one focused change, verify its boundary cases, then mark it done in the roadmap.

## 6. Fade: verify the new work, do not duplicate it

The market-favorites direction gives “fade three stars” a clear meaning. The new
opening-line pool is already implemented; its lifecycle still deserves a focused
review: immutable eligibility once picks open, event-specific snapshots, missing
coverage, deterministic ties at twentieth, and withdrawals. The model must use
the same eligible pool and deadlines as members. This workbook does not claim
that the new model has better predictive performance.
