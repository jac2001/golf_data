/**
 * fitVerdict.ts — does this course suit him? One plain answer per golfer.
 * ========================================================================
 * Course Fit used to show four numbers in four units (record here, DG fit
 * adjustment, our win-chance "boost", win chance). This turns DataGolf's
 * two course adjustments into one verdict a member can read at a glance.
 *
 * Inputs, both DataGolf, both strokes per round vs his own baseline:
 *   fit:     how well the course's demands match his skills (dg_fit_adj)
 *   history: what his past results here add or take away (dg_hist_adj)
 * Bermuda (Oct 21) range: fit -0.14 to +0.37, history -0.06 to +0.22.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type Verdict = "suits" | "neutral" | "hurts";
export type FitVerdict = { verdict: Verdict; edge: number };

/** Strokes per round the course has to be worth, either way, to say so. */
export const VERDICT_THRESHOLD = 0.10;

// ── fitVerdict (Jack, Oct 21) ────────────────────────────────────────────────────
//
// edge = fit + history (strokes per round).
//
// Facts the tests pin:
//   - edge >= +0.10 -> "suits";  edge <= -0.10 -> "hurts";  otherwise "neutral".
//     (Exactly on the line counts, like odds_move: mind floating point.)
//   - history missing (null/undefined/NaN) counts as 0: most golfers have
//     some fit number even with no record here.
//   - fit missing (null/undefined/NaN) -> null: no verdict without the
//     course-fit number itself, whatever the history says.
//   - Return the edge too, rounded to 2 decimals (the view prints it).
//
// Why fit + history, not our win-chance boost: both are in the same unit
// (strokes per round), so they add; the boost is a change in a
// probability, which isn't.

export function fitVerdict(
  fit: number | null | undefined,
  history: number | null | undefined,
): FitVerdict | null {
  // isFinite rejects NaN and Infinity: no fit number, no verdict.
  if (fit == null || !Number.isFinite(fit)) {
    return null;
  }
  const historyValue = history != null && Number.isFinite(history) ? history : 0;
  const total = fit + historyValue;
  const tolerance = 1e-9;

  let verdict: Verdict = "neutral";
  if (total >= VERDICT_THRESHOLD - tolerance) {
    verdict = "suits";
  } else if (total <= -VERDICT_THRESHOLD + tolerance) {
    verdict = "hurts";
  }
  const edge = Number(total.toFixed(2));
  return { verdict, edge };
}
