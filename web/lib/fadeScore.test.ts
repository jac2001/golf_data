/** Tests for fadeScore.ts. Run from web/:  npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { fadeTotal } from "./fadeScore.ts";

test("no withdrawals: the plain sum", () => {
  assert.equal(fadeTotal([10_000, 30_000, 0]), 40_000);   // a missed cut's $0 counts
});

test("a void fade counts as the average of the others, never as a free $0", () => {
  assert.equal(fadeTotal([40_000, 20_000, "void"]), 90_000);
  assert.ok(fadeTotal([40_000, 20_000, "void"])! > fadeTotal([40_000, 20_000, 0])!);
});

test("two voids: the one real fade stands in for all three", () => {
  assert.equal(fadeTotal([50_000, "void", "void"]), 150_000);
});

test("all void: no score rather than a winning $0", () => {
  assert.equal(fadeTotal(["void", "void", "void"]), null);
  assert.equal(fadeTotal([]), null);
});
