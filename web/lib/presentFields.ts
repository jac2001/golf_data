/**
 * presentFields.ts — show only the fields that have a value.
 * ===========================================================
 * The PGA TOUR betting profile came back with ranks, accuracy, GIR, FedEx,
 * summary and bullets all empty, and the card printed a wall of "—";
 * career earnings are blank for every 2026 event (Players audit #11, #15).
 * These two helpers let a view render only what's really there.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

export type FieldSpec<T> = {
  key: keyof T;
  label: string;
  /** How to print the value; default String(value). */
  format?: (value: never) => string;
};

export type Shown = { label: string; text: string };

// ── presentFields + hasAny (Jack, Oct 22) ────────────────────────────────────────
//
// presentFields(row, spec): one { label, text } per spec entry whose value is
// real, in spec order. Not real: null, undefined, NaN, Infinity, "" or only
// whitespace, an empty array. Real: everything else, INCLUDING 0 and false
// (0 wins is a fact; deciding a 0 is a placeholder is the API's job).
// No row at all -> [].
//
// hasAny(rows, key): does at least one row have a real value at `key`?
// (Same rule.) For hiding a whole table column, e.g. Earnings.
//
// Hint: write one isReal(value) and use it in both.
function isReal(value: unknown): boolean {
    if (value == null) return false;                                          // null and undefined
    if (typeof value === "number" && !Number.isFinite(value)) return false;   // NaN, Infinity (but 0 is real)
    if (typeof value === "string" && value.trim() === "") return false;       // "" and "  "
    if (Array.isArray(value) && value.length === 0) return false;             // []
    return true;                                                              // everything else, incl. 0 and false
    

  }
export function presentFields<T>(row: T | null | undefined, spec: readonly FieldSpec<T>[]): Shown[] {
  if (row == null) return [];               // no row at all -> nothing to show

  const out: Shown[] = [];                  // 1. an empty list to fill
  for (const entry of spec) {               // 2. walk the spec in display order
    const value = row[entry.key];           // 3. look up this field's value
    if (!isReal(value)) continue;           // 4. skip missing values
    const text = entry.format
      ? entry.format(value as never)        // 5a. the entry's own formatter...
      : String(value);                      // 5b. ...or plain text
    out.push({ label: entry.label, text }); // 6. keep it
  }
  return out;                               // 7. hand back the list
}



export function hasAny<T>(rows: readonly T[] | null | undefined, key: keyof T): boolean {
  return (rows ?? []).some(row => isReal(row[key]));
}
