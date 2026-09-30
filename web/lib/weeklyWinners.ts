/**
 * Let It Ride weekly winners: each SETTLED slate crowns the member with
 * the most money on it (PGA and DPWT are separate slates, so a week can
 * crown two). Ties share the star. A slate where nobody earned anything
 * crowns nobody, and projected (in-progress) slates never crown — a
 * Saturday leader hasn't won anything yet.
 */
export type SlateResult = { user_id: string; tid: string; total: number; settled: boolean };

export function weeklyWinners(results: SlateResult[]): {
  winners: Record<string, string[]>;
  stars: Map<string, number>;
} {
  const best = new Map<string, { total: number; crowned: string[] }>();
  for (const r of results) {
    if (!r.settled) continue;
    const b = best.get(r.tid);
    if (!b || r.total > b.total) best.set(r.tid, { total: r.total, crowned: [r.user_id] });
    else if (r.total === b.total) b.crowned.push(r.user_id);
  }
  const winners: Record<string, string[]> = {};
  const stars = new Map<string, number>();
  for (const [tid, b] of best) {
    if (b.total <= 0) continue;
    winners[tid] = b.crowned;
    for (const uid of b.crowned) stars.set(uid, (stars.get(uid) ?? 0) + 1);
  }
  return { winners, stars };
}
