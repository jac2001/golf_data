/** A learning scaffold: not connected to the live board yet.
 * Classifies PRE-START recommendations only. Live recommendations need a
 * separate contract; a newer timestamp must never resurrect a closed market.
 */
export type RecommendationTiming = {
  eventId: string | null;
  /** True identity of this recommendation's market, e.g. h2h_r1. */
  marketId: string | null;
  /** Timestamp provenance comes from the producer, never the page-load time. */
  generatedAtMs: number | null;
  oddsAtMs: number | null;
  /** Actual market cutoff (round/selection start), not fantasy-pick midnight. */
  startsAtMs: number | null;
  marketState: "open" | "closed" | "unknown";
};
export type RecommendationContext = {
  eventId: string;
  nowMs: number;
  /** Explicit product policy supplied by caller, not a magic constant here. */
  maxAgeMs: number;
};
export type RecommendationState =
  | { kind: "current"; reason: "verified" }
  | { kind: "archive"; reason: "wrong-event" | "closed" | "started" | "stale" }
  | { kind: "unavailable"; reason: "unverified" };

/**
 * TODO(Jack): classifyRecommendation. Worked solution is in
 * docs/AUDIT_FIXES_WORKBOOK.md. Read the tests first, then try these steps:
 *
 * 1. Missing/blank event IDs or invalid now/maxAge -> unavailable.
 *    maxAge must be > 0. Use Number.isFinite (NaN is still a number!).
 * 2. Different event IDs -> archive/wrong-event. Compare exact canonical IDs.
 * 3. Closed market -> archive/closed, even when timestamps are missing.
 * 4. Missing market ID or any invalid timestamp -> unavailable/unverified.
 * 5. now >= startsAt -> archive/started. Equality is closed, not one last chance.
 * 6. Unknown state, future generation/odds, or odds newer than generation ->
 *    unavailable. A saved recommendation must refer to the quote it used.
 * 7. If generation OR odds age > maxAge -> archive/stale (equal is allowed).
 * 8. Otherwise return current/verified.
 *
 * No Date.now(), network calls, mutation, scoring or model changes here.
 * Every input is explicit, so tests can simulate time without waiting.
 */
export function classifyRecommendation(
  recommendation: RecommendationTiming,
  context: RecommendationContext,
): RecommendationState {
  const { eventId, marketId, generatedAtMs, oddsAtMs, startsAtMs, marketState } = recommendation;
  const { nowMs, maxAgeMs } = context;
  // Validate context first: without it, we cannot compare events or time
  if (!eventId?.trim() || !context.eventId.trim() || !Number.isFinite(nowMs) || !Number.isFinite(maxAgeMs) || maxAgeMs <= 0) {
    return { kind: "unavailable", reason: "unverified", };
  }
  if (eventId !== context.eventId) {
    return { kind: "archive", reason: "wrong-event" };
  }
  // A definite closure is useful even if other metadata is absent.
  if (marketState === "closed") {
    return { kind: "archive", reason: "closed" };
  }
  if (!marketId?.trim() || generatedAtMs === null || oddsAtMs === null ||
      startsAtMs === null || !Number.isFinite(generatedAtMs) ||
      !Number.isFinite(oddsAtMs) || !Number.isFinite(startsAtMs)) {
    return { kind: "unavailable", reason: "unverified" };
  }
  // At the cutoff is already too late. Fresh output cannot reopen a market.
  if (nowMs >= startsAtMs) {
    return { kind: "archive", reason: "started" };
  }
  if (marketState !== "open" || generatedAtMs > nowMs || oddsAtMs > nowMs ||
      oddsAtMs > generatedAtMs) {
    return { kind: "unavailable", reason: "unverified" };
  }
  // Both the recommendation and the quote it used must be fresh.
  if (nowMs - generatedAtMs > maxAgeMs || nowMs - oddsAtMs > maxAgeMs) {
    return { kind: "archive", reason: "stale" };
  }
  return { kind: "current", reason: "verified" };
}
