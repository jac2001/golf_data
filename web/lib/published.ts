/**
 * published.ts — the chance we show, the same on every page.
 * The prediction rows carry the base model (win_prob) and the 10,000-run
 * simulation (win_prob_sim). We publish the simulation when it exists
 * (as This Week does); the base stays in the rows because The Model's own
 * decisions read it. Every display goes through here.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

type Chances = { win_prob?: number | null; top10_prob?: number | null;
  win_prob_sim?: number | null; top10_prob_sim?: number | null };

/** The row with win_prob/top10_prob set to the published numbers. */
export function shown<T extends Chances>(row: T): T {
  return { ...row,
    win_prob: row.win_prob_sim ?? row.win_prob ?? null,
    top10_prob: row.top10_prob_sim ?? row.top10_prob ?? null };
}
