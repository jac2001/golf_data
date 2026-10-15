/**
 * Tests for installPrompt.ts — written before the code.
 * Run from web/:  npm test
 *
 * These pin the facts (iPhone can't push until installed, never before a
 * first pick, never nag after "denied"). Your decisions (a)–(c) are left
 * open: where a test accepts two answers, either is fine.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { CARD_COPY, SNOOZE_DAYS, cardStep } from "./installPrompt.ts";
import type { DeviceState } from "./installPrompt.ts";

const NOW = new Date("2026-10-15T12:00:00Z");
const MIN = 60_000;
const DAY = 24 * 60 * MIN;

const iphoneTab = (over: Partial<DeviceState> = {}): DeviceState => ({
  platform: "ios",
  installed: false,
  canPromptInstall: false,
  notifications: "unsupported",
  subscribed: false,
  hasPicked: true,
  dismissCount: 0,
  lastDismissedAt: null,
  ...over,
});

const android = (over: Partial<DeviceState> = {}): DeviceState => ({
  platform: "android",
  installed: false,
  canPromptInstall: true,
  notifications: "default",
  subscribed: false,
  hasPicked: true,
  dismissCount: 0,
  lastDismissedAt: null,
  ...over,
});

// ── never too early ──────────────────────────────────────────────────────────

test("no pick yet → nothing, on any platform", () => {
  assert.equal(cardStep(iphoneTab({ hasPicked: false }), NOW), "none");
  assert.equal(cardStep(android({ hasPicked: false }), NOW), "none");
});

// ── iPhone ───────────────────────────────────────────────────────────────────

test("iPhone in a Safari tab after a pick → the Add to Home Screen steps", () => {
  assert.equal(cardStep(iphoneTab(), NOW), "install_ios");
});

test("iPhone installed, permission not asked yet → ask for reminders", () => {
  assert.equal(cardStep(iphoneTab({ installed: true, notifications: "default" }), NOW), "ask_reminders");
});

test("iPhone tab never asks for reminders (push can't work there)", () => {
  for (const n of ["default", "unsupported"] as const) {
    assert.notEqual(cardStep(iphoneTab({ notifications: n }), NOW), "ask_reminders", n);
  }
});

// ── done or refused ──────────────────────────────────────────────────────────

test("already subscribed → nothing left to ask", () => {
  assert.equal(cardStep(iphoneTab({ installed: true, notifications: "granted", subscribed: true }), NOW), "none");
  assert.equal(cardStep(android({ installed: true, notifications: "granted", subscribed: true }), NOW), "none");
});

test("notifications denied → never ask for reminders", () => {
  assert.notEqual(cardStep(iphoneTab({ installed: true, notifications: "denied" }), NOW), "ask_reminders");
  assert.notEqual(cardStep(android({ notifications: "denied", canPromptInstall: false }), NOW), "ask_reminders");
});

test("installed iPhone with reminders denied → nothing (nothing useful to offer)", () => {
  assert.equal(cardStep(iphoneTab({ installed: true, notifications: "denied" }), NOW), "none");
});

// ── Android / desktop ────────────────────────────────────────────────────────

test("Android after a pick → install or reminders (your call, decision a)", () => {
  const got = cardStep(android(), NOW);
  assert.ok(got === "install_prompt" || got === "ask_reminders", got);
});

test("Android without an install prompt → reminders, never install_prompt", () => {
  assert.equal(cardStep(android({ canPromptInstall: false }), NOW), "ask_reminders");
});

test("desktop installed, permission not asked → reminders", () => {
  assert.equal(cardStep(android({ platform: "desktop", installed: true, canPromptInstall: false }), NOW), "ask_reminders");
});

test("never offer the iPhone steps off an iPhone", () => {
  for (const platform of ["android", "desktop"] as const) {
    assert.notEqual(cardStep(android({ platform, canPromptInstall: false }), NOW), "install_ios");
  }
});

// ── snoozing (decision b): only the part every sensible rule agrees on ────────

test("dismissed a minute ago → hidden", () => {
  const s = iphoneTab({ dismissCount: 1, lastDismissedAt: new Date(NOW.getTime() - MIN) });
  assert.equal(cardStep(s, NOW), "none");
});

test("dismissed many times, long ago → still hidden (stop asking eventually)", () => {
  const s = iphoneTab({ dismissCount: 5, lastDismissedAt: new Date("2025-01-01T00:00:00Z") });
  assert.equal(cardStep(s, NOW), "none");
});

// ── copy ─────────────────────────────────────────────────────────────────────

test("the iPhone card names both real steps", () => {
  const b = CARD_COPY.install_ios.body;
  assert.ok(b.includes("Share") && b.includes("Add to Home Screen"), b);
});

// TODO(Jack): add a test for your snooze rule: the boundary. One dismissal,
// exactly N days ago → shown again (or still hidden, whichever your rule says).
test("one dismissal, exactly SNOOZE_DAYS ago → the card is back", () => {
  const s = iphoneTab({ dismissCount: 1, lastDismissedAt: new Date(NOW.getTime() - SNOOZE_DAYS * DAY) });
  assert.equal(cardStep(s, NOW), "install_ios");
});