/**
 * helpMePick.ts — "Help me pick": an editable suggested lineup.
 * =============================================================
 * The launch plan's second build priority: help a beginner make their
 * first decision. Optional and editable: a button fills the empty slots
 * with suggestions the person can accept, swap or ignore, each with one
 * plain sentence (Jack's why lines), and the screen says plainly that a
 * suggestion is not a guaranteed outcome.
 *
 * The ranking already exists: lib/advice.ts adviseSlate (Jack's
 * golferVerdict) scores every golfer for THIS member's uses left (spend
 * now vs save for a bigger week). The model picks its own lineup with it.
 * This function turns those scores into suggestions for a person.
 *
 * Pure function, no imports from "@/": `npm test` runs it.
 */

export type Candidate = {
  name: string;
  /** nameKey(name): how picks and uses are matched. */
  key: string;
  /** This member's uses left on him (0 = can't be picked). */
  usesLeft: number;
  /** adviseSlate's verdict for this member, or null when the advice
   *  values aren't available this week (DP World Tour, off-week). */
  advice: { verdict: "spend" | "save" | "spent"; score: number } | null;
  /** The model's win chance (0–1), or null. */
  winProb: number | null;
  /** Jack's whyLine for him ("" when there's nothing honest to say). */
  why: string;
};

export type Suggestion = {
  name: string;
  key: string;
  /** Already in their lineup (kept as is), not a new suggestion. */
  kept: boolean;
  /** The one line under the name on the suggestion card. */
  line: string;
};

// ── TODO(Jack): helpMePick ────────────────────────────────────────────────────
//
// field:  everyone in this week's field (any order).
// picked: keys already in this person's lineup, in pick order.
// slots:  how many golfers make a full lineup.
//
// Return the full lineup: their existing picks first (kept: true, in their
// order), then suggestions (kept: false) for the empty slots.
//
// Facts the tests pin:
//   - Never suggest a golfer they can't pick: usesLeft 0, or verdict "spent".
//   - Never suggest someone already in the lineup.
//   - Existing picks are kept, untouched, first.
//   - Fill only the empty slots; fewer if not enough golfers are eligible.
//     Never more than `slots` in total.
//   - Rank by advice score when advice exists; otherwise by winProb
//     (null last). Same input, same answer.
//   - `line` is never a promise and never a money amount (no "$").
//
// Decisions that are yours (reason in a comment):
//   a. A "save" golfer (worth more at a bigger event later): suggest him
//      anyway if he's the best score, or skip every "save" golfer while a
//      "spend" one is left? A beginner doesn't know they're burning a use.
//   b. The line: his why line, or something about the choice itself
//      ("Good week to use him")? What when `why` is ""?
//   c. Mixed weeks: some candidates have advice and some don't (a golfer
//      missing from the values). Where do the ones without advice go?
//
// Done when: npm test (from web/) passes lib/helpMePick.test.ts, plus one
// test of your own for decision (a).

export function helpMePick(field: Candidate[], picked: string[], slots: number): Suggestion[] {
  // a: follow the Spend / Save tag: every "spend" golfer before any "save"
  //    one, so a beginner never burns a use the advice says to keep.
  // b: the card shows his why line; with none, a plain "Model's suggestion
  //    this week" (no promise, no money).
  // c: golfers with advice first (their score accounts for uses left), then
  //    the rest by win chance, unknowns last.
  const byKey = new Map(field.map(c => [c.key, c]));
  const kept: Suggestion[] = picked
  .map(k => byKey.get(k))
  .filter((c): c is Candidate => c !== undefined)
    .map(c => ({ name: c.name, key: c.key, kept: true, line: c.why }));
  
  const taken = new Set(picked);
  const eligible = field.filter(c =>
  !taken.has(c.key) &&               // not already in the lineup
  c.usesLeft > 0 &&                  // has a use left
  c.advice?.verdict !== "spent"      // and the advice doesn't say spent
  );
  eligible.sort((a, b) => {
  // c: with advice first
  const aHas = a.advice !== null, bHas = b.advice !== null;
  if (aHas !== bHas) return aHas ? -1 : 1;

  // a: spend before save
  const aSave = a.advice?.verdict === "save", bSave = b.advice?.verdict === "save";
  if (aSave !== bSave) return aSave ? 1 : -1;

  // then the higher score first; with no advice, the higher win chance first (null last)
  if (a.advice && b.advice) return b.advice.score - a.advice.score;
  return (b.winProb ?? -1) - (a.winProb ?? -1);
  });
  
  const open = Math.max(0, slots - kept.length);
  const chosen = eligible.slice(0, open);
  const suggested: Suggestion[] = chosen.map(c => ({
  name: c.name, key: c.key, kept: false,
  line: c.why || "Model's suggestion this week",   // b
}));
return [...kept, ...suggested];

 
  
}
