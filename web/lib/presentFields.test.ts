/**
 * Tests for presentFields.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { hasAny, presentFields, type FieldSpec } from "./presentFields.ts";

type BP = { sg_total: number | null; sg_total_rank: number | null; wins: number | null;
  gir_pct: string | null; summary: string | null; bullets: string[] };

// Ben James's PGA TOUR betting profile, Oct 22: most fields empty.
const BEN: BP = { sg_total: 1.504, sg_total_rank: null, wins: 0, gir_pct: null, summary: "  ", bullets: [] };
const SPEC: FieldSpec<BP>[] = [
  { key: "sg_total", label: "SG total", format: (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(2)}` },
  { key: "sg_total_rank", label: "Tour rank", format: (v: number) => `#${v}` },
  { key: "wins", label: "Wins" },
  { key: "gir_pct", label: "Greens in regulation" },
  { key: "summary", label: "Summary" },
  { key: "bullets", label: "Notes" },
];

test("only real values come back, in spec order, formatted", () => {
  assert.deepEqual(presentFields(BEN, SPEC), [
    { label: "SG total", text: "+1.50" },
    { label: "Wins", text: "0" },          // 0 wins is a fact, not missing
  ]);
});

test("NaN, Infinity, blank strings and empty arrays are missing", () => {
  type R = { a: number; b: number; c: string; d: string[]; e: boolean };
  const spec: FieldSpec<R>[] = [{ key: "a", label: "A" }, { key: "b", label: "B" }, { key: "c", label: "C" },
    { key: "d", label: "D" }, { key: "e", label: "E" }];
  assert.deepEqual(presentFields({ a: Number.NaN, b: Number.POSITIVE_INFINITY, c: "", d: [], e: false }, spec),
    [{ label: "E", text: "false" }]);
});

test("no row, no fields", () => {
  assert.deepEqual(presentFields(null, SPEC), []);
  assert.deepEqual(presentFields(undefined, SPEC), []);
});

test("hasAny: hide the Earnings column when every row is blank", () => {
  const recent = [{ earnings: null as number | null }, { earnings: null }, { earnings: null }];
  assert.equal(hasAny(recent, "earnings"), false);
  assert.equal(hasAny([...recent, { earnings: 0 }], "earnings"), true);
  assert.equal(hasAny([], "earnings"), false);
  assert.equal(hasAny(null, "earnings" as never), false);
});
