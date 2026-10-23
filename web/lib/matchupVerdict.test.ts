/**
 * Tests for matchupVerdict.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { matchupVerdict, type Category } from "./matchupVerdict.ts";

// TODO(Jack): delete this flag once all tests pass.
const TODO = { todo: "Jack: implement matchupVerdict" };

const sg = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
const yd = (v: number) => `${v.toFixed(1)} yd`;
const cat = (say: string, a: number | null, b: number | null, over: Partial<Category> = {}): Category =>
  ({ say, a, b, higherBetter: true, tie: 0.05, fmt: sg, ...over });

// Conners vs Blanchet, Bermuda, Oct 23 (published chances and DataGolf skills).
const WIN = { a: 0.0336, b: 0.0042, tie: 0.002 };
const CATS = [
  cat("better approach play", 0.54, -0.10),
  cat("better off the tee", 0.38, 0.05),
  cat("better putting", -0.09, -0.24),
  cat("better around the green", -0.02, -0.33),
  cat("longer off the tee", 302.1, 303.2, { tie: 0.5, fmt: yd }),
];

test("Conners vs Blanchet: the edge, two reasons, Blanchet's one", TODO, () => {
  assert.deepEqual(matchupVerdict("Conners", "Blanchet", WIN, CATS), {
    edge: "a",
    headline: "Conners has the edge: 3.4% vs 0.4% to win.",
    reasons: [
      "Conners: better approach play (+0.54 vs -0.10)",
      "Conners: better off the tee (+0.38 vs +0.05)",
      "Blanchet: longer off the tee (303.2 yd vs 302.1 yd)",
    ],
  });
});

test("the leader can be B; his chance comes first", TODO, () => {
  const v = matchupVerdict("Blanchet", "Conners", { a: 0.0042, b: 0.0336, tie: 0.002 }, []);
  assert.equal(v?.edge, "b");
  assert.equal(v?.headline, "Conners has the edge: 3.4% vs 0.4% to win.");
  assert.deepEqual(v?.reasons, []);
});

test("win chances inside the tie are too close to call", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: 0.021, b: 0.020, tie: 0.002 },
    [cat("better approach play", 0.3, 0.1), cat("better putting", 0.1, 0.4)]);
  assert.equal(v?.edge, "even");
  assert.equal(v?.headline, "Too close to call: 2.1% vs 2.0% to win.");
  assert.deepEqual(v?.reasons, ["Kim: better approach play (+0.30 vs +0.10)", "Lee: better putting (+0.40 vs +0.10)"]);
});

test("no win chance: counted categories, missing values left out", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: null, b: null, tie: 0.002 }, [
    cat("better approach play", 0.3, 0.1), cat("better off the tee", 0.2, 0.0),
    cat("better putting", 0.1, 0.3), cat("better around the green", null, 0.2),
  ]);
  assert.equal(v?.edge, "a");
  assert.equal(v?.headline, "Kim leads 2 of 3 categories.");
});

test("lower is better when higherBetter is false; ties lead nobody", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: null, b: null, tie: 0.002 }, [
    cat("a better world rank", 12, 40, { higherBetter: false, tie: 0.5, fmt: v => `#${v}` }),
    cat("better putting", 0.10, 0.12),   // inside the 0.05 tie
  ]);
  assert.equal(v?.headline, "Kim leads 1 of 2 categories.");
  assert.deepEqual(v?.reasons, ["Kim: a better world rank (#12 vs #40)"]);
});

test("a clean sweep says so", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: 0.05, b: 0.01, tie: 0.002 },
    [cat("better approach play", 0.5, 0.1), cat("better putting", 0.4, 0.0), cat("better off the tee", 0.3, 0.1)]);
  assert.deepEqual(v?.reasons, [
    "Kim: better approach play (+0.50 vs +0.10)",
    "Kim: better putting (+0.40 vs +0.00)",
    "Kim leads every category we compare.",
  ]);
});

test("even on categories without a win chance", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: null, b: null, tie: 0.002 },
    [cat("better approach play", 0.3, 0.1), cat("better putting", 0.1, 0.3)]);
  assert.equal(v?.edge, "even");
  assert.equal(v?.headline, "Even: 1 category each.");
});

test("one category, singular", TODO, () => {
  const v = matchupVerdict("Kim", "Lee", { a: null, b: null, tie: 0.002 }, [cat("better putting", 0.4, 0.1)]);
  assert.equal(v?.headline, "Kim leads 1 of 1 category.");
});

test("nothing to compare is null", TODO, () => {
  assert.equal(matchupVerdict("Kim", "Lee", { a: null, b: 0.02, tie: 0.002 }, [cat("x", null, 1)]), null);
  assert.equal(matchupVerdict("Kim", "Lee", { a: Number.NaN, b: 0.02, tie: 0.002 }, []), null);
});
