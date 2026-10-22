/**
 * Tests for format.ts — written before the code.
 * Run from web/:  npm test
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { MISSING, finishNumber, fmtMoney, fmtOdds, fmtPct, fmtSigned } from "./format.ts";

const BAD = [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];

test("fmtSigned: sign, decimals, and no sign on zero", () => {
  assert.equal(fmtSigned(0.3443), "+0.34");
  assert.equal(fmtSigned(-1.2), "-1.20");
  assert.equal(fmtSigned(1.277, 3), "+1.277");
  assert.equal(fmtSigned(0.5, 0), "+1");        // toFixed rounds half away from zero here
  for (const z of [0, 0.004, -0.004]) assert.equal(fmtSigned(z), "0.00", String(z));
  for (const b of BAD) assert.equal(fmtSigned(b), MISSING);
});

test("fmtPct: a fraction as a percent", () => {
  assert.equal(fmtPct(0.0605), "6.0%");        // 6.05 isn't exact in binary: toFixed gives 6.0, as This Week shows
  assert.equal(fmtPct(0.3377, 0), "34%");
  assert.equal(fmtPct(1), "100.0%");
  assert.equal(fmtPct(0), "0.0%");              // a real 0% chance prints
  assert.equal(fmtPct(-0.0001), "0.0%");       // rounds to zero: no "-0.0%"
  for (const b of BAD) assert.equal(fmtPct(b), MISSING);
});

test("fmtOdds: American odds", () => {
  assert.equal(fmtOdds(1215), "+1215");
  assert.equal(fmtOdds(1214.6), "+1215");
  assert.equal(fmtOdds(-150), "-150");
  assert.equal(fmtOdds(0), MISSING);
  for (const b of BAD) assert.equal(fmtOdds(b), MISSING);
});

test("fmtMoney: whole dollars from a number or text", () => {
  assert.equal(fmtMoney(1440000), "$1,440,000");
  assert.equal(fmtMoney(534000.4), "$534,000");
  assert.equal(fmtMoney("$1,440,000"), "$1,440,000");
  assert.equal(fmtMoney("1440000"), "$1,440,000");
  assert.equal(fmtMoney(0), "$0");               // a missed cut earns $0: a fact
  assert.equal(fmtMoney("n/a"), MISSING);
  assert.equal(fmtMoney(""), MISSING);
  for (const b of BAD) assert.equal(fmtMoney(b), MISSING);
});

test("finishNumber: ties included, everything else null", () => {
  assert.equal(finishNumber("1"), 1);
  assert.equal(finishNumber("T5"), 5);
  assert.equal(finishNumber("t12"), 12);
  assert.equal(finishNumber(" T5 "), 5);
  for (const x of ["CUT", "WD", "DQ", "MDF", "", "T", null, undefined]) assert.equal(finishNumber(x), null, String(x));
});
