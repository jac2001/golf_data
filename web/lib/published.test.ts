/** Tests for published.ts. Run from web/:  npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { shown } from "./published.ts";

test("the simulation wins when it exists; the base fills in", () => {
  // Conners, Bermuda: base 6.3%, simulation 3.4% (what This Week shows).
  assert.deepEqual(shown({ win_prob: 0.0634, win_prob_sim: 0.0336, top10_prob: 0.30, top10_prob_sim: 0.2441 }),
    { win_prob: 0.0336, win_prob_sim: 0.0336, top10_prob: 0.2441, top10_prob_sim: 0.2441 });
  assert.equal(shown({ win_prob: 0.05, win_prob_sim: null }).win_prob, 0.05);
  assert.equal(shown({ win_prob: 0.05 }).win_prob, 0.05);
  assert.equal(shown({}).win_prob, null);
});
