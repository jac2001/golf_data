import { test } from "node:test";
import assert from "node:assert/strict";
import { computeGroupRecords, prepareRecordWeeks } from "./groupRecords.ts";
import type { RecordScope, RecordWeek } from "./groupRecords.ts";
const scope: RecordScope = { groupId: "g1", seasonId: "s1", mode: "let-it-ride" };
const week = (order: number, a: number, b: number, extra: Partial<RecordWeek> = {}): RecordWeek => ({
  scope, weekId: `w${order}`, order, status: "final", complete: true, official: true,
  entries: [{ userId: "a", earningsCents: a }, { userId: "model", earningsCents: b }], ...extra,
});
const run = (w: RecordWeek[]) => computeGroupRecords(prepareRecordWeeks(w), scope);
test("records: two wins build a streak; model competes under same rules", () => {
  assert.deepEqual(run([week(2, 200, 100), week(1, 150, 100)]), {
    wins: { value: 2, holderIds: ["a"] }, streak: { value: 2, holderIds: ["a"] },
    earnings: { value: 200, holderIds: ["a"] },
  });
});
test("records: ties share earnings, do not award wins, break streaks", () => {
  assert.deepEqual(run([week(1, 200, 100), week(2, 300, 300), week(3, 200, 100)]), {
    wins: { value: 2, holderIds: ["a"] }, streak: { value: 1, holderIds: ["a"] },
    earnings: { value: 300, holderIds: ["a", "model"] },
  });
});
test("records: unsettled or estimated weeks cannot award or bridge streaks", () => {
  for (const extra of [{ status: "pending" as const }, { complete: false }, { official: false }]) {
    const result = run([week(1, 200, 100), week(2, 999, 10, extra), week(3, 200, 100)]);
    assert.equal(result.streak?.value, 1);
    assert.equal(result.earnings?.value, 200);
  }
});
test("records: exact group and season isolation", () => {
  assert.deepEqual(run([week(1, 100, 50, { scope: { ...scope, groupId: "other" } })]),
    { wins: null, streak: null, earnings: null });
});
test("records: corrected results rebuild instead of incrementing counters", () => {
  const corrected = [week(1, 100, 200), week(2, 200, 100)];
  assert.deepEqual(run(corrected).wins, { value: 1, holderIds: ["a", "model"] });
  assert.equal(run(corrected).streak?.value, 1);
});
test("records: adapter rejects duplicates and invalid money", () => {
  assert.throws(() => prepareRecordWeeks([week(1, 2, 1), week(1, 2, 1)]));
  assert.throws(() => prepareRecordWeeks([week(1, NaN, 1)]));
  assert.throws(() => prepareRecordWeeks([week(1, 1, 1, { entries: [
    { userId: "a", earningsCents: 1 }, { userId: "a", earningsCents: 2 },
  ] })]));
});
