/**
 * Match Center wording — imports the real lib/matchTypes.ts (no copy).
 * Jack's tie-for-first cases moved here from __scratch__, plus the
 * solo-vs-model card lines.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { slateHeadline, matchHeadline, totalsLine, moneyNote, golferProgress } from "./matchTypes.ts";
import type { Slate, Line, Golfer } from "./matchTypes.ts";

const line = (user_id: string, rank: number, total: number, user_name = user_id): Line =>
  ({ user_id, user_name, rank, total, golfers: [] });
const slate = (lines: Line[], over: Partial<Slate> = {}): Slate => ({
  tournament_id: "R2026554", name: "Bank of Utah", tour: "pga", status: "live", projected: true,
  lines, me_id: "me", rival: null, gap: 0, story: "", beating_model: null,
  humans: lines.filter(l => l.user_id !== "model").length, ...over,
});

test("group tie for first → tied for the lead (Jack)", () => {
  const s = slate([line("me", 1, 900_000), line("sam", 1, 900_000, "Sam"), line("model", 3, 1)]);
  assert.equal(slateHeadline(s), "You're tied for the lead with Sam.");
});

test("group final tie → shared the week (Jack)", () => {
  const s = slate([line("me", 1, 900_000), line("sam", 1, 900_000, "Sam")], { status: "final" });
  assert.equal(slateHeadline(s), "You shared the week with Sam.");
});

test("solo ahead of the model names the gap", () => {
  const s = slate([line("me", 1, 248_318), line("model", 2, 134_433, "The Model")]);
  assert.equal(matchHeadline(s), "You're ahead of the model by $113,885.");
  assert.equal(totalsLine(s), "You $248,318 · Model $134,433");
});

test("solo behind, final", () => {
  const s = slate([line("model", 1, 300_000, "The Model"), line("me", 2, 200_000)], { status: "final" });
  assert.equal(matchHeadline(s), "The model beat you by $100,000.");
});

test("group keeps the rank headline", () => {
  const s = slate([line("sam", 1, 500_000, "Sam"), line("me", 2, 300_000), line("model", 3, 100_000)],
    { rival: { user_id: "sam", user_name: "Sam", total: 500_000 }, gap: 200_000 });
  assert.equal(matchHeadline(s), "You're 2nd. Sam leads you by $200,000.");
  assert.equal(totalsLine(s), "You $300,000 · Sam $500,000");
});

test("money note never says just 'projected'", () => {
  assert.equal(moneyNote(slate([])), "Estimated payouts if the tournament ended now.");
  assert.equal(moneyNote(slate([], { status: "final" })), "Final prize money.");
});

test("golfer progress", () => {
  const g = (thru: string, to_par: number | null, round: number | null): Golfer =>
    ({ name: "x", position: "T10", earnings: 0, up_one: 0, thru, to_par, round });
  assert.equal(golferProgress(g("12", -6, 2), "live"), "−6 · Thru 12");
  assert.equal(golferProgress(g("F", 0, 3), "live"), "E · Round 3 done");
  assert.equal(golferProgress(g("0", 2, 3), "live"), "+2 · Not started");
  assert.equal(golferProgress(g("F", -11, 4), "final"), "−11");
});

// ── College card ────────────────────────────────────────────────────────
import { collegeHeadline, collegeTotals } from "./matchTypes.ts";
import type { College, CollegeLine } from "./matchTypes.ts";

const school = (user_id: string, school: string, rank: number, total: number, user_name = user_id): CollegeLine =>
  ({ user_id, user_name, school, rank, total, counting: [] });
const college = (lines: CollegeLine[], status: Slate["status"] = "live"): NonNullable<College> =>
  ({ tournament_id: "R2026554", name: "Bank of Utah", status, projected: true, lines, me_id: "me", story: "" });

test("college: leading alone", () => {
  const c = college([school("me", "Stanford", 1, 412_000), school("model", "Texas", 2, 389_500, "The Model")]);
  assert.equal(collegeHeadline(c), "Stanford leads Texas by $22,500.");
  assert.equal(collegeTotals(c), "Stanford $412,000 · Texas $389,500");
});

test("college: trailing names the leader and its owner", () => {
  const c = college([school("sam", "Texas", 1, 500_000, "Sam"), school("me", "Stanford", 2, 300_000)]);
  assert.equal(collegeHeadline(c), "Stanford is 2nd. Texas (Sam) leads by $200,000.");
});

test("college: tied for first with the model, final", () => {
  const c = college([school("me", "Stanford", 1, 400_000), school("model", "Texas", 1, 400_000, "The Model")], "final");
  assert.equal(collegeHeadline(c), "Stanford shared the school race with Texas (the model).");
});
