/**
 * Tests for landing.ts — written before the code.
 * Run from web/:  npm test
 *
 * landingGame: these pin the facts; decisions (a)–(c) are left open.
 * landingEvent: Claude's PGA default, tested here too.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_GAME, GAME_IDS, landingEvent, landingGame } from "./landing.ts";
import type { GameId, LandingEvent, LandingSignals } from "./landing.ts";

const zero = (): Record<GameId, number> => ({ ride: 0, rounds: 0, fades: 0, college: 0 });
const allOpen = (): Record<GameId, boolean> => ({ ride: true, rounds: true, fades: true, college: true });

const sig = (over: Partial<LandingSignals> = {}): LandingSignals => ({
  groupPicks: zero(), lastChosen: null, open: allOpen(), ...over,
});

// ── landingGame ──────────────────────────────────────────────────────────────

test("no signal at all → the default game", () => {
  assert.equal(landingGame(sig()), DEFAULT_GAME);
});

test("a new member lands on what their group plays most", () => {
  assert.equal(landingGame(sig({ groupPicks: { ride: 2, rounds: 9, fades: 1, college: 0 } })), "rounds");
  assert.equal(landingGame(sig({ groupPicks: { ride: 0, rounds: 0, fades: 4, college: 0 } })), "fades");
});

test("never a closed game when something is open", () => {
  const open = { ride: true, rounds: false, fades: true, college: true };
  // the group's favorite is closed this week
  assert.notEqual(landingGame(sig({ groupPicks: { ride: 1, rounds: 9, fades: 0, college: 0 }, open })), "rounds");
  // the device's last choice is closed this week
  assert.notEqual(landingGame(sig({ lastChosen: "rounds", open })), "rounds");
});

test("closed favorite → the next most-played OPEN game", () => {
  const open = { ride: true, rounds: false, fades: true, college: true };
  assert.equal(landingGame(sig({ groupPicks: { ride: 1, rounds: 9, fades: 5, college: 0 }, open })), "fades");
});

test("off-week (nothing open) still returns a real game", () => {
  const none = { ride: false, rounds: false, fades: false, college: false };
  const got = landingGame(sig({ groupPicks: { ride: 1, rounds: 9, fades: 0, college: 0 }, open: none }));
  assert.ok(GAME_IDS.includes(got), got);
});

test("the device's last choice is used when the group has no history", () => {
  assert.equal(landingGame(sig({ lastChosen: "college" })), "college");
});

test("a tie lands on one of the tied games (decision b)", () => {
  const got = landingGame(sig({ groupPicks: { ride: 0, rounds: 6, fades: 6, college: 1 } }));
  assert.ok(got === "rounds" || got === "fades", got);
});

test("same inputs, same answer (no randomness)", () => {
  const s = sig({ groupPicks: { ride: 3, rounds: 3, fades: 3, college: 3 } });
  assert.equal(landingGame(s), landingGame(s));
});

// TODO(Jack): one test for decision (a): lastChosen "rounds" while the group
// mostly plays "ride", both open. What lands, and why (in the test name).

// ── landingEvent: the PGA default ────────────────────────────────────────────

const ev = (tournament_id: string, tour: "pga" | "euro", status: LandingEvent["status"], start_date = "2026-10-22"): LandingEvent =>
  ({ tournament_id, tour, status, start_date });

test("PGA wins even when the DP World Tour event opens first", () => {
  const evs = [ev("E2026141", "euro", "open", "2026-10-21"), ev("R2026557", "pga", "open")];
  assert.equal(landingEvent(evs)?.tournament_id, "R2026557");
});

test("PGA's live event beats a DPWT open one: the tour comes first", () => {
  const evs = [ev("E2026141", "euro", "open"), ev("R2026557", "pga", "live")];
  assert.equal(landingEvent(evs)?.tournament_id, "R2026557");
});

test("a DP World Tour fan lands on the DP World Tour", () => {
  const evs = [ev("R2026557", "pga", "open"), ev("E2026141", "euro", "open")];
  assert.equal(landingEvent(evs, "euro")?.tournament_id, "E2026141");
});

test("no PGA events at all (a DPWT-only league) → whatever exists", () => {
  const evs = [ev("E2026141", "euro", "open")];
  assert.equal(landingEvent(evs)?.tournament_id, "E2026141");
});

test("within a tour: open, then live, then awaiting, then the latest final", () => {
  assert.equal(landingEvent([ev("A", "pga", "live"), ev("B", "pga", "open")])?.tournament_id, "B");
  assert.equal(landingEvent([ev("A", "pga", "awaiting"), ev("B", "pga", "live")])?.tournament_id, "B");
  assert.equal(landingEvent([
    ev("A", "pga", "completed", "2026-10-01"), ev("B", "pga", "completed", "2026-10-08"),
  ])?.tournament_id, "B");
});

test("empty list → undefined", () => {
  assert.equal(landingEvent([]), undefined);
});
