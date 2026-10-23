/**
 * matchupVerdict.ts — Head-to-Head's answer before its numbers.
 * ==============================================================
 * Conners vs Blanchet (Oct 23) showed 25 rows across six sections, with
 * strokes gained from three sources, and never said who has the edge.
 * This turns the comparison into one headline and a few plain reasons;
 * the full table stays below for anyone who wants it.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

/** One row both golfers are compared on, in priority order (most important first). */
export type Category = {
  /** What leading it means, for a reason line: "better approach play". */
  say: string;
  a: number | null;
  b: number | null;
  higherBetter: boolean;
  /** Differences smaller than this are a tie (e.g. 0.05 strokes, 0.002 win chance). */
  tie: number;
  /** How a value prints in a reason: v => (v >= 0 ? "+" : "") + v.toFixed(2). */
  fmt: (v: number) => string;
};

export type Verdict = {
  /** "a", "b", or "even". */
  edge: "a" | "b" | "even";
  headline: string;
  /** Up to 3 reasons: the leader's first two leads, then the other golfer's first lead. */
  reasons: string[];
};

// ── TODO(Jack): matchupVerdict ───────────────────────────────────────────────
//
// matchupVerdict(nameA, nameB, win, cats) -> Verdict, or null.
//   win:  each golfer's published win chance (0..1) or null, with its own tie.
//   cats: the other categories, in priority order.
//
// 1. Who leads a category: only when BOTH values are numbers (Number.isFinite)
//    and they differ by MORE than `tie`. Higher wins when higherBetter, lower
//    otherwise. Anything else: nobody leads it.
//
// 2. The edge:
//      both win chances known -> whoever leads on win chance (same tie rule),
//                                "even" if it's a tie.
//      otherwise              -> whoever leads more categories, "even" if equal.
//    No win chance AND no category with both values -> return null (nothing to say).
//
// 3. headline (pct = Math.round(v * 1000) / 10, then "%": 0.0336 -> "3.4%"):
//      win known, someone leads -> "Conners has the edge: 3.4% vs 0.4% to win."
//                                  (leader's chance first)
//      win known, even          -> "Too close to call: 2.1% vs 2.0% to win."
//                                  (A's chance first)
//      no win, someone leads    -> "Conners leads 4 of 6 categories."
//                                  (6 = categories where both have values)
//      no win, even             -> "Even: 3 categories each."
//    "category" when the number is 1: "Even: 1 category each.",
//    "Kim leads 1 of 1 category."
//
// 4. reasons: the edge golfer's first two category leads, then the other
//    golfer's first lead, each as "<Name>: <say> (<fmt(his)> vs <fmt(other's)>)":
//      "Conners: better approach play (+0.54 vs -0.10)"
//    When edge is "even": A's first lead, then B's first lead.
//    If the leader leads EVERY category with both values (and there are at
//    least 2), add one more: "Conners leads every category we compare."

export function matchupVerdict(
  nameA: string,
  nameB: string,
  win: { a: number | null; b: number | null; tie: number },
  cats: readonly Category[],
): Verdict | null {
  void nameA; void nameB; void win; void cats;
  throw new Error("TODO(Jack): matchupVerdict");
}
