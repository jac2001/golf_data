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

// ── thingsToWatch ─────────────────────────────────────────────────
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
  const watches: Watch[] = [];
  const history = input.history;

  if (history) {
    const editions = history.years
      .map((year, index) => ({
        year,
        score: history.winning_to_par[index],
      }))
      .filter(({ year, score }) =>
        Number.isFinite(year) && Number.isFinite(score)
      );

    if (editions.length >= 2) {
      const total = editions.reduce(
        (sum, edition) => sum + edition.score,
        0
      );
      const mean = total / editions.length;

      const magnitude = Math.round(Math.abs(mean));
      const direction = mean > 0 ? "over" : "under";

      const years = editions.map(edition => edition.year);
      const firstYear = Math.min(...years);
      const lastYear = Math.max(...years);

      watches.push({
        text: magnitude === 0
          ? "Winners have finished around even par here."
          : `Winners have finished an average of ${magnitude} ${direction} par here.`,
        source: `Past winners, ${firstYear}–${lastYear}`,
      });
    }
  }
  const profile = input.profile;

  if (profile) {
    const skills = ["ott", "app", "arg", "putt"] as const;

    const validProfile = skills.every(skill =>
      Number.isFinite(profile[skill]) &&
      profile[skill] >= 0 &&
      profile[skill] <= 1
    );

    if (validProfile && skills.some(skill => profile[skill] > 0)) {
      const highestShare = Math.max(...skills.map(skill => profile[skill]));
      const leaders = skills
        .filter(skill => profile[skill] === highestShare)
        .map(skill => SKILL_NAMES[skill])
        .sort();
      const percentage = Math.round(highestShare * 100);

      // A tie names every leader: "Approach play and driving matter most".
      const names = new Intl.ListFormat("en", { style: "long", type: "conjunction" })
        .format(leaders.map(name => name.toLowerCase()));
      const sentenceNames = names.charAt(0).toUpperCase() + names.slice(1);

      watches.push({
        text: leaders.length === 1
          ? `${leaders[0]} separates the field more than anything else here (${percentage}% of what matters).`
          : `${sentenceNames} matter most here (${percentage}% each).`,
        source: "DataGolf course profile",
      });
    }
  }

  const windyDays = (input.forecast ?? []).filter(
    (day): day is { day: string; wind_mph: number } =>
      day.wind_mph != null &&
      Number.isFinite(day.wind_mph) &&
      day.wind_mph >= 0
  );

  if (windyDays.length > 0) {
    const strongest = windyDays.reduce((best, day) =>
      day.wind_mph > best.wind_mph ? day : best
    );

    const wind = Math.round(strongest.wind_mph);

    watches.push({
      text: wind >= 15
        ? `Wind up to ${wind} mph on ${strongest.day} could push scores up.`
        : `Light winds forecast (up to ${wind} mph), good for scoring.`,
      source: "This week's forecast",
    });
  }
  const par5Count = input.holes.filter(
    hole => hole.hole_par === 5
  ).length;

  if (par5Count > 0) {
    watches.push({
      text: par5Count === 1
        ? "1 par 5 is the best birdie chance."
        : `${par5Count} par 5s are the best birdie chances.`,
      source: "Scorecard",
    });
  }

  return watches.slice(0, 3);
}
