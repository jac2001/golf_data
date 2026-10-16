/**
 * eventStatus.ts — the one line under an event's name in the Friends Game.
 * ========================================================================
 * Redesign step 2 (the phone mockup's event bar): instead of a schedule
 * strip, each game shows its event as a name plus ONE line that answers
 * "what's going on and what do I do?":
 *
 *   Butterfield Bermuda Championship
 *   Picks open · locks in 3h 12m
 *
 * Pure function, no imports from "@/": `npm test` runs it. The event bar
 * component passes the facts in and draws whatever you return.
 */

import { TOUR_TZ, TOUR_TZ_LABEL } from "./lockTime.ts";

export type EventFacts = {
  /** Same statuses the event navigator uses (fromOpenEvents). */
  status: "open" | "awaiting" | "live" | "completed" | "upcoming";
  tour: "pga" | "euro";
  /** First day of the event, YYYY-MM-DD. */
  startDate: string;
  /** When picks lock (lib/lockTime.ts lockAt), or null if unknown. */
  lockAt: Date | null;
  /** The round being played while live (1–4), or null if unknown. */
  round: number | null;
};

/** state = the short colored word(s); detail = the muted rest. */
export type StatusLine = {
  state: string;
  detail: string;
  /** go = act now (green), live = in progress (green), quiet = nothing to do (muted). */
  tone: "go" | "live" | "quiet";
};

// ── helpers (Claude's): use these so the dates come out the same everywhere ──

/** "3h 12m" / "45m" for a duration in ms (rounded down to the minute). */
export function countdown(ms: number): string {
  const mins = Math.max(0, Math.floor(ms / 60_000));
  const h = Math.floor(mins / 60), m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** "Wed" / "Thu": the weekday of `at` on the tour's clock. */
export function weekdayOnTourClock(at: Date, tour: "pga" | "euro"): string {
  return new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: TOUR_TZ[tour] }).format(at);
}

/** "Oct 22" for a YYYY-MM-DD date (no timezone games: it's a calendar day). */
export function shortDay(ymd: string): string {
  return new Date(`${ymd.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** "ET" / "UK time". */
export const tzLabel = (tour: "pga" | "euro") => TOUR_TZ_LABEL[tour];

export const LOCK_SOON_MS = 24 * 3600_000;

// ── TODO(Jack): eventStatusLine ───────────────────────────────────────────────
//
// Turn the facts into the line. Facts the tests pin:
//   - open      → state "Picks open", tone "go". If the lock is less than
//                 LOCK_SOON_MS away, the detail is a countdown: "locks in
//                 3h 12m" (use countdown()). Otherwise it names the day.
//   - awaiting  → tone "quiet", says the field isn't out yet.
//   - live      → state starts with "Live", tone "live"; mention the round
//                 when you know it ("Round 2").
//   - completed → state "Final", tone "quiet".
//   - upcoming  → tone "quiet", says when it starts (shortDay(startDate)).
//   - Never "projected" or money words here; this line is about timing.
//
// Decisions that are yours (reason in a comment):
//   a. Picks lock at MIDNIGHT at the start of round 1's day, on the tour's
//      clock. "locks Thu 12:00am ET" is technically right and reads wrong
//      (people think Thursday daytime). How do you say it more than a day
//      out? e.g. "locks Wed at midnight ET" — weekdayOnTourClock() of the
//      lock gives "Thu"; the evening before is what a person means.
//   b. open with lockAt null (unknown): what detail, if any? Remember the
//      fail-closed rule: never imply more time than there is.
//   c. live with round null: just "Live"?
//
// Done when: npm test (from web/) passes lib/eventStatus.test.ts, plus one
// test of your own for decision (a).

export function eventStatusLine(e: EventFacts, now: Date): StatusLine {
  // Decision a: For now pick should lock midnight on the day before the first round, on the tour's clock. 
  // work on locking before the first tee shot of the tournament round
  // Decision b: LockAt null → no detail, just "Picks open" (fail-closed).
  // Decision c:  Live with round null → just "Live" (no round number).
  switch (e.status) {
    case "open":
      {
        if (e.lockAt === null) {
          return { state: "Picks open", detail: "", tone: "go" };
        }
        const timeUntilLock = e.lockAt.getTime() - now.getTime();
        if (timeUntilLock < LOCK_SOON_MS) {
          return { state: "Picks open", detail: `locks in ${countdown(timeUntilLock)}`, tone: "go" };
        } else {
          return { state: "Picks open", detail: `locks ${weekdayOnTourClock(new Date(e.lockAt.getTime() - 1), e.tour)} at midnight ${tzLabel(e.tour)}`, tone: "go" };
        }
      }
    case "awaiting":
      return { state: "Awaiting", detail: "field not out yet", tone: "quiet" };
    case "live":
      const roundText = e.round !== null ? `Round ${e.round}` : "";
      return { state: `Live ${roundText}`.trim(), detail: "", tone: "live" };
    case "completed":
      return { state: "Final", detail: "", tone: "quiet" };
    case "upcoming":
      return { state: "Upcoming", detail: `starts ${shortDay(e.startDate)}`, tone: "quiet" };
  }

}
