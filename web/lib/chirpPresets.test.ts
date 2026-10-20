/**
 * Tests for chirpPresets.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { LINES, MAX_PRESETS, chirpPresets } from "./chirpPresets.ts";
import type { ChirpContext } from "./chirpPresets.ts";

const c = (over: Partial<ChirpContext> = {}): ChirpContext => ({
  status: "live", myRank: 2, players: 4, tied: false, myGolferLeading: null,
  myGolfersOut: 0, myGolfers: 3, aheadOfModel: null, ...over,
});
const texts = (ctx: ChirpContext) => chirpPresets(ctx).map(p => p.text);
const TAUNTS = [LINES.leading, LINES.passed, LINES.beatModel];

test("before lock: no taunts, only neutral lines", () => {
  const t = texts(c({ status: "open", myRank: 1, myGolferLeading: "Scheffler", aheadOfModel: true }));
  for (const x of TAUNTS) assert.ok(!t.includes(x), `${x} offered before lock`);
  assert.ok(t.length >= 1);
});

test("didn't play: nothing to brag about", () => {
  const t = texts(c({ myRank: null, aheadOfModel: true, myGolferLeading: "Scheffler" }));
  for (const x of TAUNTS) assert.ok(!t.includes(x), x);
});

test("'Don't look now' only when one of your golfers leads", () => {
  assert.ok(texts(c({ myGolferLeading: "Scheffler" })).includes(LINES.leading));
  assert.ok(!texts(c()).includes(LINES.leading));
});

test("'Check the leaderboard' only when you lead the group", () => {
  assert.ok(texts(c({ myRank: 1 })).includes(LINES.passed));
  assert.ok(!texts(c({ myRank: 2 })).includes(LINES.passed));
});

test("leading with nobody else on the slate doesn't count", () => {
  assert.ok(!texts(c({ myRank: 1, players: 1 })).includes(LINES.passed));
});

test("'So much for the expert' only when you're ahead of the model", () => {
  assert.ok(texts(c({ aheadOfModel: true })).includes(LINES.beatModel));
  for (const v of [false, null]) assert.ok(!texts(c({ aheadOfModel: v })).includes(LINES.beatModel), String(v));
});

test("a lineup that's all out gets 'There's always next week'", () => {
  assert.ok(texts(c({ myGolfersOut: 3, myGolfers: 3 })).includes(LINES.collapse));
  assert.ok(!texts(c({ myGolfersOut: 0 })).includes(LINES.collapse));
});

test("never more than MAX_PRESETS, no duplicates", () => {
  const t = texts(c({ myRank: 1, myGolferLeading: "Scheffler", aheadOfModel: true, myGolfersOut: 3, myGolfers: 3 }));
  assert.ok(t.length <= MAX_PRESETS, String(t.length));
  assert.equal(new Set(t).size, t.length);
});

test("every preset has an id and no money", () => {
  for (const p of chirpPresets(c({ myRank: 1, myGolferLeading: "Scheffler", aheadOfModel: true }))) {
    assert.ok(p.id.length > 0);
    assert.doesNotMatch(p.text, /\$/);
  }
});

test("same input, same output", () => {
  const ctx = c({ myRank: 1, aheadOfModel: true });
  assert.deepEqual(chirpPresets(ctx), chirpPresets(ctx));
});

// TODO(Jack): one test for decision (a): leading the group, ahead of the
// model, AND your golfer leads the tournament. assert.deepEqual the exact
// texts in your order.

test("every preset's id is the LINES key for its text (the server sends LINES[id])", () => {
  const all = chirpPresets(c({ myRank: 1, myGolferLeading: "Scheffler", aheadOfModel: true, myGolfersOut: 3, myGolfers: 3 }));
  for (const p of all) assert.equal((LINES as Record<string, string>)[p.id], p.text, p.id);
});
test("group rivalry first, then the model, then the golfer (decision a)", () => {
  assert.deepEqual(texts(c({ myRank: 1, aheadOfModel: true, myGolferLeading: "Scheffler" })),
    ["Check the leaderboard", "So much for the expert", "Don't look now"]);
});