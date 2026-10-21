/**
 * An ambiguous pick is "unresolved", never a $0 golfer (audit, Oct 21).
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolvePick, UNRESOLVED_POS } from "./resultLookup.ts";
import { summarizeSlate } from "./matchCore.ts";

// Two golfers named Zach Johnson, as the API sends them.
const table = {
  "johnson zach":       { player_name: "Zach Johnson", player_id: "24024", earnings: 50_000, position: "T20" },
  "johnson zach#29747": { player_name: "Zach Johnson", player_id: "29747", earnings: 900_000, position: "2" },
  "scheffler scottie":  { player_name: "Scottie Scheffler", player_id: "46046", earnings: 1_500_000, position: "1" },
};
const quiet = <T>(fn: () => T): T => {
  const warn = console.warn; console.warn = () => {};
  try { return fn(); } finally { console.warn = warn; }
};

test("a shared name without an id is unresolved, not missing", () => {
  const r = quiet(() => resolvePick(table, { player_name: "Zach Johnson" }, "test"));
  assert.deepEqual(r, { hit: undefined, unresolved: true });
});

test("an id resolves it; an absent golfer is missing, not unresolved", () => {
  assert.equal(resolvePick(table, { player_name: "Zach Johnson", player_id: "29747" }, "t").hit?.earnings, 900_000);
  assert.deepEqual(resolvePick(table, { player_name: "Nobody Here" }, "t"), { hit: undefined, unresolved: false });
});

test("the match center marks the golfer and the member's total, and makes no claim", () => {
  const picks = [
    { user_id: "a", player_name: "Zach Johnson" },
    { user_id: "a", player_name: "Scottie Scheffler", player_id: "46046" },
    { user_id: "b", player_name: "Scottie Scheffler", player_id: "46046" },
  ];
  const s = quiet(() => summarizeSlate(picks, table, true, u => u.toUpperCase(), "a"));
  const a = s.lines.find(l => l.user_id === "a")!;
  const zach = a.golfers.find(g => g.name === "Zach Johnson")!;
  assert.equal(zach.position, UNRESOLVED_POS);
  assert.equal(zach.unresolved, true);
  assert.equal(a.incomplete, true);
  assert.equal(s.incomplete, true);
  assert.match(s.story, /incomplete/);
  assert.equal(s.lines.find(l => l.user_id === "b")!.incomplete, undefined);
});

test("a fully matched slate is not flagged", () => {
  const s = summarizeSlate([{ user_id: "a", player_name: "Scottie Scheffler" }], table, true, u => u, "a");
  assert.equal(s.incomplete, false);
  assert.equal(s.lines[0].golfers[0].unresolved, undefined);
});
