/** Order-insensitive golfer key: "Scheffler, Scottie" and "Scottie
 *  Scheffler" both become "scheffler scottie". Every join between a
 *  pick and a results/prediction row goes through this — raw-string
 *  joins fail silently and price a real pick at $0. */
export const nameKey = (n: string) =>
  n.toLowerCase().replace(",", "").split(/\s+/).filter(Boolean).sort().join(" ");
