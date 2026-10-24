import { test } from "node:test";
import assert from "node:assert/strict";
import { matchupDiff, type DiffLine } from "./matchupDiff.ts";

const line = (user_id: string, user_name: string, ...names: string[]): DiffLine =>
  ({ user_id, user_name, golfers: names.map(name => ({ name, position: "T5", earnings: 0, thru: "F" })) });
const jack = line("me", "Jack", "Scottie Scheffler", "Min Woo Lee", "Rory McIlroy");

test("matchupDiff: shared golfers cancel; the rest decide it", () => {
  const d = matchupDiff([jack, line("a", "Alex", "Scottie Scheffler", "Si Woo Kim", "Rory McIlroy")], "me", "a");
  assert.equal(d?.sentence, "You and Alex share 2 golfers (Scheffler and McIlroy). It comes down to Lee versus Kim.");
  assert.deepEqual(d?.mine.map(g => g.name), ["Min Woo Lee"]);
  assert.deepEqual(d?.theirs.map(g => g.name), ["Si Woo Kim"]);
});

test("matchupDiff: one shared golfer is named, not counted", () => {
  const d = matchupDiff([jack, line("a", "Alex", "Scottie Scheffler", "Si Woo Kim", "Jason Day")], "me", "a");
  assert.equal(d?.sentence, "You and Alex share Scheffler. It comes down to Lee and McIlroy versus Kim and Day.");
});

test("matchupDiff: nothing shared, identical, and subsets", () => {
  assert.equal(matchupDiff([jack, line("a", "Alex", "Si Woo Kim", "Jason Day", "Ben Griffin")], "me", "a")?.sentence,
    "You and Alex share no golfers: it's Scheffler, Lee and McIlroy against Kim, Day and Griffin.");
  assert.equal(matchupDiff([jack, line("a", "Alex", "Rory McIlroy", "Min Woo Lee", "Scottie Scheffler")], "me", "a")?.sentence,
    "You and Alex picked the same golfers, so this one can only end level.");
  assert.equal(matchupDiff([line("me", "Jack", "Rory McIlroy"), line("a", "Alex", "Rory McIlroy", "Si Woo Kim")], "me", "a")?.sentence,
    "All your golfers are in Alex's lineup too. It comes down to Kim.");
});

test("matchupDiff: no rival, no lineup, or yourself gives nothing", () => {
  assert.equal(matchupDiff([jack], "me", "a"), null);
  assert.equal(matchupDiff([jack], "me", null), null);
  assert.equal(matchupDiff([jack], "me", "me"), null);
  assert.equal(matchupDiff([line("me", "Jack"), line("a", "Alex", "Si Woo Kim")], "me", "a"), null);
});