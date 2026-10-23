/**
 * Tests for chaseHeadline.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { chaseHeadline, type Standing } from "./chaseHeadline.ts";



const row = (user_id: string, rank: number, total: number, user_name = user_id): Standing =>
  ({ user_id, user_name, rank, total });

// The TEST GROUP board, Friday morning Oct 23 (Bermuda, live).
const FRIDAY = [
  row("rick", 1, 1_240_000, "Rick Legnon"),
  row("inv2", 2, 533_267, "Invite Two"),
  row("model", 2, 533_267, "The Model"),
  row("me", 4, 19_056, "Jack Legnon"),
];

test("names the real leader, not the rival",  () => {
  assert.equal(chaseHeadline(FRIDAY, "me", false), "You're 4th of 4. Rick Legnon leads by $1.22M.");
});

test("The Model can lead",  () => {
  const thu = [row("model", 1, 804_000, "The Model"), row("inv2", 2, 591_600, "Invite Two"),
    row("rick", 3, 491_889, "Rick Legnon"), row("me", 4, 31_329)];
  assert.equal(chaseHeadline(thu, "me", false), "You're 4th of 4. The Model leads by $772,671.");
});

test("you tied with someone below the lead",  () => {
  assert.equal(chaseHeadline(FRIDAY, "inv2", false), "You're tied for 2nd of 4. Rick Legnon leads by $706,733.");
  assert.equal(chaseHeadline(FRIDAY, "inv2", true), "You finished tied for 2nd of 4. Rick Legnon won by $706,733.");
});

test("final, one winner",  () => {
  assert.equal(chaseHeadline(FRIDAY, "me", true), "You finished 4th of 4. Rick Legnon won by $1.22M.");
});

test("two tied leaders, in board order",  () => {
  const b = [row("sam", 1, 900_000, "Sam"), row("rick", 1, 900_000, "Rick"), row("me", 3, 400_000)];
  assert.equal(chaseHeadline(b, "me", false), "You're 3rd of 3. Sam and Rick lead by $500,000.");
  assert.equal(chaseHeadline(b, "me", true), "You finished 3rd of 3. Sam and Rick shared the win, $500,000 ahead.");
});

test("three or more tied leaders are counted, not listed",  () => {
  const b = [row("a", 1, 600_000, "A"), row("b", 1, 600_000, "B"), row("c", 1, 600_000, "C"), row("me", 4, 100_000)];
  assert.equal(chaseHeadline(b, "me", false), "You're 4th of 4. 3 players share the lead, $500,000 ahead.");
  assert.equal(chaseHeadline(b, "me", true), "You finished 4th of 4. 3 players shared the win, $500,000 ahead.");
});

test("not your case: leading, tied for the lead, or not on the board",  () => {
  assert.equal(chaseHeadline(FRIDAY, "rick", false), null);
  const tiedTop = [row("me", 1, 500_000), row("sam", 1, 500_000, "Sam")];
  assert.equal(chaseHeadline(tiedTop, "me", false), null);
  assert.equal(chaseHeadline(FRIDAY, "nobody", false), null);
  assert.equal(chaseHeadline([], "me", false), null);
});
