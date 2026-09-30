/**
 * Let It Ride pick rules (docs/PHASE2_DESIGN.md).
 *
 * The pick route gathers the facts, then asks validateLeaguePick()
 * whether the pick is allowed and — if not — what to tell the user.
 * The route's INSERT re-checks the two budget counts atomically, so
 * this function owns the *messages*; the database owns the guarantee.
 */

export type PickContext = {
  locked: boolean;           // this slate's event has started (tour-local clock)
  inSeason: boolean;         // event starts inside the league's season window
  tourInLeague: boolean;     // the event's tour is one the league plays
  alreadyPicked: boolean;    // this golfer is already in my picks for this slate
  usesOfThisGolfer: number;  // my picks of this golfer so far, ALL tours
  picksThisSlate: number;    // my picks in this tournament so far
  usesPerPlayer: number;     // league config (default 3)
  playersPerWeek: number;    // league config (default 3) — per slate
  golferName: string;        // for the message
};

export type PickVerdict =
  | { ok: true }
  | { ok: false; status: number; error: string };

/**
 * TODO(Jack): decide whether this pick is allowed.
 *
 * Return { ok: true } to allow it, or
 * { ok: false, status, error } with the HTTP status and a message the
 * pick screen shows verbatim. Suggested statuses:
 *   409 — conflict with game state (locked, duplicate)
 *   422 — breaks a budget rule (out of uses, slate full)
 *   400 — not a valid target (out of season, tour not in league)
 *
 * Things to think about:
 *   - Order matters: when several rules fail at once, which reason is
 *     the most useful one to show? ("Picks are locked" beats "you're out
 *     of uses" — the user can't fix the second one anyway.)
 *   - usesOfThisGolfer counts picks ALREADY made, so the check is about
 *     whether one MORE is allowed.
 *   - A good message names the golfer and the number:
 *     "You've used Scottie Scheffler 3 of 3 times this season."
 */
export function validateLeaguePick(ctx: PickContext): PickVerdict {
  throw new Error("TODO(Jack): validateLeaguePick not written yet");
}
