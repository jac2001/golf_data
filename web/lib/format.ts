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

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);

}


export function fmtSigned(v: number | null | undefined, dp = 2): string {
  if (!isNum(v)) return MISSING;
  const text = v.toFixed(dp);
  const rounded = Number(text);
  if (rounded === 0) return (0).toFixed(dp);
  return rounded > 0 ? `+${text}` : text;
}

export function fmtPct(v: number | null | undefined, dp = 1): string {
  if (!isNum(v)) return MISSING;

return `${(v * 100).toFixed(dp)}%`;
}

export function fmtOdds(v: number | null | undefined): string {
  if (!isNum(v)) return MISSING;
  const rounded = Math.round(v);
  if (rounded === 0) return MISSING;
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

export function fmtMoney(v: number | string | null | undefined): string {
  if (v == null) return MISSING;

  let amount: number;

  if (typeof v === "string") {
    const text = v.trim();

    if (!/^\$?-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text)) {
      return MISSING;
    }

    amount = Number(text.replace(/[$,]/g, ""));
  } else {
    amount = v;
  }

  if (!isNum(amount)) return MISSING;

  return amount.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export function finishNumber(pos: string | null | undefined): number | null {
  const text = pos?.trim();

if (!text) return null;

const match = /^T?([1-9]\d*)$/i.exec(text);

if (!match) return null;

const finish = Number(match[1]);

return Number.isSafeInteger(finish) ? finish : null;
}
