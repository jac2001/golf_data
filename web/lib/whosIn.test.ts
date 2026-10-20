/**
 * Tests for whosIn.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { whosIn } from "./whosIn.ts";
import type { MemberCount } from "./whosIn.ts";

const EVENT = "Butterfield Bermuda Championship";
const LOCK = "locks Wed at midnight ET";
const m = (name: string, picked: number, user_id = name.toLowerCase()): MemberCount => ({ user_id, name, picked });

const GROUP: MemberCount[] = [
  m("Jack", 3), m("Rick", 0), m("Sam", 2), m("Alex", 3), m("Golf Edge model", 3, "model"),
];

// ── counting ─────────────────────────────────────────────────────────────────

test("the model isn't counted as a member", () => {
  const w = whosIn(GROUP, 3, EVENT, LOCK);
  assert.ok(!w.inNames.includes("Golf Edge model") && !w.waitingNames.includes("Golf Edge model"));
  assert.match(w.headline, /2 of 4/);
});

test("in = a full entry; partial and none are waiting", () => {
  const w = whosIn(GROUP, 3, EVENT, LOCK);
  assert.deepEqual([...w.inNames].sort(), ["Alex", "Jack"]);
  assert.deepEqual([...w.waitingNames].sort(), ["Rick", "Sam"]);
});

test("names come out in a stable order", () => {
  const shuffled = [GROUP[3], GROUP[1], GROUP[4], GROUP[0], GROUP[2]];
  assert.deepEqual(whosIn(shuffled, 3, EVENT, LOCK), whosIn(GROUP, 3, EVENT, LOCK));
});

test("a single-pick game (College) works the same", () => {
  const w = whosIn([m("Jack", 1), m("Rick", 0)], 1, EVENT, LOCK);
  assert.deepEqual(w.inNames, ["Jack"]);
  assert.deepEqual(w.waitingNames, ["Rick"]);
});

// ── the share text ───────────────────────────────────────────────────────────

test("everyone in → nothing to share", () => {
  const w = whosIn([m("Jack", 3), m("Alex", 3)], 3, EVENT, LOCK);
  assert.equal(w.shareText, "");
  assert.match(w.headline, /2 of 2/);
});

test("the nudge names who's still to pick and when picks lock", () => {
  const w = whosIn(GROUP, 3, EVENT, LOCK);
  assert.match(w.shareText, /Rick/);
  assert.match(w.shareText, /Sam/);
  assert.match(w.shareText, /locks Wed at midnight ET/);
});

test("an unknown lock time is left out, not invented", () => {
  assert.doesNotMatch(whosIn(GROUP, 3, EVENT, "").shareText, /lock|midnight/i);
});

test("never names someone who's already in", () => {
  const w = whosIn(GROUP, 3, EVENT, LOCK);
  assert.doesNotMatch(w.shareText, /\bJack\b|\bAlex\b/);
});

test("no money, no shaming", () => {
  const w = whosIn(GROUP, 3, EVENT, LOCK);
  assert.doesNotMatch(w.shareText, /\$|earn|prize|lazy|slacker|loser|forgot/i, w.shareText);
});

test("short enough for a group chat", () => {
  const big = Array.from({ length: 12 }, (_, i) => m(`Player${i}`, 0));
  assert.ok(whosIn(big, 3, EVENT, LOCK).shareText.length <= 200);
});

test("decision (b): the nudge for the sample group", () => {
  assert.equal(whosIn(GROUP, 3, EVENT, LOCK).shareText, "Still need picks for Butterfield Bermuda Championship: Rick, Sam. Lineup locks Wed at midnight ET.");
});