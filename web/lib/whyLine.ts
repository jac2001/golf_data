/**
 * whyLine.ts — one plain-English reason under each golfer on a pick card.
 * =======================================================================
 * docs/MOBILE_FIRST_DESIGN.md decision D, and the launch plan's "Help me
 * pick": explain each golfer in ONE sentence a non-golf friend
 * understands, and never make it sound like a promise.
 *
 *   Scottie Scheffler      Top-10 in 4 of his last 5 starts
 *   Brian Harman           Made the cut here 5 of 5 times
 *   Taylor Moore           Long shot: about a 1 in 60 chance to win
 *
 * Pure function, no imports from "@/": `npm test` runs it. The facts come
 * in already cleaned (Claude's plumbing): no filler values, nulls where a
 * fact is unknown.
 */

/** One past start: a finishing position, or "MC" (missed cut / withdrew). */
export type Finish = number | "MC";
export type GolferFacts = {
  /** His last starts, MOST RECENT FIRST, at most 5. May be shorter (new
   *  player, injury) or empty. Only real results: no filled values. */
  recent: Finish[];
  /** Times he has played this course before, and cuts made there. */
  courseStarts: number;
  courseCuts: number;
  /** Our model's chances this week (0–1), or null if no model this week. */
  winProb: number | null;
  top10Prob: number | null;
  /** Official world ranking, or null. */
  worldRank: number | null;
};

/** Longest line a phone card shows on one line. */
export const MAX_WHY_LENGTH = 48;

// Jack's thresholds (decision b).
export const MIN_RECENT_STARTS = 3;  // recent-form lines need at least this many known starts
export const MIN_COURSE_STARTS = 3;  // a course line needs at least this many starts there
export const HOT_SHARE = 0.6;        // hot = top-10 in at least 60% of known starts
export const COLD_MISSES = 3;        // cold = at least this many missed cuts in known starts
export const FAVORITE_WIN = 0.10;    // model favorite = 10%+ to win
export const LONG_SHOT_WIN = 0.02;   // long shot = under 2% (worse than 1 in 50)

// ── helpers (Claude's) ───────────────────────────────────────────────────────

/** How many of `recent` are top-N finishes (MC never counts). */
export function countTopN(recent: Finish[], n: number): number {
  return recent.filter(f => f !== "MC" && f <= n).length;
}

/** "1 in 60" for 0.0167. Rounded to a friendly number; null for 0/unknown. */
export function oneIn(p: number | null): string | null {
  if (p === null || !(p > 0)) return null;
  const n = 1 / p;
  const nice = n < 10 ? Math.round(n) : n < 100 ? Math.round(n / 5) * 5 : Math.round(n / 25) * 25;
  return `1 in ${Math.max(2, nice)}`;
}

// ── TODO(Jack): whyLine ───────────────────────────────────────────────────────
//
// Return the single most useful TRUE sentence about this golfer, or "" when
// there's nothing honest to say (the card then shows no line).
//
// Facts the tests pin:
//   - Only claim what the facts show. "4 of his last 5" needs 5 recent
//     starts; with 3 starts, say "of his last 3". Course lines need
//     courseStarts > 0.
//   - Never a promise: no "will", "lock", "guaranteed", "can't miss".
//     Chances are chances ("about a 1 in 60 chance").
//   - Short: at most MAX_WHY_LENGTH characters, one line, no trailing period.
//   - No money words (lineup earnings are scored elsewhere; this is about
//     the golfer).
//   - Same facts, same line (no randomness).
//
// Decisions that are yours (reason in a comment):
//   a. ORDER: which fact wins when several are true? Hot recent form,
//      a strong course record, a top model chance, a long shot, a cold
//      streak. Write them as an if-chain, most interesting first.
//   b. THRESHOLDS: what counts as "hot"? (e.g. top-10 in 3+ of last 5).
//      What counts as a "long shot"? Put each in a named constant.
//   c. Bad news: say it ("Missed 3 of his last 5 cuts") or stay quiet?
//      A beginner deciding between two golfers benefits from a warning.
//
// Done when: npm test (from web/) passes lib/whyLine.test.ts, plus one test
// of your own for decision (a): a golfer where two facts are true, and the
// exact line you chose.

export function whyLine(g: GolferFacts): string {
  // a: order = a win, hot form, a perfect course record, a cold streak,
  //    the model's favorite, a long shot. The person's own results first;
  //    the model's numbers only when there's nothing better to say.
  // b: thresholds are the named constants above.
  // c: say bad news (missed cuts), and say it BEFORE the model lines: a
  //    beginner choosing between two golfers needs the warning more.
  const n = g.recent.length;
  const t10 = countTopN(g.recent, 10);
  const missed = g.recent.filter(f => f === "MC").length;

  if (g.recent[0] === 1) return "Won his last start";
  if (n >= MIN_RECENT_STARTS && t10 >= Math.ceil(n * HOT_SHARE)) return `Top-10 in ${t10} of his last ${n} starts`;
  if (g.courseStarts >= MIN_COURSE_STARTS && g.courseCuts === g.courseStarts) return `Made the cut here ${g.courseCuts} of ${g.courseStarts} times`;
  if (n >= MIN_RECENT_STARTS && missed >= COLD_MISSES) return `Missed ${missed} of his last ${n} cuts`;
  if (g.winProb !== null && g.winProb >= FAVORITE_WIN) return `Model favorite: about a ${oneIn(g.winProb)} chance`;
  if (g.winProb !== null && g.winProb < LONG_SHOT_WIN) return `Long shot: about a ${oneIn(g.winProb)} chance to win`;
  return "";
}
