/**
 * Tests for whyLine.ts — written before the code.
 * Run from web/:  npm test
 *
 * These pin honesty, length and tone. Your order and thresholds (a)–(c)
 * are left open.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_WHY_LENGTH, countTopN, oneIn, whyLine } from "./whyLine.ts";
import type { GolferFacts } from "./whyLine.ts";


const g = (over: Partial<GolferFacts> = {}): GolferFacts => ({
  recent: [], courseStarts: 0, courseCuts: 0, winProb: null, top10Prob: null, worldRank: null, ...over,
});

const HOT: GolferFacts["recent"] = [3, 7, 1, "MC", 9];          // top-10 in 4 of 5
const COLD: GolferFacts["recent"] = ["MC", 61, "MC", "MC", 44];  // 3 missed cuts

// ── the helpers (already written) ────────────────────────────────────────────

test("helpers: countTopN and oneIn", () => {
  assert.equal(countTopN(HOT, 10), 4);
  assert.equal(countTopN(COLD, 10), 0);
  assert.equal(oneIn(0.0167), "1 in 60");
  assert.equal(oneIn(0.25), "1 in 4");
  assert.equal(oneIn(0), null);
  assert.equal(oneIn(null), null);
});

// ── honest ───────────────────────────────────────────────────────────────────

test("nothing known → empty line, not filler", () => {
  assert.equal(whyLine(g()), "");
});

test("a hot streak says it, with the real count", () => {
  const s = whyLine(g({ recent: HOT }));
  assert.match(s, /4 of (his )?last 5/);
});

test("only 3 starts on record → never claims 'last 5'", () => {
  const s = whyLine(g({ recent: [2, 5, 8] }));
  assert.doesNotMatch(s, /last 5/);
});

test("no course history → never mentions 'here' or the course", () => {
  for (const facts of [g({ recent: HOT }), g({ winProb: 0.2, top10Prob: 0.6 }), g({ winProb: 0.004 })]) {
    assert.doesNotMatch(whyLine(facts).toLowerCase(), /\bhere\b|course|this event/);
  }
});

test("a strong course record can be the line", () => {
  const s = whyLine(g({ courseStarts: 5, courseCuts: 5 }));
  assert.match(s, /5 of 5|every/);
});

// ── tone ─────────────────────────────────────────────────────────────────────

const SAMPLES: GolferFacts[] = [
  g({ recent: HOT, winProb: 0.18, top10Prob: 0.55, worldRank: 1 }),
  g({ recent: COLD, winProb: 0.003 }),
  g({ courseStarts: 6, courseCuts: 6, winProb: 0.02 }),
  g({ winProb: 0.0167, top10Prob: 0.08, worldRank: 140 }),
  g({ recent: [2, 5, 8], courseStarts: 1, courseCuts: 0 }),
  g({ winProb: 0.3, top10Prob: 0.7, worldRank: 1 }),
];

test("never a promise", () => {
  for (const f of SAMPLES) {
    assert.doesNotMatch(whyLine(f).toLowerCase(), /\bwill\b|\block\b|guarantee|can't miss|cannot miss|sure thing/, whyLine(f));
  }
});

test("short, one line, no trailing period", () => {
  for (const f of SAMPLES) {
    const s = whyLine(f);
    assert.ok(s.length <= MAX_WHY_LENGTH, `${s.length}: ${s}`);
    assert.ok(!s.includes("\n") && !s.endsWith("."), s);
  }
});

test("no money words", () => {
  for (const f of SAMPLES) assert.doesNotMatch(whyLine(f), /\$|earn|purse|prize|payout/i, whyLine(f));
});

test("a long shot's chance is said as a chance", () => {
  const s = whyLine(g({ winProb: 0.004 }));   // under LONG_SHOT_WIN (0.5%)
  assert.equal(s, "Long shot: about a 1 in 250 chance to win");
});

test("same facts, same line", () => {
  for (const f of SAMPLES) assert.equal(whyLine(f), whyLine(f));
});

// TODO(Jack): one test for decision (a): a golfer who is BOTH hot (HOT) and
// has a perfect course record (5 of 5 cuts). assert.equal the exact line
// your order picks, and say why in the test name.
test("hot streak beats perfect course record (decision a)", () => {
  const s = whyLine(g({ recent: HOT, courseStarts: 5, courseCuts: 5 }));
  assert.equal(s, "Top-10 in 4 of his last 5 starts");
});

test("a world rank alone gives nothing honest to say", () => {
  assert.equal(whyLine(g({ worldRank: 40 })), "");
});

test("perfect course record beats a top model chance (decision a)", () => {
  const s = whyLine(g({ courseStarts: 5, courseCuts: 5, winProb: 0.2 }));
  assert.match(s, /5 of 5|every/);
});

test("a top model chance beats a long shot (decision a)", () => {
  const s = whyLine(g({ winProb: 0.2, top10Prob: 0.55 }));
  assert.match(s, /about a 1 in 5 chance|top model/i);
});

test("a long shot beats a cold streak (decision a)", () => {
  const s = whyLine(g({ winProb: 0.004, top10Prob: 0.03, worldRank: 140 }));
  assert.match(s, /long shot/i);
});

test("a contender is never called a long shot", () => {
  assert.doesNotMatch(whyLine(g({ winProb: 0.048 })), /long shot/i);
});
