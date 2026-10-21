/**
 * Tests for consider.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { considerHref, resolveConsider } from "./consider.ts";

// TODO(Jack): delete this flag once resolveConsider passes. Until then the
// tests run and report, but don't fail `npm test` (so the hook doesn't block
// other edits).
const TODO = { todo: "Jack: implement resolveConsider" };

const FIELD = ["Scottie Scheffler", "Ludvig Åberg", "Rasmus Højgaard", "Nicolai Højgaard", "J.T. Poston"];

test("the field's own spelling comes back", TODO, () => {
  assert.equal(resolveConsider("Scottie Scheffler", FIELD), "Scottie Scheffler");
  assert.equal(resolveConsider("Aberg, Ludvig", FIELD), "Ludvig Åberg");
  assert.equal(resolveConsider("rasmus hojgaard", FIELD), "Rasmus Højgaard");
  assert.equal(resolveConsider("JT Poston", FIELD), "J.T. Poston");
});

test("surrounding whitespace doesn't matter", TODO, () => {
  assert.equal(resolveConsider("  Scottie Scheffler ", FIELD), "Scottie Scheffler");
});

test("not in this field is null", TODO, () => {
  assert.equal(resolveConsider("Rory McIlroy", FIELD), null);
  assert.equal(resolveConsider("Højgaard", FIELD), null);   // a surname alone is two golfers here
});

test("never a guess when two field names share a key", TODO, () => {
  assert.equal(resolveConsider("Zach Johnson", ["Zach Johnson", "Johnson, Zach", "Scottie Scheffler"]), null);
});

test("empty, missing and junk are null", TODO, () => {
  assert.equal(resolveConsider(null, FIELD), null);
  assert.equal(resolveConsider(undefined, FIELD), null);
  assert.equal(resolveConsider("", FIELD), null);
  assert.equal(resolveConsider("   ", FIELD), null);
  assert.equal(resolveConsider("Scottie Scheffler".padEnd(81, "x"), FIELD), null);
  assert.equal(resolveConsider("Scottie Scheffler", []), null);
});

test("considerHref round-trips through the URL", TODO, () => {
  const href = considerHref("Ludvig Åberg", "r2026528");
  const q = new URL(href, "https://playgolfedge.com").searchParams;
  assert.equal(q.get("game"), "ride");
  assert.equal(q.get("tid"), "R2026528");
  assert.equal(resolveConsider(q.get("consider"), FIELD), "Ludvig Åberg");
});
