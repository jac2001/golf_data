/**
 * Tests for pickConfirm.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_BODY, confirmCopy } from "./pickConfirm.ts";
import type { ConfirmInput } from "./pickConfirm.ts";

const c = (over: Partial<ConfirmInput> = {}): ConfirmInput => ({
  picked: ["Scottie Scheffler", "Rory McIlroy", "Ludvig Åberg"],
  needed: 3, lockDetail: "locks Wed at midnight ET", remindersOn: null, ...over,
});
const lastName = (n: string) => n.split(" ").slice(-1)[0];

// ── complete ─────────────────────────────────────────────────────────────────

test("a full lineup is complete and says you're in", () => {
  const out = confirmCopy(c());
  assert.equal(out.complete, true);
  assert.match(out.title, /in/i);
});

test("the confirmation names every pick", () => {
  const out = confirmCopy(c());
  for (const n of ["Scottie Scheffler", "Rory McIlroy", "Ludvig Åberg"]) {
    assert.ok(out.body.includes(lastName(n)), `${n} missing: ${out.body}`);
  }
});

test("it says when picks lock", () => {
  assert.match(confirmCopy(c()).body, /locks Wed at midnight ET/);
});

test("an unknown lock time is left out, not invented", () => {
  const out = confirmCopy(c({ lockDetail: "" }));
  assert.doesNotMatch(out.body, /lock|midnight|\d+h/i);
});

// ── not complete ─────────────────────────────────────────────────────────────

test("one of three → saved, with what's left", () => {
  const out = confirmCopy(c({ picked: ["Scottie Scheffler"] }));
  assert.equal(out.complete, false);
  assert.match(out.title, /saved/i);
  assert.match(out.body, /1 of 3/);
  assert.match(out.body, /2 to go|2 more|2 left/);
});

test("the saved note names the golfer just added (the last one)", () => {
  const out = confirmCopy(c({ picked: ["Scottie Scheffler", "Rory McIlroy"] }));
  assert.ok(`${out.title} ${out.body}`.includes("McIlroy"), `${out.title} | ${out.body}`);
});

// ── reminders: never promised unless they're on ─────────────────────────────

test("no reminder promise when reminders are off or unknown", () => {
  for (const remindersOn of [false, null]) {
    const out = confirmCopy(c({ remindersOn }));
    assert.doesNotMatch(out.body.toLowerCase(), /we'll remind|we will remind/, String(remindersOn));
  }
});

// ── tone and size ────────────────────────────────────────────────────────────

const SAMPLES: ConfirmInput[] = [
  c(), c({ remindersOn: true }), c({ remindersOn: false }), c({ picked: ["Scottie Scheffler"] }),
  c({ picked: ["Auburn"], needed: 1, lockDetail: "locks in 3h 12m" }),
  c({ picked: ["Christiaan Bezuidenhout", "Matthieu Pavon", "Nicolai Højgaard"], lockDetail: "locks in 23h 59m", remindersOn: true }),
];

test("short enough for a phone", () => {
  for (const s of SAMPLES) {
    const out = confirmCopy(s);
    assert.ok(out.body.length <= MAX_BODY, `${out.body.length}: ${out.body}`);
  }
});

test("no money or winning talk", () => {
  for (const s of SAMPLES) {
    const out = confirmCopy(s);
    assert.doesNotMatch(`${out.title} ${out.body}`, /\$|earn|prize|payout|win|guarantee/i, out.body);
  }
});

test("a single-pick game (College) completes with one", () => {
  assert.equal(confirmCopy(c({ picked: ["Auburn"], needed: 1 })).complete, true);
});

// TODO(Jack): one test for decision (a): the three-golfer lineup above.
// assert.equal the exact body your function writes.
test("decision (a): full names, in pick order", () => {
  assert.equal(
    confirmCopy(c()).body,
    "Scottie Scheffler, Rory McIlroy, Ludvig Åberg. Lineup locks Wed at midnight ET. Turn on reminders in Settings.",
  );
});