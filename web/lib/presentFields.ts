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

// ── TODO(Jack): presentFields + hasAny ────────────────────────────────────────
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

export function presentFields<T>(row: T | null | undefined, spec: readonly FieldSpec<T>[]): Shown[] {
  void row; void spec;
  throw new Error("TODO(Jack): presentFields");
}

export function hasAny<T>(rows: readonly T[] | null | undefined, key: keyof T): boolean {
  void rows; void key;
  throw new Error("TODO(Jack): hasAny");
}
