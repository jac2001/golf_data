/**
 * bestEvents.ts — a golfer's best events left, instead of Spend / Save.
 * =====================================================================
 * Spend/save is a yes/no built on estimates for events months away, so it
 * flips on small gaps and sounds certain when it isn't (Jack, Oct 23). This
 * ranks this week against his upcoming events and lets the member decide:
 * "Conners: Bermuda $127K · Cognizant $132K · WM Phoenix $122K".
 * Same values as before (Render's /api/advice/values, contested windows
 * only); only the presentation changes.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

import type { FutureWindow } from "./advice.ts";
import { k } from "./pickReason.ts";

export type EventValue = { tid: string; name: string; ev: number; thisWeek: boolean };

export type BestEvents = {
  /** This week + his best future events, best first (see the TODO for which). */
  events: EventValue[];
  /** This week's place among ALL his events (1 = best). */
  rank: number;
  /** "spent": no uses left. "best": this week is #1. "top": inside his best
   *  `usesLeft` events. "later": a use is worth more at a later event. */
  fit: "spent" | "best" | "top" | "later";
  /** The short tag on his row. */
  tag: string;
};

// ── TODO(Jack): bestEvents ───────────────────────────────────────────────────
//
// bestEvents(thisWeek, nowEv, future, usesLeft, show = 3)
//
// 1. One list: this week ({ ...thisWeek, ev: nowEv, thisWeek: true }) plus
//    every future window ({ tid, name, ev, thisWeek: false }). Best first.
//    Ties: this week ahead of a future event; two future events keep the
//    order they came in (stable sort).
// 2. rank = this week's place in that list (1 = best). Same rule as your
//    modelPickReason: 1 + the number of future events worth MORE.
// 3. events = the first `show` of the list, and if this week isn't among
//    them, this week added at the end (members always see this week).
// 4. fit and tag:
//      usesLeft <= 0       -> "spent",  "No uses left"
//      rank 1              -> "best",   "Best week for him"
//      rank <= usesLeft    -> "top",    "One of his 3 best"        (3 = usesLeft)
//      otherwise           -> "later",  "Better at The American Express ($117K)"
//                             (the FUTURE event at position usesLeft, best
//                             first: the use this week gives up, as in your
//                             modelPickReason; money with k())
//    "spent" is checked first: with no uses left, nothing else matters.
//
// Don't change `future` (copy before sorting).

export function bestEvents(
  thisWeek: { tid: string; name: string },
  nowEv: number,
  future: readonly FutureWindow[],
  usesLeft: number,
  show = 3,
): BestEvents {
  const current: EventValue = {
    ...thisWeek,
    ev: nowEv,
    thisWeek: true,
  };
  const all: EventValue[] = [
    current,
    ...future.map(event => ({
      tid: event.tid,
      name: event.name,
      ev: event.ev,
      thisWeek: false,
    })),
  ];
  all.sort((a, b) => b.ev - a.ev);
  const rank = all.findIndex(event => event.thisWeek) + 1;
  const events = all.slice(0, show);
  if (!events.some(event => event.thisWeek)) {
    events.push(current);
  }

  let fit: BestEvents['fit'];
  let tag: string;

  if (usesLeft <= 0) {
    fit = 'spent';
    tag = "No uses left";
  } else if (rank === 1) {
    fit = "best";
    tag = "Best week for him";
  } else if (rank <= usesLeft) {
    fit = "top";
    tag = `One of his ${usesLeft} best`;
  } else {
    const futureRanked = all.filter(event => !event.thisWeek);
    const displaced = futureRanked[usesLeft - 1];

    fit = "later";
    tag = `Better at ${displaced.name} (${k(displaced.ev)})`;
  }
  return { events, rank, fit, tag };
  

}
