/**
 * Tests for bottomNav.ts — written before the code.
 * Run from web/:  npm test
 *
 * These pin the facts. Your decisions (a)–(c) are left open.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { MORE_LINKS, TABS, activeTab } from "./bottomNav.ts";

// ── the four tabs ────────────────────────────────────────────────────────────

test("exactly / is Home", () => {
  assert.equal(activeTab("/"), "home");
});

test("Home doesn't light up on every page (every path starts with /)", () => {
  for (const p of ["/friends", "/match", "/predictions", "/settings"]) {
    assert.notEqual(activeTab(p), "home", p);
  }
});

test("/friends and below → Play", () => {
  assert.equal(activeTab("/friends"), "play");
  assert.equal(activeTab("/friends/anything"), "play");
});

test("/match and below → Matchup", () => {
  assert.equal(activeTab("/match"), "matchup");
  assert.equal(activeTab("/match/R2026554"), "matchup");
});

test("a lookalike path is NOT inside a section (/matchups isn't /match)", () => {
  assert.notEqual(activeTab("/matchups"), "matchup");
  assert.notEqual(activeTab("/friendship"), "play");
});

test("every More page lights More, and so do pages under it", () => {
  for (const { href } of MORE_LINKS) {
    assert.equal(activeTab(href), "more", href);
    assert.equal(activeTab(`${href}/x`), "more", `${href}/x`);
  }
});

// ── open decisions: only what every sensible answer agrees on ────────────────

test("an invite link never pretends to be Matchup or Home", () => {
  const got = activeTab("/join/abc123");
  assert.ok(got === null || got === "more" || got === "play", String(got));
});

test("legacy league pages light Play, More, or nothing — never Home/Matchup", () => {
  for (const p of ["/fantasy", "/mypicks", "/history/league"]) {
    const got = activeTab(p);
    assert.ok(got === null || got === "play" || got === "more", `${p}: ${got}`);
  }
});

// ── the data itself ──────────────────────────────────────────────────────────

test("four tabs, only More without a link", () => {
  assert.equal(TABS.length, 4);
  assert.deepEqual(TABS.filter(t => t.href === null).map(t => t.tab), ["more"]);
});

test("the More sheet doesn't repeat a tab", () => {
  const tabHrefs = new Set(TABS.map(t => t.href));
  for (const { href } of MORE_LINKS) assert.ok(!tabHrefs.has(href), href);
});

// TODO(Jack): one test for your decision (a) or (b), e.g. what /mypicks
// or /join/abc123 returns, with the reason in the test's name.

test("legacy league pages and invite links don't light up Home or Matchup", () => {
  for (const p of ["/fantasy", "/mypicks", "/history/league", "/join/abc123"]) {
    const got = activeTab(p);
    assert.ok(got === null || got === "play" || got === "more", `${p}: ${got}`);
  }
});
