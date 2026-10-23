/** Tests for roundContext.ts. Run from web/:  npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { byPosition, contextLine, roundContext } from "./roundContext.ts";
import { nameKey } from "./names.ts";

// Bermuda after Round 1 (Oct 22), trimmed.
const LIVE = [
  { player_name: "Corey Conners", position: "T2", total: "-8" },
  { player_name: "Chandler Blanchet", position: "1", total: "-9" },
  { player_name: "Aaron Wise", position: "T110", total: "+4" },
];
const TEES = [
  { tee_time: "7:35 AM", players: [{ name: "Corey Conners", start_tee: 10 }, { name: "Rico Hoey", start_tee: 10 }] },
  { tee_time: "12:40 PM", players: [{ name: "Chandler Blanchet", start_tee: 1 }] },
];

test("joins the live board and the tee sheet by name", () => {
  const ctx = roundContext(LIVE, TEES);
  assert.deepEqual(ctx.get(nameKey("Corey Conners")),
    { position: "T2", toPar: "-8", teeTime: "7:35 AM", startTee: 10 });
  assert.deepEqual(ctx.get(nameKey("Rico Hoey")),     // tee sheet only
    { position: null, toPar: null, teeTime: "7:35 AM", startTee: 10 });
});

test("the picker line", () => {
  const ctx = roundContext(LIVE, TEES);
  assert.equal(contextLine(ctx.get(nameKey("Corey Conners"))), "T2 · -8 · tees 7:35 AM, No. 10");
  assert.equal(contextLine(ctx.get(nameKey("Chandler Blanchet"))), "1 · -9 · tees 12:40 PM");
  assert.equal(contextLine(ctx.get(nameKey("Aaron Wise"))), "T110 · +4");
  assert.equal(contextLine(undefined), null);
});

test("missing sources give an empty map, not an error", () => {
  assert.equal(roundContext(null, undefined).size, 0);
  assert.equal(roundContext([{ player_name: "", position: "1", total: "-1" }], []).size, 0);
});

test("sorted by position, ties as numbers, unknowns last in original order", () => {
  const ctx = roundContext(LIVE, TEES);
  const field = ["Rico Hoey", "Aaron Wise", "Corey Conners", "Unknown Guy", "Chandler Blanchet"]
    .map(player_name => ({ player_name }));
  assert.deepEqual([...field].sort(byPosition(ctx)).map(r => r.player_name),
    ["Chandler Blanchet", "Corey Conners", "Aaron Wise", "Rico Hoey", "Unknown Guy"]);
});
