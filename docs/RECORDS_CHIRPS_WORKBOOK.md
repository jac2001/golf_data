# Group records and purposeful chirps

Learning scaffold, October 24, 2026. Not connected to production.

## First release

Let It Ride only, one group and season. Three records: most outright weekly wins,
longest winning streak, highest weekly lineup earnings. Include the model as an
opponent, labeled The Model. All tied record holders appear; tied weekly first
places do not count as outright wins and break a winning streak. A solo entry
cannot earn these competitive records. Missing a scheduled week breaks a streak.
Pending, incomplete, and estimated-money weeks award nothing and break streaks
until official results allow a fresh rebuild. This conservative rule prevents
silently claiming consecutive wins across an unresolved week.

Use the label “Highest weekly lineup earnings,” not “best performance.” Purses
and number of tournaments vary. Show the week and contributing events alongside
that record in the eventual UI. Do not compare this record across game modes.

## Your files and tasks

1. `web/lib/groupRecords.ts`: implement `computeGroupRecords`.
2. `web/lib/groupRecords.test.ts`: read examples and add your boundary tests.
3. `web/lib/recordChirps.ts`: implement `recordChirps`.
4. `web/lib/recordChirps.test.ts`: verify when the suggestions are truthful.

The adapter guard is implemented; both interesting functions are TODOs. Tests
are active and intentionally red until those functions are complete. No existing
chirp behavior changes. Do not ship as a finished feature while tests are red.

From web/:

```sh
node --test lib/groupRecords.test.ts lib/recordChirps.test.ts
npm test
npm run build
```

## Walkthrough: records

Filter by all three scope fields, then sort a new array by order. The adapter
must supply exactly one row for each scheduled calendar week, including missing
or pending weeks. Combine all tours belonging to that week BEFORE this helper;
never infer a week from settlement time or from adjacent tournament IDs.

Maintain Maps for total wins, current winning streaks, and best streaks. For each
qualifying week, find the maximum earnings and everyone with that amount. If
there is exactly one leader, increase their win count and current streak. Reset
all other current streaks to zero. If there is a tie or nonqualifying week, reset
all current streaks. Track highest earnings across every qualifying entry,
including ties. Finally, take each map's maximum and sorted holder IDs.

Useful TypeScript patterns:

```ts
const wins = new Map<string, number>();
const nextCount = (wins.get(userId) ?? 0) + 1;
wins.set(userId, nextCount);
const ordered = [...weeks].sort((a, b) => a.order - b.order);
```

`?? 0` supplies the initial value when a person has no entry. The spread creates
a copy so sorting cannot reorder the caller's data. Store integer cents to avoid
fractional-dollar equality issues. Don't use display names as identity.

Return null for no record. Zero-dollar earnings is still a valid earnings record
when at least two people actually competed. Zero wins is not a win record.
Add tests for missing a week, solo competition, all-zero earnings, season scope,
and frozen inputs. Add a test proving a pending middle week later finalized as
a win restores the full streak when history is recomputed.

## Walkthrough: chirps

Start with an early return unless final, played, and eligible. Compare before and
after record snapshots for the latest finalized week. A previous record must
exist: setting the first baseline is not breaking a record. Check that the
speaker actually holds the after record. If earnings increased, suggest the new
record line; if equal and they newly joined the holders, suggest the matched line.
Then check for an increased streak of at least two. Return at most two presets.

The `eligible` flag is an internal server-derived fact, NOT a client permission.
The adapter must prove that the latest week is complete and official and has
older qualifying history. `before` and `after` must use the same corrected source
snapshot, scope, and rule version. An unresolved latest week cannot fall back to
celebrating an older result. Add tests for lost records and deterministic output.

## Plumbing before release

- Build a members-only history adapter. Reuse canonical settlement and result
  matching rules (see recap route and resultLookup), not client-supplied totals.
  The recap currently groups nearby events; that is not a complete season history
  contract. Establish explicit week membership and include missing scheduled weeks.
- Resolve duplicate revisions to the authoritative latest result BEFORE calling
  `prepareRecordWeeks`; it rejects duplicates rather than guessing. Validate the
  mode, scope, order uniqueness, completeness, official-money flag, and runtime
  payload. TypeScript types alone do not validate JSON.
- Recompute records on corrected history. Cache by group, season, mode, rule
  version and settlement revision. Never permanently increment winner counters.
- Preserve provenance: contributing week IDs and event labels for each record
  holder. The exercise's compact return type intentionally lacks this UI metadata;
  extend it with evidence before shipping record cards or shareable claims.
- Add a collapsed Record Book below the matchup: three rows, holder names,
  value, season, and event/week detail. Keep the next pick above it on phones.
- Merge at most two record presets ahead of existing `chirpPresets`, deduplicate
  IDs, and apply the existing MAX_PRESETS limit across the combined list.
- POST /api/friends/chirps currently recognizes only LINES. Do not just add new
  IDs to that map: recompute and validate record eligibility server-side at send
  time. Build the context card there, preserve group membership checks, existing
  rate limits, reporting, removal, and reveal rules.
- Existing threads are per tournament, records are per week. Choose a deterministic
  anchor tournament from the week's configured event list and store week ID and
  result revision in the context card. Avoid duplicate prompts in both tours.
- Let the user tap to send. No automatic messages, push notifications, DMs, or new
  messaging center. Show a brief unavailable message if a correction invalidates
  the suggestion before sending. Existing sent chirps are historical snapshots;
  label corrected record context rather than silently rewriting someone's words.

## Context and purpose beyond records

Before play: use the existing neutral good-luck option. During play: retain
truthful existing leaderboard/model chirps. After final settlement: offer the new
record suggestions. Record-related claims must never use estimated live totals.
A target such as “defend your streak” can come later, backed by the same history.

## Done when

Core tests and full suite pass, build passes, adapter has integration coverage for
membership and settlement/corrections, no claims leak before final, and a real
member can view a record and choose to send a factual chirp. Current scaffold
finishes none of the server or UI integration steps above.
