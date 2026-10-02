/** Order-insensitive golfer key: "Scheffler, Scottie" and "Scottie
 *  Scheffler" both become "scheffler scottie". Every join between a
 *  pick and a results/prediction row goes through this — raw-string
 *  joins fail silently and price a real pick at $0. */
export const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");

/** A golfer's surname from either spelling ("Scheffler, Scottie" or
 *  "Scottie Scheffler" → "Scheffler"). */
export const surname = (n: string) =>
  n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);

/**
 * TODO(Jack): compact display names for a list of golfers shown together.
 *
 * Today every compact lineup shows bare surnames, so the model's
 * "MacIntyre, Fitzpatrick, Fitzpatrick" doesn't say which Fitzpatrick.
 * Return one display name per input, in the same order:
 *   - a surname that appears ONCE in the list → just the surname
 *       "Scottie Scheffler"            → "Scheffler"
 *   - a surname shared by 2+ golfers → first initial + surname
 *       "Matt Fitzpatrick", "Alex Fitzpatrick" → "M. Fitzpatrick", "A. Fitzpatrick"
 * Names arrive in either order ("Fitzpatrick, Matt" or "Matt Fitzpatrick").
 *
 * Think about:
 *   - You need to know how often each surname occurs BEFORE you can
 *     decide how to display any one name — that's two passes, and a
 *     Map<string, number> is the natural counter.
 *   - Count case-insensitively ("Fitzpatrick" vs "fitzpatrick").
 *   - Getting the first name: for "Last, First" it's after the comma;
 *     for "First Last" it's the first word.
 */
export function displaySurnames(names: string[]): string[] {
  // Pass 1 — count each surname, case-insensitively (the KEY is lowercase).
  const counts = new Map<string, number>();
  for (const n of names) {
    const key = surname(n).toLowerCase();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  // Pass 2 — look up by the same lowercase key, but DISPLAY the original
  // capitalization; only a shared surname gets the first initial.
  return names.map((n) => {
    const display = surname(n);
    if (counts.get(display.toLowerCase()) === 1) return display;
    const first = n.includes(",") ? n.split(",")[1].trim() : n.trim().split(/\s+/)[0];
    return `${first.charAt(0)}. ${display}`;
  });
}
