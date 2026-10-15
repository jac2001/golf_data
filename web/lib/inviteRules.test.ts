/**
 * Tests for inviteRules.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { INVITE_MAX_USES, inviteExpiry, inviteMessage, inviteStatus } from "./inviteRules.ts";
import type { InviteLink } from "./inviteRules.ts";

const NOW = new Date("2026-10-15T12:00:00Z");
const HOUR = 3600_000;
const DAY = 24 * HOUR;

const link = (over: Partial<InviteLink> = {}): InviteLink => ({
  expires_at: new Date(NOW.getTime() + 3 * DAY),
  max_uses: INVITE_MAX_USES,
  uses: 0,
  revoked_at: null,
  ...over,
});

// ── inviteExpiry ─────────────────────────────────────────────────────────────

test("a link lasts exactly 7 days", () => {
  assert.equal(inviteExpiry(NOW).getTime() - NOW.getTime(), 7 * DAY);
});

test("inviteExpiry doesn't change the date it's given", () => {
  const before = NOW.getTime();
  inviteExpiry(NOW);
  assert.equal(NOW.getTime(), before);
});

// ── inviteStatus: one condition at a time ────────────────────────────────────

test("fresh link, new person → ok", () => {
  assert.equal(inviteStatus(link(), NOW, false), "ok");
});

test("one second before expiry still works", () => {
  assert.equal(inviteStatus(link({ expires_at: new Date(NOW.getTime() + 1000) }), NOW, false), "ok");
});

test("AT the expiry instant → expired", () => {
  assert.equal(inviteStatus(link({ expires_at: NOW }), NOW, false), "expired");
});

test("19 of 20 used → the 20th person still gets in", () => {
  assert.equal(inviteStatus(link({ uses: INVITE_MAX_USES - 1 }), NOW, false), "ok");
});

test("20 of 20 used → used_up", () => {
  assert.equal(inviteStatus(link({ uses: INVITE_MAX_USES }), NOW, false), "used_up");
});

test("revoked → revoked", () => {
  assert.equal(inviteStatus(link({ revoked_at: new Date(NOW.getTime() - HOUR) }), NOW, false), "revoked");
});

test("already in the group → already_member", () => {
  assert.equal(inviteStatus(link(), NOW, true), "already_member");
});

// ── inviteMessage ────────────────────────────────────────────────────────────

const ALL = ["ok", "already_member", "revoked", "expired", "used_up"] as const;

test("every status gets a message that names the group", () => {
  for (const s of ALL) {
    const m = inviteMessage(s, "Riverside Golf");
    assert.ok(m.includes("Riverside Golf"), `${s}: "${m}"`);
  }
});

test("each problem status says what to do next (mentions a new link or the sender)", () => {
  for (const s of ["revoked", "expired", "used_up"] as const) {
    const m = inviteMessage(s, "Riverside Golf").toLowerCase();
    assert.ok(/new link|ask|sent/.test(m), `${s}: "${m}"`);
  }
});

test("no jargon: messages don't leak status codes", () => {
  for (const s of ALL) {
    const m = inviteMessage(s, "Riverside Golf");
    assert.ok(!/used_up|already_member|revoked_at|expires_at/.test(m), `${s}: "${m}"`);
  }
});

test("messages differ per status", () => {
  const msgs = new Set(ALL.map(s => inviteMessage(s, "G")));
  assert.equal(msgs.size, ALL.length);
});

// TODO(Jack): add a test for the precedence you chose in inviteStatus,
// e.g. a link that is BOTH expired and revoked, or an existing member
// opening an expired link.
