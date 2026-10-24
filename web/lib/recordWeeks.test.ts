import { test } from "node:test";
import assert from "node:assert/strict";
import { buildRecordWeeks, latestWeekEligibility, weekOf, type EventResults, type RecordPick } from "./recordWeeks.ts";
import { computeGroupRecords, prepareRecordWeeks, type RecordScope } from "./groupRecords.ts";

const scope: RecordScope = { groupId: "7", seasonId: "3", mode: "let-it-ride" };
const ev = (tournamentId: string, startDate: string) => ({ tournamentId, name: tournamentId, startDate });
const pick = (user_id: string, tournament_id: string, player_name: string, player_id: string | null = null): RecordPick =>
  ({ user_id, tournament_id, player_name, player_id });
const res = (players: Record<string, number>, extra: Partial<EventResults> = {}): EventResults => ({
  settled: true, estimated: false, ...extra,
  players: Object.fromEntries(Object.entries(players).map(([n, e]) => [n, { player_name: n, earnings: e }])),
});
const build = (events: ReturnType<typeof ev>[], picks: RecordPick[], results: Record<string, EventResults | null>, today = "2026-10-26") =>
  buildRecordWeeks(scope, events, picks, new Map(Object.entries(results)), today);

test("recordWeeks: weeks run Monday to Sunday by start date", () => {
  assert.deepEqual(weekOf("2026-10-22").weekId, "2026-10-19");   // Thursday
  assert.deepEqual(weekOf("2026-10-19").weekId, "2026-10-19");   // Monday
  assert.deepEqual(weekOf("2026-10-25").weekId, "2026-10-19");   // Sunday
  assert.equal(weekOf("2026-10-29").order - weekOf("2026-10-22").order, 1);
});

test("recordWeeks: both tours in one week combine; cents per member", () => {
  const h = build([ev("R2026528", "2026-10-22"), ev("E2026150", "2026-10-23")],
    [pick("a", "R2026528", "Corey Conners"), pick("a", "E2026150", "Tom McKibbin"), pick("model", "R2026528", "Ben Griffin")],
    { R2026528: res({ "Corey Conners": 100.5, "Ben Griffin": 150 }), E2026150: res({ "Tom McKibbin": 60.25 }) });
  assert.ok(h.ok);
  assert.equal(h.weeks.length, 1);
  assert.deepEqual(h.weeks[0].entries, [{ userId: "a", earningsCents: 16075 }, { userId: "model", earningsCents: 15000 }]);
  assert.deepEqual(h.events["2026-10-19"].map(e => e.tournamentId), ["R2026528", "E2026150"]);
});

test("recordWeeks: an unsettled or missing result makes the week pending with no entries", () => {
  for (const r of [res({ X: 1 }, { settled: false }), null]) {
    const h = build([ev("R1", "2026-10-22")], [pick("a", "R1", "X"), pick("b", "R1", "X")], { R1: r });
    assert.ok(h.ok);
    assert.deepEqual(h.weeks[0], { scope, weekId: "2026-10-19", order: h.weeks[0].order,
      status: "pending", complete: false, official: false, entries: [] });
  }
});

test("recordWeeks: estimated money is not official; an ambiguous name is incomplete", () => {
  const est = build([ev("R1", "2026-10-22")], [pick("a", "R1", "X")], { R1: res({ X: 5 }, { estimated: true }) });
  assert.ok(est.ok && est.weeks[0].official === false && est.weeks[0].status === "final");
  const amb: EventResults = { settled: true, estimated: false, players: {
    k1: { player_name: "Sam Smith", earnings: 9 }, k2: { player_name: "Sam Smith", earnings: 1 } } };
  const h = build([ev("E1", "2026-10-22")], [pick("a", "E1", "Sam Smith")], { E1: amb });
  assert.ok(h.ok && h.weeks[0].complete === false);
});

test("recordWeeks: a scheduled week nobody played still exists and breaks streaks", () => {
  const events = [ev("R1", "2026-10-01"), ev("R2", "2026-10-08"), ev("R3", "2026-10-15")];
  const picks = [pick("a", "R1", "X"), pick("model", "R1", "Y"), pick("a", "R3", "X"), pick("model", "R3", "Y")];
  const h = build(events, picks, { R1: res({ X: 10, Y: 1 }), R3: res({ X: 10, Y: 1 }) });
  assert.ok(h.ok);
  assert.equal(h.weeks.length, 3);
  assert.deepEqual(h.weeks[1].entries, []);
  const rec = computeGroupRecords(prepareRecordWeeks(h.weeks), scope);
  assert.deepEqual(rec.wins, { value: 2, holderIds: ["a"] });
  assert.deepEqual(rec.streak, { value: 1, holderIds: ["a"] });
});

test("recordWeeks: events not started yet are left out; future picks are fine", () => {
  const h = build([ev("R1", "2026-10-22"), ev("R2", "2026-10-29")],
    [pick("a", "R1", "X"), pick("a", "R2", "X")], { R1: res({ X: 1 }) }, "2026-10-26");
  assert.ok(h.ok);
  assert.deepEqual(h.weeks.map(w => w.weekId), ["2026-10-19"]);
});

test("recordWeeks: a pick on an unscheduled event refuses rather than drop money", () => {
  const h = build([ev("R1", "2026-10-22")], [pick("a", "E2027T01211", "X")], {});
  assert.deepEqual(h, { ok: false, reason: "unplaced-pick", tournamentId: "E2027T01211" });
});

test("recordWeeks: a corrected settlement rebuilds the records", () => {
  const events = [ev("R1", "2026-10-01"), ev("R2", "2026-10-08")];
  const picks = [pick("a", "R1", "X"), pick("b", "R1", "Y"), pick("a", "R2", "X"), pick("b", "R2", "Y")];
  const before = build(events, picks, { R1: res({ X: 10, Y: 1 }), R2: res({ X: 10, Y: 1 }) });
  const after = build(events, picks, { R1: res({ X: 10, Y: 1 }), R2: res({ X: 1, Y: 10 }) });
  assert.ok(before.ok && after.ok);
  assert.equal(computeGroupRecords(before.weeks, scope).streak?.value, 2);
  assert.deepEqual(computeGroupRecords(after.weeks, scope).wins, { value: 1, holderIds: ["a", "b"] });
});

test("recordWeeks: chirp eligibility needs a qualifying latest week and older history", () => {
  const events = [ev("R1", "2026-10-01"), ev("R2", "2026-10-08")];
  const picks = [pick("a", "R1", "X"), pick("b", "R1", "Y"), pick("a", "R2", "X"), pick("b", "R2", "Y")];
  const ok = build(events, picks, { R1: res({ X: 10, Y: 1 }), R2: res({ X: 10, Y: 1 }) });
  assert.ok(ok.ok);
  assert.deepEqual(latestWeekEligibility(ok.weeks), { weekId: "2026-10-05", eligible: true });
  const firstOnly = build([events[0]], picks.slice(0, 2), { R1: res({ X: 10, Y: 1 }) });
  assert.ok(firstOnly.ok && latestWeekEligibility(firstOnly.weeks).eligible === false);
  const pendingLatest = build(events, picks, { R1: res({ X: 10, Y: 1 }), R2: res({ X: 1 }, { settled: false }) });
  assert.ok(pendingLatest.ok);
  assert.deepEqual(latestWeekEligibility(pendingLatest.weeks), { weekId: "2026-10-05", eligible: false });
  assert.deepEqual(latestWeekEligibility([]), { weekId: null, eligible: false });
});
