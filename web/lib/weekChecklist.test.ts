/**
 * Tests for weekChecklist.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { weekChecklist, type GameStatus } from "./weekChecklist.ts";



// Wednesday Oct 21, 4pm ET: when Rick made his Let It Ride picks.
const NOW = new Date("2026-10-21T20:00:00Z");
const MIDNIGHT_THU = new Date("2026-10-22T04:00:00Z");   // Bermuda locks (midnight ET)
const MIDNIGHT_FRI = new Date("2026-10-23T04:00:00Z");   // Round 2 locks

const ride: GameStatus = { key: "ride", game: "ride", label: "Let It Ride", locksAt: MIDNIGHT_THU, have: 3, needed: 3 };
const r1: GameStatus = { key: "r1", game: "rounds", label: "Round Game · Round 1", locksAt: MIDNIGHT_THU, have: 0, needed: 1 };
const fades: GameStatus = { key: "fades", game: "fades", label: "Fade Game", locksAt: MIDNIGHT_THU, have: 1, needed: 3 };
const college: GameStatus = { key: "college", game: "college", label: "College Game", locksAt: MIDNIGHT_THU, have: 0, needed: 1 };

test("Rick's Wednesday: the three games he hadn't picked, in order",  () => {
  const rows = weekChecklist([ride, r1, fades, college], NOW);
  assert.deepEqual(rows.map(r => r.game), ["rounds", "fades", "college"]);   // ride is full
  assert.deepEqual(rows.map(r => r.left), [1, 2, 1]);
  assert.ok(rows.every(r => r.soon));                                       // 8 hours away
  assert.equal(rows[0].label, "Round Game · Round 1");
  assert.equal(rows[0].key, "r1");
  assert.equal(rows[0].locksAt.getTime(), MIDNIGHT_THU.getTime());
});

test("soonest lock first; ties keep their order", () => {
  const r2 = { ...r1, key: "r2", label: "Round Game · Round 2", locksAt: MIDNIGHT_FRI };
  const rows = weekChecklist([r2, college, fades], NOW);
  assert.deepEqual(rows.map(r => r.label), ["College Game", "Fade Game", "Round Game · Round 2"]);
});

test("locked, unknown, off and full games are left out", () => {
  const past = { ...college, locksAt: new Date("2026-10-21T19:59:59Z") };
  const atNow = { ...college, locksAt: NOW };                 // locking this instant: locked
  const unknown = { ...college, locksAt: null };              // fail closed
  const off = { ...college, needed: 0 };                      // not played in this group
  const over = { ...fades, have: 4, needed: 3 };              // more than needed still means full
  assert.deepEqual(weekChecklist([past, atNow, unknown, off, over, ride], NOW), []);
  assert.deepEqual(weekChecklist([], NOW), []);
});

test("soon means within 24 hours, inclusive",  () => {
  const day = 24 * 60 * 60 * 1000;
  const exactly = { ...college, locksAt: new Date(NOW.getTime() + day) };
  const later = { ...college, locksAt: new Date(NOW.getTime() + day + 1) };
  assert.equal(weekChecklist([exactly], NOW)[0].soon, true);
  assert.equal(weekChecklist([later], NOW)[0].soon, false);
});

test("doesn't change what it was given",  () => {
  const input = [college, r1];
  const copy = input.map(s => ({ ...s }));
  weekChecklist(input, NOW);
  assert.deepEqual(input, copy);
});
