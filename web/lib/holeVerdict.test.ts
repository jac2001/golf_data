/**
 * Tests for holeVerdict.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { holeSentence, holeVerdict } from "./holeVerdict.ts";

// TODO(Jack): delete this flag once both functions pass.
const TODO = { todo: "Jack: implement holeVerdict + holeSentence" };

test("easy, around par, tough", TODO, () => {
  assert.equal(holeVerdict(-0.42), "chance");
  assert.equal(holeVerdict(0.05), "par");
  assert.equal(holeVerdict(-0.1), "par");
  assert.equal(holeVerdict(0.31), "tough");
});

test("exactly on the line counts", TODO, () => {
  assert.equal(holeVerdict(0.15), "tough");
  assert.equal(holeVerdict(0.35 - 0.2), "tough");     // 0.14999999999999997 in floats
  assert.equal(holeVerdict(-0.35 + 0.2), "chance");   // -0.14999999999999997
});

test("not played means no label", TODO, () => {
  for (const d of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) assert.equal(holeVerdict(d), null);
});

test("plain-words sentence", TODO, () => {
  assert.equal(holeSentence(0.31), "Playing 0.31 shots over par.");
  assert.equal(holeSentence(-0.42), "Playing 0.42 shots under par.");
  assert.equal(holeSentence(0.002), "Playing right at par.");
  assert.equal(holeSentence(-0.004), "Playing right at par.");
  assert.equal(holeSentence(1), "Playing 1.00 shot over par.");
  assert.equal(holeSentence(-1), "Playing 1.00 shot under par.");
  assert.equal(holeSentence(null), "Not played yet this week.");
  assert.equal(holeSentence(Number.NaN), "Not played yet this week.");
});
