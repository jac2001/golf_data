/**
 * Tests for pickReason.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { modelPickReason, type PickReasonInput } from "./pickReason.ts";

// TODO(Jack): delete this flag once all tests pass.
const TODO = { todo: "Jack: implement modelPickReason" };

const ev = (name: string, v: number) => ({ tid: name, name, start_date: "2027-01-01", purse: 9_000_000, ev: v });
const base: PickReasonInput = { winProb: null, winRank: null, why: null, nowEv: 0, usesLeft: 3, future: [] };

// Bermuda, Oct 20: the model's three picks.
test("Conners: top pick, and this week is his best event", TODO, () => {
  const r = modelPickReason({ ...base, winProb: 0.121, winRank: 1, nowEv: 127_000,
    future: [ev("Genesis Invitational", 110_000), ev("WM Phoenix Open", 122_000), ev("Valspar", 90_000)] });
  assert.equal(r, "Model's top pick: about a 1 in 8 chance to win. His best event left: about $127K expected, ahead of WM Phoenix Open ($122K).");
});

test("James: a why line, and one of his best events", TODO, () => {
  const r = modelPickReason({ ...base, winProb: 0.062, winRank: 2, why: "Top-10 in 3 of his last 5 starts",
    nowEv: 125_000, future: [ev("Cognizant Classic", 131_000), ev("RBC Heritage", 123_000), ev("Valero", 100_000)] });
  assert.equal(r, "Top-10 in 3 of his last 5 starts. One of his 3 best events left: about $125K expected (best: $131K at Cognizant Classic).");
});

test("Kohles: picked although a later event is worth more — no 'save'", TODO, () => {
  const r = modelPickReason({ ...base, winProb: 0.042, winRank: 4, why: "Made the cut at this event 3 of 3 times",
    nowEv: 110_000, usesLeft: 1, future: [ev("The American Express", 117_000)] });
  assert.equal(r, "Made the cut at this event 3 of 3 times. Worth more at The American Express ($117K), but still one of this week's best uses.");
});

test("the use given up is the one at position usesLeft", TODO, () => {
  const r = modelPickReason({ ...base, nowEv: 100_000, usesLeft: 2,
    future: [ev("A", 150_000), ev("B", 120_000), ev("C", 80_000)] });
  assert.equal(r, "Worth more at B ($120K), but still one of this week's best uses.");
});

test("no future events, no golfer case", TODO, () => {
  assert.equal(modelPickReason({ ...base, nowEv: 114_000 }), "His best event left: about $114K expected.");
});

test("a win chance without a why line; ties count for this week", TODO, () => {
  const r = modelPickReason({ ...base, winProb: 0.02, winRank: 30, nowEv: 90_000, future: [ev("A", 90_000)] });
  assert.equal(r, "About a 1 in 50 chance to win. His best event left: about $90K expected, ahead of A ($90K).");
});

test("zero or missing win chance says nothing about winning", TODO, () => {
  assert.equal(modelPickReason({ ...base, winProb: 0, winRank: 1, nowEv: 50_000 }), "His best event left: about $50K expected.");
});
