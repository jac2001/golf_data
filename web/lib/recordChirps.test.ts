import { test } from "node:test";
import assert from "node:assert/strict";
import { recordChirps, RECORD_LINES } from "./recordChirps.ts";
import type { RecordChirpContext } from "./recordChirps.ts";
const context = (): RecordChirpContext => ({ status: "final", played: true, eligible: true, userId: "a",
  before: { wins: null, streak: { value: 2, holderIds: ["b"] }, earnings: { value: 100, holderIds: ["b"] } },
  after: { wins: null, streak: { value: 3, holderIds: ["a"] }, earnings: { value: 200, holderIds: ["a"] } },
});
test("record chirps: earnings before streak, truthful fixed copy", () => {
  assert.deepEqual(recordChirps(context()), [
    { id: "recordEarnings", text: RECORD_LINES.recordEarnings },
    { id: "recordStreak", text: RECORD_LINES.recordStreak },
  ]);
});
test("record chirps: no claims before final, without play, or on historical views", () => {
  for (const patch of [{ status: "open" as const }, { status: "live" as const },
    { status: "settling" as const }, { played: false }, { eligible: false }]) {
    assert.deepEqual(recordChirps({ ...context(), ...patch }), []);
  }
});
test("record chirps: joining a tie is matching, not breaking", () => {
  const c = context();
  c.after = { wins: null, streak: null, earnings: { value: 100, holderIds: ["a", "b"] } };
  assert.deepEqual(recordChirps(c), [{ id: "tiedEarnings", text: RECORD_LINES.tiedEarnings }]);
  c.before = c.after;
  assert.deepEqual(recordChirps(c), []);
});
test("record chirps: baseline and someone else's records are quiet", () => {
  const c = context();
  c.before = { wins: null, streak: null, earnings: null };
  assert.deepEqual(recordChirps(c), []);
  assert.deepEqual(recordChirps({ ...context(), userId: "other" }), []);
});
