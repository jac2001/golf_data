/**
 * Tests for eventStatus.ts — written before the code.
 * Run from web/:  npm test
 *
 * The Bermuda Championship starts Thu 2026-10-22; PGA picks lock at
 * midnight ET at the start of that day (2026-10-22T04:00Z).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { countdown, eventStatusLine, weekdayOnTourClock } from "./eventStatus.ts";
import type { EventFacts } from "./eventStatus.ts";
import { lockAt } from "./lockTime.ts";

const LOCK = lockAt("2026-10-22", "pga");
const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
const before = (ms: number) => new Date(LOCK.getTime() - ms);

const bermuda = (over: Partial<EventFacts> = {}): EventFacts => ({
  status: "open", tour: "pga", startDate: "2026-10-22", lockAt: LOCK, round: null, ...over,
});

// ── the helpers (already written) ────────────────────────────────────────────

test("helpers: the lock really is midnight ET Thursday", () => {
  assert.equal(LOCK.toISOString(), "2026-10-22T04:00:00.000Z");
  assert.equal(weekdayOnTourClock(LOCK, "pga"), "Thu");
  assert.equal(countdown(3 * HOUR + 12 * MIN + 30_000), "3h 12m");
  assert.equal(countdown(45 * MIN), "45m");
});

// ── open ─────────────────────────────────────────────────────────────────────

test("open, locking soon → 'Picks open' + a countdown", () => {
  const s = eventStatusLine(bermuda(), before(3 * HOUR + 12 * MIN));
  assert.equal(s.state, "Picks open");
  assert.equal(s.tone, "go");
  assert.match(s.detail, /3h 12m/);
});

test("open, days away → names a day and the tour's clock, no countdown", () => {
  const s = eventStatusLine(bermuda(), before(3 * DAY));
  assert.equal(s.state, "Picks open");
  assert.match(s.detail, /Wed|Thu/);
  assert.match(s.detail, /ET/);
  assert.doesNotMatch(s.detail, /\d+h \d+m/);
});

test("the countdown switches on just under a day out", () => {
  assert.match(eventStatusLine(bermuda(), before(DAY - MIN)).detail, /23h 59m/);
  assert.doesNotMatch(eventStatusLine(bermuda(), before(DAY + MIN)).detail, /\d+h \d+m/);
});

test("DP World Tour says UK time, not ET", () => {
  const euro = bermuda({ tour: "euro", lockAt: lockAt("2026-10-22", "euro") });
  const s = eventStatusLine(euro, new Date(lockAt("2026-10-22", "euro").getTime() - 3 * DAY));
  assert.match(s.detail, /UK time/);
  assert.doesNotMatch(s.detail, /ET/);
});

test("open with an unknown lock never invents a time (decision b)", () => {
  const s = eventStatusLine(bermuda({ lockAt: null }), before(3 * DAY));
  assert.equal(s.state, "Picks open");
  assert.doesNotMatch(s.detail, /\d+h|\d+m|Wed|Thu/);
});

// ── the other statuses ───────────────────────────────────────────────────────

test("awaiting → quiet, about the field", () => {
  const s = eventStatusLine(bermuda({ status: "awaiting" }), before(3 * DAY));
  assert.equal(s.tone, "quiet");
  assert.match(`${s.state} ${s.detail}`.toLowerCase(), /field/);
});

test("live → 'Live', with the round when known", () => {
  const s = eventStatusLine(bermuda({ status: "live", round: 2 }), new Date(LOCK.getTime() + DAY + 5 * HOUR));
  assert.match(s.state, /^Live/);
  assert.equal(s.tone, "live");
  assert.match(`${s.state} ${s.detail}`, /Round 2/);
});

test("live without a round still says Live (decision c)", () => {
  const s = eventStatusLine(bermuda({ status: "live" }), new Date(LOCK.getTime() + 5 * HOUR));
  assert.match(s.state, /^Live/);
});

test("completed → Final, quiet", () => {
  const s = eventStatusLine(bermuda({ status: "completed" }), new Date(LOCK.getTime() + 5 * DAY));
  assert.equal(s.state, "Final");
  assert.equal(s.tone, "quiet");
});

test("upcoming → quiet, says when it starts", () => {
  const s = eventStatusLine(bermuda({ status: "upcoming" }), before(10 * DAY));
  assert.equal(s.tone, "quiet");
  assert.match(`${s.state} ${s.detail}`, /Oct 22/);
});

test("timing only: no money words (rule 6)", () => {
  for (const status of ["open", "awaiting", "live", "completed", "upcoming"] as const) {
    const s = eventStatusLine(bermuda({ status, round: 1 }), before(2 * DAY));
    assert.doesNotMatch(`${s.state} ${s.detail}`.toLowerCase(), /\$|projected|earnings|payout/, status);
  }
});

// TODO(Jack): one test for decision (a): three days out, what exactly does
// the detail say? assert.equal the whole string.

test("three days out, the detail says the day before the first round, on the tour's clock (decision a)", () => {
  const s = eventStatusLine(bermuda(), before(3 * DAY));
  assert.match(s.detail, /Wed|Thu/);
  assert.match(s.detail, /ET/);
  assert.equal(s.detail, "locks Wed at midnight ET");
});
