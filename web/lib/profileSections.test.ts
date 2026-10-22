/**
 * Tests for profileSections.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { profileSections, type ProfileInput } from "./profileSections.ts";

// TODO(Jack): delete this flag once profileSections passes.
const TODO = { todo: "Jack: implement profileSections" };

const BERMUDA = "Butterfield Bermuda Championship";
// Shapes from production, Oct 22.
const BEN_JAMES: ProfileInput = {   // in the field: everything present
  our_model: { win_prob: 0.0605, top10_prob: 0.3377 },
  dg_prediction: { win: 0.079 }, decompositions: { total_fit_adjustment: -0.14 },
  skill_ratings: { total: 1.277 }, approach_skill: { overall_prox: 29.8 }, betting_profile: { sg_total: 1.5 },
};
const SCHEFFLER: ProfileInput = {   // not playing Bermuda: only season-level data
  our_model: { win_prob: null }, dg_prediction: null, decompositions: null,
  skill_ratings: { total: 2.854 }, approach_skill: { overall_prox: 30.0 }, betting_profile: null,
};

test("a golfer in the field gets every section with data, in order", TODO, () => {
  assert.deepEqual(profileSections(BEN_JAMES, BERMUDA), {
    inField: true, note: null,
    show: ["thisWeek", "dgPrediction", "courseFit", "skills", "approach", "season", "career"],
  });
});

test("a golfer not in the field says so and shows season sections only", TODO, () => {
  assert.deepEqual(profileSections(SCHEFFLER, BERMUDA), {
    inField: false, note: "Not in the Butterfield Bermuda Championship field this week.",
    show: ["skills", "approach", "career"],
  });
});

test("no event name still reads naturally", TODO, () => {
  assert.equal(profileSections(SCHEFFLER, null).note, "Not in this week's field.");
  assert.equal(profileSections(SCHEFFLER, "").note, "Not in this week's field.");
});

test("either our model or DataGolf is enough to be in the field", TODO, () => {
  const dgOnly = { ...SCHEFFLER, dg_prediction: { win: 0.01 } };
  const p = profileSections(dgOnly, BERMUDA);
  assert.equal(p.inField, true);
  assert.deepEqual(p.show, ["dgPrediction", "skills", "approach", "career"]);   // no win chance -> no thisWeek
});

test("stray this-week data on a golfer not playing is not shown", TODO, () => {
  const stale = { ...SCHEFFLER, decompositions: { total_fit_adjustment: 0.2 } };
  assert.ok(!profileSections(stale, BERMUDA).show.includes("courseFit"));
});

test("a NaN win chance is not a win chance", TODO, () => {
  assert.equal(profileSections({ ...SCHEFFLER, our_model: { win_prob: Number.NaN } }, BERMUDA).inField, false);
  assert.equal(profileSections({ ...SCHEFFLER, our_model: null }, BERMUDA).inField, false);
});
