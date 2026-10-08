/**
 * Tests for advice.ts — the spend/save rule, written BEFORE the code.
 * Run from web/:  npm test
 *
 * Unlike the scratch headline test, this imports the real file
 * (relative path + .ts extension, which tsconfig now allows), so the
 * code under test can't drift from the code that ships.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { golferVerdict, adviseSlate } from "./advice.ts";
import type { GolferValue, FutureWindow } from "./advice.ts";


const win = (name: string, ev: number): FutureWindow =>
  ({ tid: name, name, start_date: "2026-10-15", purse: ev * 20, ev });

const golfer = (now_ev: number, future: FutureWindow[], name = "Matt Fitzpatrick"): GolferValue =>
  ({ player_name: name, key: name.toLowerCase(), now_ev, future });

test("no uses left → spent, never picked", () => {
  const v = golferVerdict(golfer(500_000, []), 0);
  assert.equal(v.verdict, "spent");
  assert.equal(v.score, -Infinity);
});

test("no future windows → spend at full value", () => {
  const v = golferVerdict(golfer(500_000, []), 3);
  assert.equal(v.verdict, "spend");
  assert.equal(v.score, 500_000);
});

test("3 uses, windows 900/700/400, now 500 → spend (it beats the 3rd-best window)", () => {
  const v = golferVerdict(golfer(500_000, [win("A", 900_000), win("B", 700_000), win("C", 400_000)]), 3);
  assert.equal(v.verdict, "spend");
  assert.equal(v.score, 500_000);
});

test("1 use, best window 900, now 500 → save for that window", () => {
  const v = golferVerdict(golfer(500_000, [win("Masters", 900_000), win("B", 300_000)]), 1);
  assert.equal(v.verdict, "save");
  assert.equal(v.saveFor?.name, "Masters");
  assert.equal(v.score, 500_000 - (900_000 - 500_000));
});

test("windows arrive unsorted → still uses the left-th best", () => {
  const v = golferVerdict(golfer(650_000, [win("C", 400_000), win("A", 900_000), win("B", 700_000)]), 2);
  assert.equal(v.verdict, "save");          // 2nd best is B at 700K, and 650K < 700K
  assert.equal(v.saveFor?.name, "B");
});

test("more uses than windows → spending now costs nothing", () => {
  const v = golferVerdict(golfer(200_000, [win("A", 900_000)]), 2);
  assert.equal(v.verdict, "spend");
});

test("reason names both numbers", () => {
  const v = golferVerdict(golfer(410_000, [win("the Masters", 1_200_000)]), 1);
  assert.match(v.reason, /410K/);
  assert.match(v.reason, /1\.20M/);
});

test("slate takes the top scores and skips spent golfers", () => {
  const field = [
    golfer(900_000, [], "Spent Star"),
    golfer(600_000, [], "Ready One"),
    golfer(500_000, [], "Ready Two"),
    golfer(100_000, [], "Long Shot"),
  ];
  const { slate } = adviseSlate(field, { "spent star": 0 }, 3, 2);
  assert.deepEqual(slate, ["Ready One", "Ready Two"]);
});



test("doesn't reorder the caller's windows", () => {
  const windows = [win("C", 400_000), win("A", 900_000)];
  golferVerdict(golfer(500_000, windows), 2);
  assert.deepEqual(windows.map(w => w.name), ["C", "A"]);
});

test("nothing ahead → reason doesn't mention $0", () => {
  const v = golferVerdict(golfer(500_000, []), 3);
  assert.doesNotMatch(v.reason, /\$0/);
});

test("windows filtered out → says he wouldn't be a top pick", () => {
  const v = golferVerdict({ ...golfer(125_000, []), allWindows: 3 }, 3);
  assert.match(v.reason, /top pick/);
});
