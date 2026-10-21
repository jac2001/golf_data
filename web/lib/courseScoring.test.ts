/** Run from web/: npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { scoringPlayed } from "./courseScoring.ts";

const h = (hole_par: number, scoring_avg: number | null, birdies: number | null, bogeys: number | null) =>
  ({ hole_par, scoring_avg, birdies, bogeys });

test("the pre-round feed (avg = par, 0 birdies, 0 bogeys) is not played", () => {
  // Port Royal, Oct 21, before round 1, as /api/course sends it.
  assert.equal(scoringPlayed([h(4, 4.0, 0, 0), h(5, 5.0, 0, 0), h(3, 3.0, 0, 0)]), false);
  assert.equal(scoringPlayed([h(4, null, null, null)]), false);
  assert.equal(scoringPlayed([]), false);
});

test("any real scoring means played", () => {
  assert.equal(scoringPlayed([h(4, 4.0, 0, 0), h(5, 4.71, 22, 3)]), true);
  assert.equal(scoringPlayed([h(4, 4.0, 5, 5)]), true);   // a real even-par average still has birdies and bogeys
});
