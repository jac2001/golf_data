/**
 * profileSections.ts — what a player profile shows, and in what order.
 * =====================================================================
 * A golfer who isn't in this week's field got an "Our Model" card full of
 * dashes and "WIN RANK —" (Players audit #12). This decides, from what the
 * profile actually holds, whether he's playing this week and which
 * sections to render. The view renders exactly the list it gets back.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type Section =
  | "thisWeek"        // our model's chances for this event
  | "dgPrediction"    // DataGolf's chances for this event
  | "courseFit"       // DataGolf's course decomposition for this event
  | "skills"          // DataGolf skill ratings (season-level)
  | "approach"        // DataGolf approach skill by distance (season-level)
  | "season"          // PGA TOUR season profile
  | "career";         // results by year / recent events (always fetched separately)

export type ProfileInput = {
  our_model: { win_prob?: number | null; top10_prob?: number | null } | null;
  dg_prediction: object | null;
  decompositions: object | null;
  skill_ratings: object | null;
  approach_skill: object | null;
  betting_profile: object | null;
};

export type ProfilePlan = { inField: boolean; note: string | null; show: Section[] };

/** Display order, this-week sections first. */
export const ORDER: readonly Section[] = ["thisWeek", "dgPrediction", "courseFit", "skills", "approach", "season", "career"];

// ── TODO(Jack): profileSections ───────────────────────────────────────────────
//
// eventName: this week's event ("Butterfield Bermuda Championship").
//
// Facts the tests pin:
//   - In the field = our model has a win chance (a real finite number), OR
//     DataGolf has a prediction for him. Either is enough.
//   - In the field: note null; show every section whose data exists, in
//     ORDER. "thisWeek" needs our win chance; "career" always shows.
//   - Not in the field: note "Not in the <eventName> field this week."
//     (no event name -> "Not in this week's field."); show only the
//     season-level sections that exist (skills, approach, season) plus
//     career, in ORDER. Never this-week sections, even if some stray
//     this-week data exists (a decomposition with no prediction is stale).
//   - A section with no data never appears, so the view never renders an
//     empty card.

export function profileSections(p: ProfileInput, eventName?: string | null): ProfilePlan {
  void p; void eventName; void ORDER;
  throw new Error("TODO(Jack): profileSections");
}
