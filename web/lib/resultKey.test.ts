/**
 * Tests for resultKey.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveResult, resultKey } from "./resultKey.ts";

const same = (a: string, b: string) => assert.equal(resultKey(a), resultKey(b), `${a} vs ${b}`);
const differ = (a: string, b: string) => assert.notEqual(resultKey(a), resultKey(b), `${a} vs ${b}`);

test("order and case don't matter", () => {
  same("Scheffler, Scottie", "Scottie Scheffler");
  same("SCOTTIE SCHEFFLER", "scottie scheffler");
});

test("accents fold, including letters that don't decompose", () => {
  same("Ludvig Åberg", "Ludvig Aberg");
  same("Åberg, Ludvig", "aberg ludvig");
  same("Nicolás Echavarría", "Nicolas Echavarria");
  same("Rasmus Højgaard", "Rasmus Hojgaard");
  same("Thorbjørn Olesen", "Thorbjorn Olesen");
});

test("punctuation: periods and apostrophes vanish, hyphens split", () => {
  same("J.T. Poston", "JT Poston");
  same("Sean O'Hair", "Sean OHair");
  same("Byeong-Hun An", "Byeong Hun An");
});

test("suffixes don't count", () => {
  same("Davis Love III", "Davis Love");
  same("Ted Potter, Jr.", "Potter, Ted");
  same("Love III, Davis", "Davis Love III");
});

test("different golfers stay different", () => {
  differ("Nicolai Højgaard", "Rasmus Højgaard");
  differ("Matt Fitzpatrick", "Alex Fitzpatrick");
  differ("Ludvig Åberg", "Ludvig Aberg Jr Smith");
});

test("empty names give an empty key", () => {
  assert.equal(resultKey(""), "");
  assert.equal(resultKey("   "), "");
});

// The audit's reproduction: the API sends "Ludvig Åberg" with $259,500 and
// the pick says "Ludvig Aberg" (no id: an older pick). It must find the
// money, not fall back to $0.
const TABLE = {
  "aberg ludvig": { player_name: "Ludvig Åberg", player_id: "52955", earnings: 259500 },
  "højgaard nicolai": { player_name: "Nicolai Højgaard", player_id: "52686", earnings: 100000 },
  "højgaard rasmus": { player_name: "Rasmus Højgaard", player_id: "52687", earnings: 50000 },
  "scheffler scottie": { player_name: "Scheffler, Scottie", player_id: "46046", earnings: 1800000 },
  // The two Zach Johnsons at the 2020 PGA Championship.
  "johnson zach": { player_name: "Zach Johnson", player_id: "24024", earnings: 30000 },
  "johnson zach#29747": { player_name: "Zach Johnson", player_id: "29747", earnings: 0 },
  "nameless": { player_name: null, player_id: null, earnings: 1 },
};

test("a name match finds the money across spellings (older picks, no id)", () => {
  const r = resolveResult(TABLE, { player_name: "Ludvig Aberg" });
  assert.equal(r.row?.earnings, 259500);
  assert.ok(r.row && r.via === "name");
  assert.equal(resolveResult(TABLE, { player_name: "Rasmus Hojgaard" }).row?.earnings, 50000);
  assert.equal(resolveResult(TABLE, { player_name: "Scottie Scheffler" }).row?.earnings, 1800000);
});

test("an id match wins, even when the names are spelled differently", () => {
  const r = resolveResult(TABLE, { player_name: "Ludwig Aaberg", player_id: "52955" });
  assert.equal(r.row?.earnings, 259500);
  assert.ok(r.row && r.via === "id");
});

test("ids pick the right golfer when two share a name", () => {
  assert.equal(resolveResult(TABLE, { player_name: "Zach Johnson", player_id: "24024" }).row?.earnings, 30000);
  assert.equal(resolveResult(TABLE, { player_name: "Zach Johnson", player_id: "29747" }).row?.earnings, 0);
});

test("a shared name with no id is ambiguous, never a guess", () => {
  assert.deepEqual(resolveResult(TABLE, { player_name: "Zach Johnson" }), { row: null, reason: "ambiguous" });
});

test("an id the table doesn't have falls back to the name", () => {
  // DataGolf's live board has no PGA ids.
  const live = { "aberg ludvig": { player_name: "Ludvig Åberg", earnings: 99 } };
  assert.equal(resolveResult(live, { player_name: "Ludvig Aberg", player_id: "52955" }).row?.earnings, 99);
});

test("ids compare as text, ignoring leading zeros", () => {
  const t = { "singh vijay": { player_name: "Vijay Singh", player_id: "6567", earnings: 5 } };
  assert.equal(resolveResult(t, { player_name: "V. Singh", player_id: "06567" }).row?.earnings, 5);
});

test("missing: no table, no match, or a nameless row", () => {
  assert.deepEqual(resolveResult(undefined, { player_name: "Ludvig Aberg" }), { row: null, reason: "missing" });
  assert.deepEqual(resolveResult(null, { player_name: "Ludvig Aberg" }), { row: null, reason: "missing" });
  assert.deepEqual(resolveResult(TABLE, { player_name: "Tiger Woods" }), { row: null, reason: "missing" });
  assert.deepEqual(resolveResult(TABLE, { player_name: "" }), { row: null, reason: "missing" });
});
