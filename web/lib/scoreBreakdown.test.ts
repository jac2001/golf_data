import { test } from "node:test";
import assert from "node:assert/strict";
import { buildScoreBreakdown, SCORE_COPY } from "./scoreBreakdown.ts";
import type { ScoreInput } from "./scoreBreakdown.ts";

const base = (): ScoreInput => ({
  game: "ride", status: "live",
  lineup: { total: 31329, golfers: [
    { name: "Luke Clanton", position: "T30", earnings: 31329 },
    { name: "Ben James", position: "T76", earnings: 0 },
  ] },
});

test("score breakdown: no personal scoring before lock or without a lineup", () => {
  for (const status of ["open", "awaiting"] as const) {
    assert.equal(buildScoreBreakdown({ ...base(), status }), null);
  }
  assert.equal(buildScoreBreakdown({ ...base(), lineup: null }), null);
  assert.equal(buildScoreBreakdown({ ...base(), lineup: { total: 0, golfers: [] } }), null);
});

test("score breakdown: live rows explain the total without extra golf stats", () => {
  assert.deepEqual(buildScoreBreakdown(base()), {
    title: "Your lineup score", note: SCORE_COPY.live, rule: SCORE_COPY.ride, total: 31329,
    rows: [
      { name: "Luke Clanton", position: "T30", amount: 31329 },
      { name: "Ben James", position: "T76", amount: 0 },
    ],
  });
});

test("score breakdown: settling, official final and estimated final are distinct", () => {
  for (const [status, estimated, note] of [
    ["settling", false, SCORE_COPY.settling],
    ["final", false, SCORE_COPY.final],
    ["final", true, SCORE_COPY.estimatedFinal],
  ] as const) {
    assert.equal(buildScoreBreakdown({ ...base(), status, estimated })?.note, note);
  }
});

test("score breakdown: unresolved and unknown positions are pending, never zero", () => {
  for (const golfer of [
    { name: "Unknown", position: "?", earnings: 0, unresolved: true },
    ...["", " ", "—", "-", "?"].map(position => ({ name: "Unknown", position, earnings: 0 })),
    { name: "Unknown", position: "T30", earnings: 0, unresolved: true },
  ]) {
    const result = buildScoreBreakdown({ ...base(), lineup: { total: 0, golfers: [golfer] } });
    assert.ok(result);
    assert.equal(result.rows[0].amount, null);
    assert.equal(result.total, null);
  }
});

test("score breakdown: invalid earnings and totals cannot become a score", () => {
  for (const invalid of [null, NaN, Infinity, -1]) {
    const input = base();
    input.lineup!.golfers = [{ name: "Luke", position: "T30", earnings: invalid }];
    const result = buildScoreBreakdown(input);
    assert.ok(result);
    assert.equal(result.rows[0].amount, null);
    assert.equal(result.total, null);
    const badTotal = base();
    badTotal.lineup!.total = invalid;
    assert.equal(buildScoreBreakdown(badTotal)?.total, null);
  }
  const incomplete = base();
  incomplete.lineup!.incomplete = true;
  assert.equal(buildScoreBreakdown(incomplete)?.total, null);
});

test("score breakdown: preserves API precision and legitimate CUT/WD zeros", () => {
  const input = base();
  input.lineup = { total: 10.49, golfers: [
    { name: "A", position: "1", earnings: 10.49 },
    { name: "B", position: "CUT", earnings: 0 },
    { name: "C", position: "WD", earnings: 0 },
  ] };
  const result = buildScoreBreakdown(input);
  assert.ok(result);
  assert.equal(result.total, 10.49);
  assert.deepEqual(result.rows.map(r => r.amount), [10.49, 0, 0]);
});

test("score breakdown: College uses counting alumni supplied by API", () => {
  const result = buildScoreBreakdown({ ...base(), game: "college" });
  assert.ok(result);
  assert.equal(result.title, "Your school score");
  assert.equal(result.rule, SCORE_COPY.college);
  assert.equal(result.rows.length, 2);
});

test("score breakdown: deterministic, immutable, preserves authoritative total", () => {
  const input = base();
  input.lineup!.total = 31329.25; // Presentation must not silently re-score.
  const copy = structuredClone(input);
  const result = buildScoreBreakdown(input);
  assert.ok(result);
  assert.equal(result.total, 31329.25);
  assert.deepEqual(buildScoreBreakdown(input), result);
  assert.deepEqual(input, copy);
});
