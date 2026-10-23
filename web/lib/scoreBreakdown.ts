/** Presentation only: the API remains responsible for scoring and ranking. */
export type ScoreInput = {
  game: "ride" | "college";
  status: "awaiting" | "open" | "live" | "settling" | "final";
  estimated?: boolean;
  lineup: {
    total: number | null;
    incomplete?: boolean;
    // College callers pass counting alumni ONLY, never the bench.
    golfers: readonly {
      name: string; position: string; earnings: number | null; unresolved?: boolean;
    }[];
  } | null;
};
export type ScoreBreakdown = {
  title: string;
  note: string;
  rule: string;
  total: number | null;
  rows: { name: string; position: string; amount: number | null }[];
};

export const SCORE_COPY = {
  live: "Estimated payouts if the tournament ended now.",
  settling: "Final positions — prize money is still settling.",
  final: "Final official prize money.",
  estimatedFinal: "Final positions — earnings estimated from the payout table.",
  ride: "Add your golfers’ tournament earnings. Highest total wins.",
  college: "Only your school’s two best-paid alumni count. Highest total wins.",
} as const;

/**
 * TODO(Jack): buildScoreBreakdown — your TypeScript exercise.
 *
 * 1. Return null before lock (open/awaiting), for no lineup, or no golfers.
 * 2. Use .map() to make rows, keeping names, order and positions.
 *    amount is null (UI says Pending) for unresolved, missing position
 *    (blank, —, -, ?), or earnings that are null, negative or non-finite.
 *    A real 0 with a known position is valid! Never infer a missed cut
 *    just because earnings are zero. Preserve CUT/WD position labels.
 * 3. Keep the API total; do NOT re-score, round or sum the lineup here.
 *    But return total: null if incomplete, any row is pending, or the
 *    supplied total is null, negative or non-finite.
 * 4. Pick note from SCORE_COPY using status and estimated. Final estimates
 *    must never say official. Settling is its own state, not live.
 * 5. title: ride = "Your lineup score", college = "Your school score".
 *    rule: SCORE_COPY[input.game]. Return { title, note, rule, total, rows }.
 *
 * Hints: guard clauses first; Number.isFinite(value); .map() transforms;
 * .some() asks whether at least one row is pending. Don't mutate input.
 *
 * Tests are intentionally red until you finish. Add a test of your own
 * for a College lineup with only one counting alumnus (still valid).
 * The null stub keeps the existing live page unchanged while you learn.
 */
export function buildScoreBreakdown(input: ScoreInput): ScoreBreakdown | null {
  if (input.status === 'open' || input.status === 'awaiting') {
    return null;
  }
  const lineup = input.lineup;

  if (!lineup || lineup.golfers.length === 0) {
    return null;
  }
  const rows = lineup.golfers.map(golfer => {
    const position = golfer.position.trim();
    const missingPosition =
      position === "" ||
      position === "\u2014" || // Em dash (—), distinct from a hyphen (-).
      position === "-" ||
      position === "?";
    const earnings = golfer.earnings;
    const validAmount =
      !golfer.unresolved &&
      !missingPosition &&
      earnings !== null &&
      Number.isFinite(earnings) &&
      earnings >= 0;
    return {
      name: golfer.name,
      position: golfer.position,
      amount: validAmount ? earnings : null,
    };
  });

  const hasPending = rows.some(row => row.amount === null);
  const suppliedTotal = lineup.total;
  const total =
    !lineup.incomplete && !hasPending &&
      suppliedTotal !== null &&
      Number.isFinite(suppliedTotal) && suppliedTotal >= 0 ? suppliedTotal : null;
  
  let note: string;

if (input.status === "live") {
  note = SCORE_COPY.live;
} else if (input.status === "settling") {
  note = SCORE_COPY.settling;
} else {
  note = input.estimated
    ? SCORE_COPY.estimatedFinal
    : SCORE_COPY.final;
}
  return {
    title: input.game === 'ride'
      ? "Your lineup score"
      : "Your school score",
    note,
    rule: SCORE_COPY[input.game],
    total,
    rows
  };
}
