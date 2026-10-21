/**
 * Tests for fitVerdict.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { fitVerdict } from "./fitVerdict.ts";

// TODO(Jack): delete this flag once fitVerdict passes. Until then the tests
// run and report but don't fail `npm test` (so the hook doesn't block edits).
const TODO = { todo: "Jack: implement fitVerdict" };

test("a course worth +0.10 strokes or more suits him", TODO, () => {
  assert.deepEqual(fitVerdict(0.37, 0.0), { verdict: "suits", edge: 0.37 });
  assert.deepEqual(fitVerdict(0.06, 0.05), { verdict: "suits", edge: 0.11 });   // history tips it
});

test("worth -0.10 or less hurts him", TODO, () => {
  assert.deepEqual(fitVerdict(-0.14, 0.0), { verdict: "hurts", edge: -0.14 });
  assert.deepEqual(fitVerdict(-0.06, -0.05), { verdict: "hurts", edge: -0.11 });
});

test("in between is neutral", TODO, () => {
  assert.deepEqual(fitVerdict(0.06, 0.0), { verdict: "neutral", edge: 0.06 });
  assert.deepEqual(fitVerdict(0.12, -0.05), { verdict: "neutral", edge: 0.07 });   // history pulls him back
});

test("exactly on the line counts", TODO, () => {
  assert.equal(fitVerdict(0.01, 0.09)?.verdict, "suits");    // 0.01 + 0.09 is 0.09999999999999999 in floats
  assert.equal(fitVerdict(0.3, -0.2)?.verdict, "suits");     // 0.09999999999999998
  assert.equal(fitVerdict(-0.01, -0.09)?.verdict, "hurts");
});

test("missing history counts as zero", TODO, () => {
  assert.deepEqual(fitVerdict(0.2, null), { verdict: "suits", edge: 0.2 });
  assert.deepEqual(fitVerdict(0.2, undefined), { verdict: "suits", edge: 0.2 });
  assert.deepEqual(fitVerdict(0.2, Number.NaN), { verdict: "suits", edge: 0.2 });
});

test("no fit number, no verdict", TODO, () => {
  assert.equal(fitVerdict(null, 0.3), null);
  assert.equal(fitVerdict(undefined, 0.3), null);
  assert.equal(fitVerdict(Number.NaN, 0.3), null);
});
