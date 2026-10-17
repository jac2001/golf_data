/**
 * pickConfirm.ts — what the confirmation says after someone saves a pick.
 * =======================================================================
 * The launch plan's must-understand list includes "whether their picks
 * have been saved". A list that quietly updates doesn't answer it, so
 * every save gets a message, and a COMPLETE lineup gets a confirmation
 * sheet (phone mockup, docs/MOBILE_FIRST_DESIGN.md flow 2):
 *
 *   You're in
 *   Scheffler, McIlroy, Åberg. Picks lock Wed at midnight ET.
 *
 * Pure function, no imports from "@/": `npm test` runs it. The sheet
 * (components/PickConfirm.tsx) draws whatever you return.
 */

export type ConfirmInput = {
  /** Every golfer (or school) this person has in for this event, in the
   *  order they picked. Includes the one just saved. */
  picked: string[];
  /** How many make a full entry (Let It Ride: the league's players per
   *  week; Fade: 3; College: 1). */
  needed: number;
  /** The lock part of Jack's eventStatusLine, e.g. "locks Wed at midnight
   *  ET" or "locks in 3h 12m". "" when unknown. */
  lockDetail: string;
  /** This device gets pick reminders: true, false, or null (unknown). */
  remindersOn: boolean | null;
};

export type ConfirmCopy = {
  /** The big line: short. */
  title: string;
  /** One or two sentences under it. */
  body: string;
  /** true → the full sheet ("You're in"); false → a small "saved" note. */
  complete: boolean;
};

/** Longest body the sheet shows without scrolling on a phone. */
export const MAX_BODY = 140;

// ── TODO(Jack): confirmCopy ───────────────────────────────────────────────────
//
// Facts the tests pin:
//   - complete = picked.length >= needed.
//   - Complete: the title says they're in; the body names EVERY pick and
//     says when picks lock (if lockDetail isn't "").
//   - Not complete: the title says the latest pick was saved; the body
//     says how many are left ("2 of 3 picked, 1 to go").
//   - Never claim a reminder that isn't set up: only remindersOn === true
//     may promise "we'll remind you".
//   - No money words; nothing about winning.
//   - body at most MAX_BODY characters.
//
// Decisions that are yours (reason in a comment):
//   a. Names: full names, or last names ("Scheffler, McIlroy")? Last names
//      are shorter; two golfers can share one (two Højgaards).
//   b. Reminders off (false) or unknown (null): nudge them to turn
//      reminders on, or say nothing? The install card already asks after
//      the first pick, so think about asking twice.
//   c. One pick needed (College): "You're in" still, or something that
//      reads better for a single school?
//
// Done when: npm test (from web/) passes lib/pickConfirm.test.ts, plus one
// test of your own for decision (a).

export function confirmCopy(c: ConfirmInput): ConfirmCopy {
  // a: full names: clearer than last names, and the Højgaard twins can't be confused
  // b: reminders off or unknown → a short nudge; on → say we'll remind them
  // c: "You're in" for a single school too: one pick is still a full entry
  const n = c.picked.length;
  const lock = c.lockDetail ? ` Lineup ${c.lockDetail}.` : "";

  if (n >= c.needed) {
    const remind = c.remindersOn === true
      ? " We'll remind you next week."
      : " Turn on reminders in Settings.";
    return {
      title: "You're in", body: `${c.picked.join(", ")}.${lock}${remind}`,
      complete: true
    };
  }
  const latest = c.picked.at(-1) ?? "";
  return {
  title: `Saved: ${latest}`, body: `${n} of ${c.needed} picked, ${c.needed - n} to go.${lock}`,
  complete: false,
};
}