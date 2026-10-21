/**
 * Tests for thingsToWatch.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { thingsToWatch, type WatchInput } from "./thingsToWatch.ts";

const card = (pars: number[]) => pars.map((hole_par, i) => ({ hole_num: i + 1, hole_par }));
// Port Royal (Bermuda 2026, from /api/course): par 71 with par 5s at 2, 7 and 17.
const PORT_ROYAL = card([4, 5, 3, 4, 4, 4, 5, 3, 4, 4, 4, 4, 3, 4, 4, 3, 5, 4]);
const PROFILE = { ott: 0.30, app: 0.347, arg: 0.272, putt: 0.082 };
const LIGHT = [{ day: "Thu", wind_mph: 3 }, { day: "Fri", wind_mph: 10 }, { day: "Sat", wind_mph: 12 }, { day: "Sun", wind_mph: 12 }];

test("Bermuda this week: profile, light wind, par 5s (no history)", () => {
  assert.deepEqual(thingsToWatch({ profile: PROFILE, holes: PORT_ROYAL, forecast: LIGHT, history: null }), [
    { text: "Approach play separates the field more than anything else here (35% of what matters).", source: "DataGolf course profile" },
    { text: "Light winds forecast (up to 12 mph), good for scoring.", source: "This week's forecast" },
    { text: "3 par 5s are the best birdie chances.", source: "Scorecard" },
  ]);
});

test("history comes first and pushes par 5s out of the three", () => {
  const w = thingsToWatch({ profile: PROFILE, holes: PORT_ROYAL, forecast: LIGHT,
    history: { years: [2023, 2021, 2025], winning_to_par: [-15, -14, -17] } });
  assert.equal(w.length, 3);
  assert.deepEqual(w[0], { text: "Winners have finished an average of 15 under par here.", source: "Past winners, 2021–2025" });
  assert.equal(w[2].source, "This week's forecast");
});

test("one edition is not a pattern", () => {
  const w = thingsToWatch({ holes: PORT_ROYAL, history: { years: [2025], winning_to_par: [-20] } });
  assert.ok(!w.some(x => x.source.startsWith("Past winners")));
});

test("strong wind names the day", () => {
  const w = thingsToWatch({ holes: card([4, 4, 3]),
    forecast: [{ day: "Thu", wind_mph: 8 }, { day: "Fri", wind_mph: 18.4 }, { day: "Sat", wind_mph: null }] });
  assert.deepEqual(w, [{ text: "Wind up to 18 mph on Fri could push scores up.", source: "This week's forecast" }]);
});

test("one par 5 reads as singular", () => {
  assert.deepEqual(thingsToWatch({ holes: card([4, 5, 3]) }),
    [{ text: "1 par 5 is the best birdie chance.", source: "Scorecard" }]);
});

test("missing data is skipped, never invented", () => {
  assert.deepEqual(thingsToWatch({ holes: card([4, 4, 3]), profile: null, forecast: [{ day: "Thu", wind_mph: null }], history: null }), []);
  assert.deepEqual(thingsToWatch({ holes: [] }), []);
});

// Follow-up wording cases: keep the displayed numbers and claims consistent.

test("a winning average that rounds to 0 is 'around even par'", () => {
  assert.equal(thingsToWatch({ holes: [], history: { years: [2024, 2025], winning_to_par: [-1, 0.2] } })[0]?.text,
    "Winners have finished around even par here.");
});

test("a profile tie names both skills, not one 'more than anything else'", () => {
  assert.equal(thingsToWatch({ holes: [], profile: { ott: 0.3, app: 0.3, arg: 0.2, putt: 0.2 } })[0]?.text,
    "Approach play and driving matter most here (30% each).");
});

test("wind is judged on the number we show", () => {
  // 14.6 shows as 15 mph, so it must read as the 15+ sentence, not 'light'.
  assert.equal(thingsToWatch({ holes: [], forecast: [{ day: "Sat", wind_mph: 14.6 }] })[0]?.text,
    "Wind up to 15 mph on Sat could push scores up.");
});
