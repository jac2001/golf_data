# Match Center scoring exercise

The existing details panel mixes scoring, model reasoning and possible moves.
The new panel answers one question: how does my lineup produce this total?
It is presentation only; the API continues to score and rank the game.

## Your task

Implement `buildScoreBreakdown` in `web/lib/scoreBreakdown.ts`. Read its TODO
for the full contract. The types, wording, UI and page wiring are ready.

1. Guard clauses: return null before lock, without a lineup, or without golfers.
2. `.map()` transforms golfers into rows. `null` means Pending; 0 is real money
   worth zero. Don't use `if (earnings)` to check whether earnings exist.
3. `.some()` checks whether any row is pending. An incomplete lineup must not
   display a complete total. Otherwise preserve the API total, not a new sum.
4. Choose title, note and rule. Final estimates must not say official.
5. Return the object matching the output type. Don't mutate input.

College callers pass only counting alumni. Don't sort the whole school roster
or recalculate which two count. Add one test yourself: a College school with
only one counting alumnus should still display its real earnings.

## Tests

From `web/`:

```sh
node --test lib/scoreBreakdown.test.ts
npm test
npm run build
```

Tests are intentionally active and red while the helper is a stub. Don't remove
assertions or skip tests. Work through each failure. The stub returns null so
existing Match Center UI stays unchanged until you complete it.

## Supplied plumbing

`web/app/match/_components/ScoreBreakdownPanel.tsx` supplies a native expandable
panel: total, status note, rule, golfer names/positions and earnings. It uses full
dollar amounts rather than abbreviated millions. Unknown values read Pending.

`web/app/match/page.tsx` calls the helper for Let It Ride and College. A returned
object activates the new panel and renames the old one “Matchup insights and
data details.” Returning null leaves the old panel unchanged. No additional
fetches, database writes, dependencies or scoring changes.

## Check after implementation

At 375px and desktop, light and dark: live estimates; settling; official final;
estimated final; a real zero; an incomplete lineup; no entry; open picks;
College counting alumni only. Tab to the summary and use Enter/Space to open it.

The old detail panel remains for this first exercise. After checking real data,
reduce duplicate explanations and separate model reasoning further if needed.
Round/Fade aren't rendered by these Match Center cards and need their own rules
if added later.

Boundary: this helper detects only missing data signaled by the response. It
cannot diagnose a plausible position paired with an incorrect numeric amount.
