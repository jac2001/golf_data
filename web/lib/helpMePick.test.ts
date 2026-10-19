/**
 * Tests for helpMePick.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { helpMePick } from "./helpMePick.ts";
import type { Candidate } from "./helpMePick.ts";

const g = (name: string, over: Partial<Candidate> = {}): Candidate => ({
  name, key: name.toLowerCase(), usesLeft: 3,
  advice: { verdict: "spend", score: 100 }, winProb: 0.02, why: `${name} why`, ...over,
});

const FIELD: Candidate[] = [
  g("Scheffler", { advice: { verdict: "save", score: 900 }, winProb: 0.2 }),
  g("McIlroy", { advice: { verdict: "spend", score: 800 }, winProb: 0.1 }),
  g("Aberg", { advice: { verdict: "spend", score: 700 }, winProb: 0.08 }),
  g("Spent Guy", { usesLeft: 0, advice: { verdict: "spent", score: -Infinity }, winProb: 0.15 }),
  g("Morikawa", { advice: { verdict: "spend", score: 600 }, winProb: 0.06 }),
  g("Longshot", { advice: { verdict: "spend", score: 10 }, winProb: 0.003, why: "" }),
];
const names = (s: { name: string }[]) => s.map(x => x.name);

test("empty lineup → exactly `slots` suggestions, none kept", () => {
  const s = helpMePick(FIELD, [], 3);
  assert.equal(s.length, 3);
  assert.ok(s.every(x => !x.kept));
});

test("never suggests a golfer with no uses left", () => {
  for (const slots of [1, 3, 5]) assert.ok(!names(helpMePick(FIELD, [], slots)).includes("Spent Guy"));
});

test("existing picks stay first, kept, in their order", () => {
  const s = helpMePick(FIELD, ["morikawa", "longshot"], 3);
  assert.deepEqual(s.slice(0, 2).map(x => [x.name, x.kept]), [["Morikawa", true], ["Longshot", true]]);
  assert.equal(s.length, 3);
  assert.equal(s[2].kept, false);
});

test("never suggests someone already in the lineup", () => {
  const s = helpMePick(FIELD, ["mcilroy"], 3);
  assert.equal(names(s).filter(n => n === "McIlroy").length, 1);
});

test("a full lineup gets no suggestions", () => {
  const s = helpMePick(FIELD, ["mcilroy", "aberg", "morikawa"], 3);
  assert.ok(s.every(x => x.kept));
  assert.equal(s.length, 3);
});

test("not enough eligible golfers → fewer suggestions, never padded", () => {
  const tiny = [g("A"), g("B", { usesLeft: 0, advice: { verdict: "spent", score: -Infinity } })];
  assert.deepEqual(names(helpMePick(tiny, [], 3)), ["A"]);
});

test("advice score ranks the spend golfers", () => {
  const s = names(helpMePick(FIELD.filter(x => x.name !== "Scheffler"), [], 2));
  assert.deepEqual(s, ["McIlroy", "Aberg"]);
});

test("no advice this week → ranked by win chance, unknowns last", () => {
  const noAdvice = [
    g("Low", { advice: null, winProb: 0.01 }), g("Unknown", { advice: null, winProb: null }),
    g("High", { advice: null, winProb: 0.12 }), g("Mid", { advice: null, winProb: 0.05 }),
  ];
  assert.deepEqual(names(helpMePick(noAdvice, [], 4)), ["High", "Mid", "Low", "Unknown"]);
});

test("same input, same answer", () => {
  assert.deepEqual(helpMePick(FIELD, ["aberg"], 3), helpMePick(FIELD, ["aberg"], 3));
});

test("lines never promise or quote money", () => {
  for (const x of helpMePick(FIELD, [], 5)) {
    assert.doesNotMatch(x.line, /\$|\bwill\b|guarantee|lock\b|sure thing/i, x.line);
  }
});

// TODO(Jack): one test for decision (a): an empty 3-slot lineup from FIELD.
// Scheffler has the best score but is a "save". assert.deepEqual the exact
// three names your rule suggests.
test("a save golfer is skipped while spend golfers are left: a beginner never burns a use the advice says to keep (decision a)", () => {
  assert.deepEqual(names(helpMePick(FIELD, [], 3)), ["McIlroy", "Aberg", "Morikawa"]);
});