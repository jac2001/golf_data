import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyRecommendation } from "./recommendationState.ts";
import type { RecommendationContext, RecommendationTiming } from "./recommendationState.ts";

const now = Date.parse("2026-10-22T12:00:00Z");
const context: RecommendationContext = { eventId: "R2026528", nowMs: now, maxAgeMs: 15 * 60_000 };
// 15 minutes is just a fixture, NOT a recommendation for production policy.
const sample = (): RecommendationTiming => ({ eventId: context.eventId, marketId: "h2h_r1",
  generatedAtMs: now - 60_000, oddsAtMs: now - 120_000,
  startsAtMs: now + 60_000, marketState: "open" });
const check = (patch: Partial<RecommendationTiming>, kind: string, reason: string,
  ctx = context) => assert.deepEqual(classifyRecommendation({ ...sample(), ...patch }, ctx), { kind, reason });

test("recommendation: a verified fresh pre-start market is current", () => {
  check({}, "current", "verified");
});
test("recommendation: another event cannot be current", () => {
  check({ eventId: "R2026527" }, "archive", "wrong-event");
});
test("recommendation: closed stays closed even without timing", () => {
  check({ marketState: "closed", startsAtMs: null }, "archive", "closed");
});
test("recommendation: starts at equality, and a fresh file cannot revive R1", () => {
  check({ startsAtMs: now }, "archive", "started");
  check({ startsAtMs: now - 86_400_000, generatedAtMs: now }, "archive", "started");
});
test("recommendation: generation AND odds must be fresh; boundary allowed", () => {
  check({ generatedAtMs: now - context.maxAgeMs - 1, oddsAtMs: now - context.maxAgeMs - 2 }, "archive", "stale");
  check({ oddsAtMs: now - context.maxAgeMs - 1 }, "archive", "stale");
  check({ oddsAtMs: now - context.maxAgeMs }, "current", "verified");
});
test("recommendation: unknown identity/state/timing stays unavailable", () => {
  for (const patch of [ { eventId: null }, { eventId: " " }, { marketId: null },
    { marketId: "" }, { marketState: "unknown" as const }, { generatedAtMs: null },
    { oddsAtMs: null }, { startsAtMs: null }, { startsAtMs: NaN },
    { generatedAtMs: Infinity }, { oddsAtMs: NaN } ]) {
    check(patch, "unavailable", "unverified");
  }
});
test("recommendation: impossible timing is unavailable", () => {
  check({ generatedAtMs: now + 1 }, "unavailable", "unverified");
  check({ oddsAtMs: now + 1 }, "unavailable", "unverified");
  check({ oddsAtMs: now, generatedAtMs: now - 1 }, "unavailable", "unverified");
});
test("recommendation: invalid caller context is unavailable", () => {
  for (const patch of [{ eventId: "" }, { nowMs: NaN }, { maxAgeMs: 0 },
    { maxAgeMs: -1 }, { maxAgeMs: Infinity }]) {
    check({}, "unavailable", "unverified", { ...context, ...patch });
  }
});
test("recommendation: pure and deterministic", () => {
  const r = Object.freeze(sample());
  const c = Object.freeze({ ...context });
  assert.deepEqual(classifyRecommendation(r, c), { kind: "current", reason: "verified" });
  assert.deepEqual(classifyRecommendation(r, c), classifyRecommendation(r, c));
  assert.deepEqual(r, sample());
});
// TODO(Jack): add a test proving a started market with unknown state is archived,
// while an unstarted market with unknown state is unavailable.
