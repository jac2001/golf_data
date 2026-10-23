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
  const isNumber = (value: number | null): value is number => value !== null && Number.isFinite(value);
  const categoryLeader = (
  a: number,
  b: number,
  tie: number,
  higherBetter: boolean,
): Verdict["edge"] => {
  if (Math.abs(a - b) <= tie) {
    return "even";
  }

  const aLeads = higherBetter ? a > b : a < b;

  return aLeads ? "a" : "b";
  };
  const comparable = cats.filter(
  (cat): cat is Category & { a: number; b: number } =>
    isNumber(cat.a) && isNumber(cat.b)
  );
  
const comparisons = comparable.map(cat => ({
  ...cat,
  leader: categoryLeader(cat.a, cat.b, cat.tie, cat.higherBetter),
}));

const aLeads = comparisons.filter(cat => cat.leader === "a");
const bLeads = comparisons.filter(cat => cat.leader === "b");

const winKnown = isNumber(win.a) && isNumber(win.b);

if (!winKnown && comparisons.length === 0) {
  return null;
}
let edge: Verdict["edge"];

if (isNumber(win.a) && isNumber(win.b)) {
  edge = categoryLeader(win.a, win.b, win.tie, true);
} else if (aLeads.length > bLeads.length) {
  edge = "a";
} else if (bLeads.length > aLeads.length) {
  edge = "b";
} else {
  edge = "even";
}
  const pct = (value: number): string =>
  `${(Math.round(value * 1000) / 10).toFixed(1)}%`;

let headline: string;

if (isNumber(win.a) && isNumber(win.b)) {
  if (edge === "even") {
    headline = `Too close to call: ${pct(win.a)} vs ${pct(win.b)} to win.`;
  } else {
    const leaderName = edge === "a" ? nameA : nameB;
    const leaderChance = edge === "a" ? win.a : win.b;
    const otherChance = edge === "a" ? win.b : win.a;

    headline = `${leaderName} has the edge: ${pct(leaderChance)} vs ${pct(otherChance)} to win.`;
  }
} else if (edge === "even") {
  const count = aLeads.length;
  const categoryWord = count === 1 ? "category" : "categories";

  headline = `Even: ${count} ${categoryWord} each.`;
} else {
  const leaderName = edge === "a" ? nameA : nameB;
  const count = edge === "a" ? aLeads.length : bLeads.length;
  const categoryWord =
    comparisons.length === 1 ? "category" : "categories";

  headline = `${leaderName} leads ${count} of ${comparisons.length} ${categoryWord}.`;
}
  const reasonFor = (
  cat: (typeof comparisons)[number],
  side: "a" | "b",
): string => {
  const name = side === "a" ? nameA : nameB;
  const value = side === "a" ? cat.a : cat.b;
  const otherValue = side === "a" ? cat.b : cat.a;

  return `${name}: ${cat.say} (${cat.fmt(value)} vs ${cat.fmt(otherValue)})`;
};

let reasons: string[];

if (edge === "even") {
  reasons = [
    ...aLeads.slice(0, 1).map(cat => reasonFor(cat, "a")),
    ...bLeads.slice(0, 1).map(cat => reasonFor(cat, "b")),
  ];
} else {
  const leaderLeads = edge === "a" ? aLeads : bLeads;
  const otherLeads = edge === "a" ? bLeads : aLeads;
  const otherSide = edge === "a" ? "b" : "a";
  const leaderName = edge === "a" ? nameA : nameB;

  reasons = [
    ...leaderLeads.slice(0, 2).map(cat => reasonFor(cat, edge)),
    ...otherLeads.slice(0, 1).map(cat => reasonFor(cat, otherSide)),
  ];

  if (
    comparisons.length >= 2 &&
    leaderLeads.length === comparisons.length
  ) {
    reasons.push(`${leaderName} leads every category we compare.`);
  }
}

return { edge, headline, reasons };
  

}
