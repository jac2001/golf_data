/** Tests for fadePool (lib/modelBrain.ts). Run from web/:  npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { fadePool } from "./modelBrain.ts";

const g = (player_name: string, market_prob: number | null, win_prob: number) =>
  ({ player_name, market_prob, win_prob, top5_prob: null, top10_prob: null, top20_prob: null, cut_prob: null });

test("the market's favorites, best first, when enough are priced", () => {
  const field = [g("A", 0.02, 0.09), g("B", 0.08, 0.01), g("C", 0.05, 0.05), g("D", null, 0.2)];
  assert.deepEqual(fadePool(field, 3).map(p => p.player_name), ["B", "C", "A"]);
});

test("too few prices: the model's chance ranks everyone", () => {
  const field = [g("A", 0.02, 0.09), g("B", null, 0.01), g("C", null, 0.05)];
  assert.deepEqual(fadePool(field, 3).map(p => p.player_name), ["A", "C", "B"]);
});

test("doesn't reorder what it was given", () => {
  const field = [g("A", 0.01, 0.01), g("B", 0.02, 0.02)];
  fadePool(field, 2);
  assert.deepEqual(field.map(p => p.player_name), ["A", "B"]);
});
test("everyone tied at the cut is in, whatever order they arrived in", () => {
  const field = [g("A", 0.09, 0), g("B", 0.05, 0), g("C", 0.03, 0), g("D", 0.03, 0), g("E", 0.01, 0)];
  assert.deepEqual(fadePool(field, 3).map(p => p.player_name), ["A", "B", "C", "D"]);
  assert.deepEqual(fadePool([...field].reverse(), 3).map(p => p.player_name).sort(), ["A", "B", "C", "D"]);
});
