/**
 * advice.ts — spend or save, for one member's Let It Ride slate.
 * ==============================================================
 * Render computes what every golfer in this week's field is worth now
 * and at each upcoming event (/api/advice/values — the same for
 * everyone). This file applies ONE member's uses left to those values.
 * Pure functions, no imports from "@/", so `npm test` runs them directly.
 *
 * The model plays by the same function: model-sync calls adviseSlate()
 * for the model member, so its picks come with reasons.
 *
 * Design: docs/ADVICE_VIEW_DESIGN.md
 */

/** One upcoming event's value for a golfer (from Render). */
export type FutureWindow = { tid: string; name: string; start_date: string; purse: number; ev: number };

/** One golfer in this week's field, as Render values him. */
export type GolferValue = {
  player_name: string;
  key: string;              // nameKey(player_name) — how uses are looked up
  now_ev: number;           // expected prize money THIS week
  future: FutureWindow[];   // upcoming events on this tour, any order
  allWindows?: number;      // windows before contestedFutures filtered them (set by adviseSlate)
};

export type Verdict = {
  verdict: "spend" | "save" | "spent";
  score: number;            // ranks golfers for the slate: higher = better use of a pick now
  saveFor?: FutureWindow;   // the window that makes saving worth it (verdict "save")
  reason: string;           // one line a member reads
};

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v / 1000)}K`;

/**
 * TODO(Jack): decide spend / save / spent for ONE golfer.
 *
 * `left` = how many uses this member still has on him.
 * `future` = only the windows he'd realistically get a slot at
 *            (adviseSlate filters out contested ones before calling you).
 *
 * The rule from the design doc:
 *   - left 0 → "spent" (score -Infinity so he never fills a slate).
 *   - Sort his future EVs high → low: e1 ≥ e2 ≥ …
 *   - The use you GIVE UP by spending now is the left-th best window,
 *     e[left - 1] — with 3 uses and windows 900/700/400 you'd lose the
 *     400 one, not the 900 one. If he has fewer windows than uses left,
 *     spending now costs nothing ($0).
 *   - now_ev ≥ that window's EV → "spend", score = now_ev.
 *   - otherwise → "save", saveFor = that window,
 *                 score = now_ev − (window.ev − now_ev).
 *   - reason: one sentence with both numbers, e.g.
 *       "$410K now vs $1.20M at the Masters — save."
 *     Use the money() helper above.
 *
 * The tests in advice.test.ts spell out each case. Run `npm test`
 * from web/ and make them pass.
 */
export function golferVerdict(g: GolferValue, left: number): Verdict {
  left = Math.max(left, 0);
  const now = g.now_ev;
  const future = [...g.future].sort((a, b) => b.ev - a.ev);
  const cost = left > 0 && left <= future.length ? future[left - 1].ev : 0;
  if (left === 0) {
    return { verdict: "spent", score: -Infinity, reason: `${money(now)} now — spent.` };
  } else if (now >= cost) {
    const reason = cost === 0
      ? ((g.allWindows ?? 0) > g.future.length
          ? `${money(now)} now — no later event where he'd be a top pick — spend.`
          : `${money(now)} now, nothing better ahead — spend.`)
      : `${money(now)} now beats ${money(cost)} at ${future[left - 1].name} — spend.`;
    return { verdict: "spend", score: now, reason };
  } else {
    const saveFor = future[left - 1];
    return { verdict: "save", score: now - (cost - now), saveFor, reason: `${money(now)} now vs ${money(cost)} at ${saveFor.name} — save.` };
  }
}

/**
 * Capacity gate: only `slots` golfers can be picked per event, so a
 * golfer's future window only counts if he'd rank inside the top
 * `slots × 2` for that event across the field. (×2 leaves room for
 * members who'd pick him there even if he isn't a top-3 value.)
 * Without this, every decent golfer "saves for the Masters" and nobody
 * spends anyone.
 */
export function contestedFutures(field: GolferValue[], slots: number): Map<string, FutureWindow[]> {
  const byEvent = new Map<string, { key: string; ev: number }[]>();
  for (const g of field) {
    for (const w of g.future) {
      const list = byEvent.get(w.tid) ?? [];
      list.push({ key: g.key, ev: w.ev });
      byEvent.set(w.tid, list);
    }
  }
  const room = new Map<string, Set<string>>();
  for (const [tid, list] of byEvent) {
    room.set(tid, new Set(list.sort((a, b) => b.ev - a.ev).slice(0, slots * 2).map(x => x.key)));
  }
  const out = new Map<string, FutureWindow[]>();
  for (const g of field) out.set(g.key, g.future.filter(w => room.get(w.tid)?.has(g.key)));
  return out;
}

/**
 * The whole slate: every golfer's verdict, plus the best `slots` picks
 * (used by the model; members see verdicts only).
 */
export function adviseSlate(
  field: GolferValue[],
  usesLeft: Record<string, number>,
  usesPerPlayer: number,
  slots: number,
): { verdicts: Record<string, Verdict>; slate: string[] } {
  const futures = contestedFutures(field, slots);
  const verdicts: Record<string, Verdict> = {};
  for (const g of field) {
    verdicts[g.key] = golferVerdict({ ...g, future: futures.get(g.key) ?? [], allWindows: g.future.length }, usesLeft[g.key] ?? usesPerPlayer);
  }
  const slate = field
    .filter(g => verdicts[g.key].verdict !== "spent")
    .sort((a, b) => verdicts[b.key].score - verdicts[a.key].score)
    .slice(0, slots)
    .map(g => g.player_name);
  return { verdicts, slate };
}

export { money as adviceMoney };
