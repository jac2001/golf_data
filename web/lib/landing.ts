/**
 * landing.ts — where the Friends Game opens: which game, which event.
 * ===================================================================
 * docs/MOBILE_FIRST_DESIGN.md decision C: a member lands on the game
 * their group actually plays, not a menu of four. And on the PGA TOUR
 * unless they chose the DP World Tour in Settings ("favorite-tour").
 *
 * Pure functions, no imports from "@/": `npm test` runs them.
 */

// ── games ────────────────────────────────────────────────────────────────────

export type GameId = "ride" | "rounds" | "fades" | "college";
export const GAME_IDS: readonly GameId[] = ["ride", "rounds", "fades", "college"];

/** What landingGame looks at, gathered by the page. */
export type LandingSignals = {
  /** Picks made by the people in this person's groups (including them),
   *  per game, over the last few weeks. A game nobody plays has 0. */
  groupPicks: Record<GameId, number>;
  /** The game this device last chose (the Games buttons), or null. */
  lastChosen: GameId | null;
  /** Games with an event you can pick in right now. A game that's off
   *  this week (no model for Fade, team event, off-week) is false. */
  open: Record<GameId, boolean>;
};

/** Where to land when nothing else says anything. */
export const DEFAULT_GAME: GameId = "ride";

// ── TODO(Jack): landingGame ───────────────────────────────────────────────────
//
// Return the game the Friends page should open on.
//
// Facts:
//   - Never land on a game that isn't open, if any game is open.
//   - If NO game is open (off-week), still return a game: someone may
//     want last week's results. Fall back sensibly.
//   - A brand-new member (lastChosen null) should land on the game their
//     group plays most. That's the whole point of decision C.
//   - With no signal at all, DEFAULT_GAME.
//
// Decisions that are yours (reason in a comment):
//   a. lastChosen vs groupPicks. Someone who tapped Round Game yesterday
//      while their group mostly plays Let It Ride: respect their own
//      choice, or the group's? (Hint: the person's own tap is the
//      strongest signal there is about them.)
//   b. A tie in groupPicks (e.g. ride 6, rounds 6). Which wins? A fixed
//      order (GAME_IDS) is predictable; say which and why.
//   c. Does a game with groupPicks 0 ever beat DEFAULT_GAME?
//
// Done when: npm test (from web/) passes lib/landing.test.ts, plus one test
// of your own for decision (a).

export function landingGame(s: LandingSignals): GameId {
  // decision a: lastChosen should always default to the person's own choice
  // decision b: fixed order, first in GAME_IDS wins
  // decision c: return to the game with the most picks, or DEFAULT_GAME if all are 0
  const openGames = GAME_IDS.filter(g => s.open[g]);
  // decision a: lastChosen should always default to the person's own choice
  if (s.lastChosen && openGames.includes(s.lastChosen)) {
    return s.lastChosen;
  }
  if (openGames.length > 0) {
    const maxPicks = Math.max(...openGames.map(g => s.groupPicks[g]));
    const candidates = openGames.filter(g => s.groupPicks[g] === maxPicks);
    return candidates[0]; // decision b: fixed order, first in GAME_IDS wins
  }
  
  // decision c: if no games are open, return the game with the most groupPicks, or DEFAULT_GAME if all are 0
  const maxPicks = Math.max(...GAME_IDS.map(g => s.groupPicks[g]));
  if (maxPicks > 0) {
    const candidates = GAME_IDS.filter(g => s.groupPicks[g] === maxPicks);
    return candidates[0]; // decision b: fixed order, first in GAME_IDS wins
  }
  return DEFAULT_GAME;
}

// ── events (Claude's: the PGA default) ───────────────────────────────────────

export type Tour = "pga" | "euro";
export type LandingEvent = {
  tournament_id: string; tour: Tour; start_date: string;
  status: "open" | "live" | "awaiting" | "completed" | "upcoming";
};

/** The tour chosen in Settings (localStorage "favorite-tour"), PGA unless
 *  set. Safe on the server and in private mode: both give "pga". */
export function favoriteTour(): Tour {
  try {
    return typeof localStorage !== "undefined" && localStorage.getItem("favorite-tour") === "euro" ? "euro" : "pga";
  } catch { return "pga"; }
}

/** Which event a game opens on: the favorite tour's events if it has any
 *  (PGA unless the person chose otherwise), else whatever exists. Within
 *  them, an open slate first, else a live one, else one waiting for its
 *  field, else the latest final. */
export function landingEvent<E extends LandingEvent>(evs: E[], tour: Tour = "pga"): E | undefined {
  const mine = evs.filter(e => e.tour === tour);
  const pool = mine.length ? mine : evs;
  return pool.find(w => w.status === "open") ?? pool.find(w => w.status === "live")
    ?? pool.find(w => w.status === "awaiting")
    ?? [...pool].filter(w => w.status === "completed").sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
    ?? pool[0];
}
