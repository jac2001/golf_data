/**
 * thingsToWatch.ts — three things to watch at this week's course.
 * =================================================================
 * Course Guide's second section. Every line must come from data we really
 * have, say where it came from, and never be invented: no history means
 * no history line, not a guess. Missing data is skipped, never shown as 0.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type Watch = { text: string; source: string };

export type WatchInput = {
  /** DataGolf course demand profile: share of what separates players here (sums to ~1). */
  profile?: { ott: number; app: number; arg: number; putt: number } | null;
  /** The scorecard: each hole's par. */
  holes: { hole_num: number; hole_par: number }[];
  /** This week's forecast, one entry per round day. */
  forecast?: { day: string; wind_mph: number | null }[] | null;
  /** Past editions here: the winning score to par each year (e.g. -15). */
  history?: { years: number[]; winning_to_par: number[] } | null;
};

export const SKILL_NAMES = { ott: "Driving", app: "Approach play", arg: "The short game", putt: "Putting" } as const;

// ── TODO(Jack): thingsToWatch ─────────────────────────────────────────────────
//
// Build up to THREE lines, in this priority order, skipping any whose data
// is missing:
//
//  1. History (needs at least 2 editions with a winning score):
//     text   "Winners have finished an average of N under par here."
//            N = the mean winning score's magnitude, rounded to a whole number.
//            If the mean is over par, "N over par" instead.
//     source "Past winners, <first year>–<last year>"   e.g. "Past winners, 2021–2025"
//
//  2. Profile (needs a profile):
//     text   "<Skill> separates the field more than anything else here (<P>% of what matters)."
//            Skill = SKILL_NAMES of the biggest share; P = share * 100, rounded.
//     source "DataGolf course profile"
//
//  3. Wind (needs at least one day with a wind number):
//     strongest day >= 15 mph:  "Wind up to <W> mph on <Day> could push scores up."
//     otherwise:                "Light winds forecast (up to <W> mph), good for scoring."
//     W = the highest wind_mph, rounded. Day = that day's label.
//     source "This week's forecast"
//
//  4. Par 5s (needs at least one par-5 hole):
//     text   "<N> par 5s are the best birdie chances."   (N = how many)
//            one par 5: "1 par 5 is the best birdie chance."
//     source "Scorecard"
//
// Return at most 3, in that order. Nothing usable -> [].

export function thingsToWatch(input: WatchInput): Watch[] {
  void input;
  throw new Error("TODO(Jack): thingsToWatch");
}
