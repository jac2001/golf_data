/**
 * Tests for activeGroup.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { pickActiveGroup } from "./activeGroup.ts";

test("in no group → null, whatever the link or storage says", () => {
  assert.equal(pickActiveGroup([], null, null), null);
  assert.equal(pickActiveGroup([], 5, 7), null);
});

test("one group → that group", () => {
  assert.equal(pickActiveGroup([5], null, null), 5);
});

test("just joined through an invite → that group, over the stored one", () => {
  assert.equal(pickActiveGroup([5, 9], 9, 5), 9);
});

test("a link to a group they're NOT in is ignored", () => {
  assert.equal(pickActiveGroup([5, 9], 42, 5), 5);
});

test("the device's last choice is kept", () => {
  assert.equal(pickActiveGroup([5, 9, 12], null, 12), 12);
});

test("a stale stored choice (left that group) is ignored", () => {
  const got = pickActiveGroup([5, 9], null, 42);
  assert.ok(got === 5 || got === 9, String(got));
});

test("nothing usable, several groups → one of theirs (decision a)", () => {
  const got = pickActiveGroup([5, 9, 12], null, null);
  assert.ok([5, 9, 12].includes(got as number), String(got));
});

// TODO(Jack): one test for decision (a): [5, 9, 12] with no link and no
// stored choice. assert.equal the exact id, and say why in the name.

test("no link, no stored choice, several groups → the newest group (decision a)", () => {
  const got = pickActiveGroup([5, 9, 12], null, null);
  assert.equal(got, 12);
});
