/**
 * courseScoring.ts — has anyone played this course this week yet?
 * Before round 1 the PGA TOUR feed sends every hole as scoring avg = par,
 * 0 birdies, 0 bogeys. That's "no rounds yet", not an even-par course, and
 * Course Guide shows those holes as not played (never 0% or "neutral").
 * Pure, no "@/" imports: `npm test` runs it.
 */
export type HoleScoring = { hole_par: number; scoring_avg: number | null; birdies: number | null; bogeys: number | null };

export function scoringPlayed(holes: readonly HoleScoring[]): boolean {
  return holes.some(h => (h.birdies ?? 0) > 0 || (h.bogeys ?? 0) > 0
    || (h.scoring_avg != null && Math.abs(h.scoring_avg - h.hole_par) > 1e-9));
}
