/**
 * When picks lock, on the tour's own clock.
 *
 * Picks for an event (and each Round Game round) lock at midnight at the
 * START of that day, in the tour's timezone: US Eastern for the PGA,
 * UK time for the DP World Tour. `new Date("YYYY-MM-DDT00:00:00")` is
 * midnight in whatever timezone the SERVER runs — UTC on Vercel — which
 * locked PGA rounds at 8pm ET the evening before. Everything that asks
 * "is it locked?" or "when does it lock?" goes through here.
 */

export const TOUR_TZ: Record<string, string> = {
  pga: "America/New_York",
  euro: "Europe/London",
};
export const TOUR_TZ_LABEL: Record<string, string> = { pga: "ET", euro: "UK time" };

/** Offset of `tz` from UTC at `at`, in ms (e.g. ET in October: -4h). */
function tzOffsetMs(at: Date, tz: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(at);
  const n = (t: string) => Number(parts.find(p => p.type === t)?.value);
  const asUtc = Date.UTC(n("year"), n("month") - 1, n("day"), n("hour"), n("minute"), n("second"));
  return asUtc - at.getTime();
}

/** Midnight at the start of `date` (YYYY-MM-DD, plus `addDays`) in the
 *  tour's timezone, as an absolute instant. Two passes so a DST change
 *  between the guess and the answer can't leave it an hour off. */
export function lockAt(date: string, tour: string, addDays = 0): Date {
  const tz = TOUR_TZ[tour] ?? TOUR_TZ.pga;
  const [y, m, d] = date.slice(0, 10).split("-").map(Number);
  const wallMidnight = Date.UTC(y, m - 1, d + addDays);
  let t = wallMidnight - tzOffsetMs(new Date(wallMidnight), tz);
  t = wallMidnight - tzOffsetMs(new Date(t), tz);
  return new Date(t);
}

/** Round Game: round r (1–4) locks at midnight before its own day. */
export function roundLockAt(startDate: string, tour: string, round: number): Date {
  return lockAt(startDate, tour, round - 1);
}
