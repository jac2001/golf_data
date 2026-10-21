/**
 * holeVerdict.ts — how is a hole playing? A word for each tile.
 * ===============================================================
 * Course Guide's 18-hole strip colors a tile only when real scoring exists
 * this week, and always with a word, so color is never the only signal.
 * This decides the word (and the view picks the color from it).
 *
 * Input: the hole's scoring average minus its par this week (scoring_diff),
 * e.g. +0.31 = plays 0.31 shots over par. null = not played yet.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type HoleLabel = "chance" | "par" | "tough";

/** Shots relative to par a hole must play, either way, to stand out. */
export const HOLE_THRESHOLD = 0.15;

// ── TODO(Jack): holeVerdict ───────────────────────────────────────────────────
//
// Facts the tests pin:
//   - diff <= -0.15 -> "chance"   (plays easier than par: a birdie chance)
//   - diff >= +0.15 -> "tough"
//   - otherwise     -> "par"      (plays around par)
//   - exactly on the line counts (mind floating point, as before)
//   - null, undefined, NaN, Infinity -> null: not played, no label at all
//
// Then holeSentence: the plain-words line the tap panel shows.
//   - null-ish diff                -> "Not played yet this week."
//   - |diff| rounds to 0.00        -> "Playing right at par."
//   - diff > 0                     -> "Playing 0.31 shots over par."   (2 decimals)
//   - diff < 0                     -> "Playing 0.42 shots under par."
//   - exactly 1.00 either way      -> "shot", not "shots": "Playing 1.00 shot over par."

export function holeVerdict(diff: number | null | undefined): HoleLabel | null {
  void diff; void HOLE_THRESHOLD;
  throw new Error("TODO(Jack): holeVerdict");
}

export function holeSentence(diff: number | null | undefined): string {
  void diff;
  throw new Error("TODO(Jack): holeSentence");
}
