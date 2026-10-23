/**
 * roundContext.ts — what matters for a Round Game pick once play has started.
 * ===========================================================================
 * The Round 2 picker listed the field by PRE-tournament win chance (Conners
 * 6.3% while he led at -8 and his live chance was 12%). A one-round pick
 * wants where each golfer stands and when he tees off. This joins the live
 * board and the next round's tee sheet onto the field, by name.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

import { finishNumber } from "./format.ts";
import { nameKey } from "./names.ts";

export type LiveRow = { player_name: string; position: string | null; total: string | null };
export type TeeGroup = { tee_time: string; players: { name: string; start_tee: number | null }[] };

export type RoundContext = {
  position: string | null;   // "T2", "CUT", null
  toPar: string | null;      // "-8", "E", "+3"
  teeTime: string | null;    // "7:35 AM" (the course's local time, as the tee sheet gives it)
  startTee: number | null;   // 1 or 10
};

/** name key -> context, for golfers on either source. Missing sources are fine. */
export function roundContext(
  live: readonly LiveRow[] | null | undefined,
  tees: readonly TeeGroup[] | null | undefined,
): Map<string, RoundContext> {
  const out = new Map<string, RoundContext>();
  const get = (name: string) => {
    const k = nameKey(name);
    let c = out.get(k);
    if (!c) { c = { position: null, toPar: null, teeTime: null, startTee: null }; out.set(k, c); }
    return c;
  };
  for (const r of live ?? []) {
    if (!r.player_name) continue;
    const c = get(r.player_name);
    c.position = r.position?.trim() || null;
    c.toPar = r.total?.trim() || null;
  }
  for (const g of tees ?? []) {
    for (const p of g.players ?? []) {
      if (!p.name) continue;
      const c = get(p.name);
      c.teeTime = g.tee_time?.trim() || null;
      c.startTee = p.start_tee ?? null;
    }
  }
  return out;
}

/** One line for the picker: "T2 · -8 · tees 7:35 AM, No. 10". null when nothing is known. */
export function contextLine(c: RoundContext | undefined): string | null {
  if (!c) return null;
  const parts: string[] = [];
  if (c.position) parts.push(c.position);
  if (c.toPar) parts.push(c.toPar);
  if (c.teeTime) parts.push(`tees ${c.teeTime}${c.startTee === 10 ? ", No. 10" : ""}`);
  return parts.length ? parts.join(" · ") : null;
}

/** Sort for the picker: best position first (ties count: T2 = 2), then golfers
 *  with no position (CUT, WD, not on the board) in their original order. */
export function byPosition(ctx: Map<string, RoundContext>) {
  return (a: { player_name: string }, b: { player_name: string }): number => {
    const pa = finishNumber(ctx.get(nameKey(a.player_name))?.position);
    const pb = finishNumber(ctx.get(nameKey(b.player_name))?.position);
    if (pa == null && pb == null) return 0;
    if (pa == null) return 1;
    if (pb == null) return -1;
    return pa - pb;
  };
}
