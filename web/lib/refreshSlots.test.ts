/**
 * Tests for refreshSlots.ts (the watchdog's dropped-slot check).
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { missedSlot } from "./refreshSlots.ts";

// Oct 20, 2026 is a Tuesday. The watchdog runs daily at 15:00 UTC.
const TUE_1500 = new Date("2026-10-20T15:00:00Z");

test("the Oct 20 case: Tuesday's 11:00 UTC slot dropped, last run Monday 19:11 → re-run tuesday-morning", () => {
  assert.equal(missedSlot(TUE_1500, [run("2026-10-19T19:11:15Z", "monday")]), "tuesday-morning");
});

test("the slot ran (even 2 hours late) → nothing to do", () => {
  assert.equal(missedSlot(TUE_1500, [run("2026-10-20T13:02:00Z", "tuesday-morning")]), null);
});

test("an early manual dispatch just before the slot covers it", () => {
  assert.equal(missedSlot(TUE_1500, [run("2026-10-20T10:50:00Z", "tuesday-morning")]), null);
});

test("a slot less than 3 hours old isn't judged yet (GitHub runs late)", () => {
  assert.equal(missedSlot(new Date("2026-10-20T13:30:00Z"), [run("2026-10-19T19:11:15Z", "monday")]), null);
});

test("Wednesday 15:00: Tuesday evening's 23:00 slot dropped, and Wednesday morning's too → the latest (wednesday-morning)", () => {
  const wed = new Date("2026-10-21T15:00:00Z");
  assert.equal(missedSlot(wed, [run("2026-10-20T14:39:21Z", "tuesday-morning")]), "wednesday-morning");
});

test("Wednesday 15:00: Wednesday morning ran → covers Tuesday evening too", () => {
  const wed = new Date("2026-10-21T15:00:00Z");
  assert.equal(missedSlot(wed, [run("2026-10-21T11:40:00Z", "wednesday-morning")]), null);
});

test("Thursday 15:00: Wednesday evening's slot dropped → wednesday-evening", () => {
  const thu = new Date("2026-10-22T15:00:00Z");
  assert.equal(missedSlot(thu, [run("2026-10-21T11:40:00Z", "wednesday-morning")]), "wednesday-evening");
});

test("weekend: no Mon–Wed slots in the window → nothing", () => {
  assert.equal(missedSlot(new Date("2026-10-24T15:00:00Z"), []), null);
});

test("Monday 15:00: the monday slot dropped → monday", () => {
  assert.equal(missedSlot(new Date("2026-10-19T15:00:00Z"), [run("2026-10-18T19:10:42Z", "post-tournament")]), "monday");
});
function run(
  created_at: string,
  schedule: string,
  conclusion: string | null = "success"
) {
  return {
    created_at,
    conclusion,
    display_title: `Data Refresh | ${schedule}`,
  };
}

test("a settlement run does not cover Monday's refresh", () => {
  assert.equal(
    missedSlot(new Date("2026-10-19T15:00:00Z"), [
      run("2026-10-19T13:00:00Z", "post-tournament"),
    ]),
    "monday"
  );
});

test("a failed Tuesday refresh still needs recovery", () => {
  assert.equal(
    missedSlot(TUE_1500, [
      run("2026-10-20T11:00:00Z", "tuesday-morning", "failure"),
    ]),
    "tuesday-morning"
  );
});

test("a refresh still running counts (a re-dispatch would only queue a duplicate)", () => {
  assert.equal(missedSlot(TUE_1500, [run("2026-10-20T13:50:00Z", "tuesday-morning", null)]), null);
});

test("a scheduled run is matched by its cron, and a cancelled one doesn't count", () => {
  const cron = (at: string, conclusion: string | null) =>
    ({ created_at: at, conclusion, display_title: "Data Refresh | 0 11 * * 2" });
  assert.equal(missedSlot(TUE_1500, [cron("2026-10-20T12:30:00Z", "success")]), null);
  assert.equal(missedSlot(TUE_1500, [cron("2026-10-20T12:30:00Z", "cancelled")]), "tuesday-morning");
});
