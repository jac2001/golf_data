/**
 * weekChecklist.ts — "Also this week": the games you haven't picked yet.
 * ======================================================================
 * Rick's first week (Bermuda, Oct 21): he made his Let It Ride picks and
 * never saw the Round, Fade or College games, which locked the same
 * midnight. Nothing on the page said they existed or when they locked.
 * This decides which games to put in front of a member, most urgent first.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

import type { GameId } from "./landing.ts";

/** One game's state for the member, built by the page (the plumbing). */
export type GameStatus = {
  /** The page's own id for this row (game + event); passed through as is. */
  key: string;
  game: GameId;
  /** What the row says: "Let It Ride", "Round Game · Round 2", ... */
  label: string;
  /** When this game's picks lock. null = we don't know. */
  locksAt: Date | null;
  /** Picks the member has in. */
  have: number;
  /** Picks a full entry needs. 0 = this game isn't on for this group/event. */
  needed: number;
};

/** One row of the checklist. */
export type ChecklistItem = {
  key: string;
  game: GameId;
  label: string;
  locksAt: Date;
  /** How many picks are still missing (needed - have). */
  left: number;
  /** Locks within the next 24 hours: the row is highlighted. */
  soon: boolean;
};

export const SOON_MS = 24 * 60 * 60 * 1000;

// ── TODO(Jack): weekChecklist ────────────────────────────────────────────────
//
// weekChecklist(statuses, now) -> the rows to show, in order.
//
// Keep a status only when ALL of these hold:
//   - the game is on            (needed > 0)
//   - the entry isn't full yet  (have < needed)
//   - its lock is KNOWN         (locksAt is not null)
//   - it hasn't locked          (locksAt is after now)
// An unknown lock is treated as locked: never invite a pick we can't
// promise will count (CLAUDE.md rule 4, "fail closed").
//
// Order: soonest lock first. Two games locking at the same moment keep
// the order they came in (Array.prototype.sort is stable, so compare only
// the times).
//
// Each row: key, game, label and locksAt as given; left = needed - have; soon = locks within SOON_MS of now
// (exactly 24h away counts as soon).
//
// Hint: filter, then sort, then map. Compare Dates with getTime().

export function weekChecklist(statuses: readonly GameStatus[], now: Date): ChecklistItem[] {
  void statuses; void now;
  throw new Error("TODO(Jack): weekChecklist");
}
