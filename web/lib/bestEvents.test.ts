/**
 * Tests for bestEvents.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { bestEvents } from "./bestEvents.ts";

// TODO(Jack): delete this flag once all tests pass.
const TODO = { todo: "Jack: implement bestEvents" };

const w = (name: string, ev: number) => ({ tid: name, name, start_date: "2027-01-01", purse: 9_000_000, ev });
const BERMUDA = { tid: "R2026528", name: "Bermuda" };
const names = (r: ReturnType<typeof bestEvents>) => r.events.map(e => `${e.name} ${e.ev / 1000}K${e.thisWeek ? "*" : ""}`);

test("Conners: one of his 3 best (Cognizant is worth more)", TODO, () => {
  const r = bestEvents(BERMUDA, 127_000, [w("WM Phoenix", 122_000), w("Cognizant", 132_000), w("Valspar", 90_000)], 3);
  assert.deepEqual(names(r), ["Cognizant 132K", "Bermuda 127K*", "WM Phoenix 122K"]);
  assert.equal(r.rank, 2);
  assert.equal(r.fit, "top");
  assert.equal(r.tag, "One of his 3 best");
});

test("James: this week is his best", TODO, () => {
  const r = bestEvents(BERMUDA, 126_000, [w("Houston", 125_000), w("Cognizant", 124_000)], 3);
  assert.equal(r.rank, 1);
  assert.equal(r.fit, "best");
  assert.equal(r.tag, "Best week for him");
});

test("Kohles with 1 use: a later event is worth more", TODO, () => {
  const r = bestEvents(BERMUDA, 110_000, [w("The American Express", 117_000)], 1);
  assert.equal(r.rank, 2);
  assert.equal(r.fit, "later");
  assert.equal(r.tag, "Better at The American Express ($117K)");
});

test("the use given up is the future event at position usesLeft", TODO, () => {
  const r = bestEvents(BERMUDA, 100_000, [w("A", 150_000), w("B", 120_000), w("C", 80_000)], 2);
  assert.equal(r.tag, "Better at B ($120K)");
});

test("this week always shows, even outside the top `show`", TODO, () => {
  const r = bestEvents(BERMUDA, 50_000, [w("A", 150_000), w("B", 120_000), w("C", 80_000), w("D", 70_000)], 3);
  assert.deepEqual(names(r), ["A 150K", "B 120K", "C 80K", "Bermuda 50K*"]);
  assert.equal(r.rank, 5);
});

test("ties: this week first, future events keep their order", TODO, () => {
  const r = bestEvents(BERMUDA, 100_000, [w("Y", 100_000), w("X", 100_000)], 3);
  assert.deepEqual(names(r), ["Bermuda 100K*", "Y 100K", "X 100K"]);
  assert.equal(r.fit, "best");
});

test("no uses left wins over everything", TODO, () => {
  const r = bestEvents(BERMUDA, 200_000, [], 0);
  assert.equal(r.fit, "spent");
  assert.equal(r.tag, "No uses left");
});

test("doesn't change the future list", TODO, () => {
  const future = [w("B", 1), w("A", 2)];
  bestEvents(BERMUDA, 0, future, 3);
  assert.deepEqual(future.map(f => f.name), ["B", "A"]);
});
