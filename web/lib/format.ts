/**
 * format.ts — one way to print a number on the Players page.
 * ============================================================
 * Players had a formatter per spot (fmt, fmtPct, fmtSg, fmtOdds, fmtMoney,
 * fmtH2H) and two copies of the color helpers. They disagreed: NaN printed
 * as "NaN", -0.004 as "-0.00", and a tied finish "T5" was never colored
 * because parseInt("T5") is NaN (Players audit #23). These replace them.
 *
 * Every function prints MISSING for null, undefined, NaN or Infinity.
 * Pure, no "@/" imports: `npm test` runs it.
 */

export const MISSING = "—";

// ── TODO(Jack): five small formatters ─────────────────────────────────────────
//
// fmtSigned(v, dp = 2)  -> "+0.34", "-1.20"; dp decimals.
//     Zero after rounding has NO sign: 0, 0.004 and -0.004 all -> "0.00".
//     (The -0 trap from holeSentence: decide the sign from the ROUNDED text.)
//
// fmtPct(v, dp = 1)     -> v is a fraction: 0.0605 -> "6.0%", 1 -> "100.0%".
//     (Use (v * 100).toFixed(dp): it must match This Week, which prints 6.0%.)
//
// fmtOdds(v)            -> American odds, whole number: 1215 -> "+1215",
//     -150 -> "-150", 1214.6 -> "+1215". 0 isn't valid American odds -> MISSING.
//
// fmtMoney(v)           -> number or text like "$1,440,000" / "1440000":
//     -> "$1,440,000" (whole dollars, US commas). Text that isn't a number
//     -> MISSING.
//
// finishNumber(pos)     -> the number in a finish position, ties included:
//     "1" -> 1, "T5" -> 5, "t12" -> 12, " T5 " -> 5. Anything else ("CUT",
//     "WD", "DQ", "", null) -> null. Used by the color helpers, so a tied
//     5th colors like a 5th.
//
// Hint: write one isNum(v): v is number (typeof + Number.isFinite) and reuse it.

export function fmtSigned(v: number | null | undefined, dp = 2): string {
  void v; void dp;
  throw new Error("TODO(Jack): fmtSigned");
}

export function fmtPct(v: number | null | undefined, dp = 1): string {
  void v; void dp;
  throw new Error("TODO(Jack): fmtPct");
}

export function fmtOdds(v: number | null | undefined): string {
  void v;
  throw new Error("TODO(Jack): fmtOdds");
}

export function fmtMoney(v: number | string | null | undefined): string {
  void v;
  throw new Error("TODO(Jack): fmtMoney");
}

export function finishNumber(pos: string | null | undefined): number | null {
  void pos;
  throw new Error("TODO(Jack): finishNumber");
}
