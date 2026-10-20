/**
 * Tests for scorecard.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { scorecard } from "./scorecard.ts";
import type { EventRow, Membership } from "./scorecard.ts";

const EVENTS = ["R2026528", "R2026540", "R2026457"];   // pilot events, date order
let t = 0;
const at = () => new Date(Date.UTC(2026, 9, 20) + (t++) * 60_000).toISOString();
const e = (user_id: string, event: string, props: Record<string, unknown> = {}, group_id: number | null = null): EventRow =>
  ({ user_id, event, props, group_id, created_at: at() });
const pick = (u: string, tid: string, game = "let_it_ride") => e(u, "pick_made", { game, tournament_id: tid });

// Group 1: Ann, Ben, Cal. Group 2: Dee, Eve. Jack (admin) is in group 1.
const MEMBERS: Membership[] = [
  { group_id: 1, user_id: "ann" }, { group_id: 1, user_id: "ben" }, { group_id: 1, user_id: "cal" },
  { group_id: 1, user_id: "jack" }, { group_id: 2, user_id: "dee" }, { group_id: 2, user_id: "eve" },
];

function rows(): EventRow[] {
  t = 0;
  return [
    e("ben", "joined_group", { source: "link" }, 1), e("cal", "joined_group", { source: "link" }, 1),
    e("eve", "joined_group", { source: "code" }, 2),
    // Event 1: ann, ben, cal, dee, eve, jack pick; the model too
    pick("ann", EVENTS[0]), pick("ben", EVENTS[0]), pick("cal", EVENTS[0]), pick("dee", EVENTS[0]),
    pick("eve", EVENTS[0]), pick("jack", EVENTS[0]), pick("model", EVENTS[0]),
    // Event 2: ann, ben, dee (eve dropped off)
    pick("ann", EVENTS[1]), pick("ben", EVENTS[1]), pick("dee", EVENTS[1]),
    // Event 3: ann, ben
    pick("ann", EVENTS[2]), pick("ben", EVENTS[2]),
    // Match Center during play: ann, dee; cal only looked at the final board
    e("ann", "match_viewed", { status: "live" }, 1), e("dee", "match_viewed", { status: "live,final" }, 2),
    e("cal", "match_viewed", { status: "final" }, 1),
    // Shares: ann twice, dee once, jack (admin, excluded) once
    e("ann", "invite_shared", { via: "share" }, 1), e("ann", "nudge_shared", { via: "copy" }, 1),
    e("dee", "invite_shared", { via: "copy" }, 2), e("jack", "invite_shared", { via: "share" }, 1),
  ];
}

test("1: joined, then picked (ben, cal, eve all picked after joining)", () => {
  assert.deepEqual(scorecard(rows(), MEMBERS, EVENTS, ["jack"]).invitedWhoPicked, { n: 3, of: 3 });
});

test("1: a pick BEFORE joining doesn't count as 'after they joined'", () => {
  t = 0;
  const r = [pick("zed", EVENTS[0]), e("zed", "joined_group", { source: "link" }, 1)];
  assert.deepEqual(scorecard(r, [...MEMBERS, { group_id: 1, user_id: "zed" }], EVENTS, []).invitedWhoPicked, { n: 0, of: 1 });
});

test("2: picked again in a later event (ann, ben, dee of the 6 real players)", () => {
  assert.deepEqual(scorecard(rows(), MEMBERS, EVENTS, ["jack"]).pickedAgain, { n: 3, of: 5 });
});

test("2: 'later' follows the events list, not tournament-id order", () => {
  t = 0;
  // R2026457 sorts first by id but is the LAST pilot event.
  const r = [pick("ann", "R2026457"), pick("ann", "R2026528")];
  assert.deepEqual(scorecard(r, MEMBERS, EVENTS, []).pickedAgain, { n: 1, of: 1 });
});

test("3: only group 1 kept 2+ active players in every event (with MIN_ACTIVE = 2)", () => {
  const s = scorecard(rows(), MEMBERS, EVENTS, ["jack"]).steadyGroups;
  assert.equal(s.of, 2);
  assert.ok(s.n === 1 || s.n === 0, `n=${s.n}: 1 with MIN_ACTIVE 2, 0 with MIN_ACTIVE 3`);
});

test("4: Match Center during play (ann, dee) of those who picked", () => {
  const s = scorecard(rows(), MEMBERS, EVENTS, ["jack"]).checkedMatchCenter;
  assert.equal(s.of, 5);
  assert.ok(s.n === 2 || s.n === 3, `n=${s.n}: 2 live-only, 3 counting cal's final-board look`);
});

test("5: shares by real players (3 shares by ann and dee; jack excluded)", () => {
  assert.deepEqual(scorecard(rows(), MEMBERS, EVENTS, ["jack"]).invitesShared, { n: 3, of: 2 });
});

test("the model and excluded admins never count", () => {
  const s = scorecard(rows(), MEMBERS, EVENTS, ["jack"]);
  assert.equal(s.pickedAgain.of, 5);   // ann ben cal dee eve, not jack or model
});

test("same rows in any order, same scorecard", () => {
  const r = rows();
  assert.deepEqual(scorecard([...r].reverse(), MEMBERS, EVENTS, ["jack"]), scorecard(r, MEMBERS, EVENTS, ["jack"]));
});

test("no rows → all zero, no crash", () => {
  const s = scorecard([], MEMBERS, EVENTS, []);
  for (const v of Object.values(s)) assert.deepEqual(v, { n: 0, of: 0 });
});

test("3: two active players in every event are enough for a steady group", () => {
  assert.deepEqual(scorecard(rows(), MEMBERS, EVENTS, ["jack"]).steadyGroups, { n: 1, of: 2 });
});
