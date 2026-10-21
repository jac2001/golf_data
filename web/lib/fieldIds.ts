/**
 * fieldIds.ts: the PGA TOUR player_id for a golfer someone just picked.
 * ======================================================================
 * Picks store it (league_picks / fade_picks / round_picks.player_id, added
 * Oct 20, 2026) so scoring can match results by id first: two golfers can
 * share a name (web/lib/resultKey.ts resolveResult). Server-side only.
 *
 * Returns null, and the pick falls back to name matching, when:
 *   - the event is DP World Tour (no PGA ids),
 *   - the predictions response is for another event (provenance),
 *   - the name matches no one, or more than one golfer in the field.
 * A null never blocks a pick: the id improves scoring, it doesn't gate it.
 */
import { MODEL_API } from "@/lib/db";
import { resultKey } from "@/lib/resultKey";

type FieldRow = { player_name: string; player_id?: string | null };

export async function fieldPlayerId(tid: string, playerName: string): Promise<string | null> {
  const id = tid.trim().toUpperCase();
  if (!id.startsWith("R")) return null;
  try {
    const res = await fetch(`${MODEL_API}/api/predictions?limit=300&tournament_id=${encodeURIComponent(id)}`,
      { next: { revalidate: 300 } });
    if (!res.ok) return null;
    const d = await res.json();
    if (String(d.tournament_id ?? "").toUpperCase() !== id) return null;
    const key = resultKey(playerName);
    const hits = ((d.players ?? []) as FieldRow[]).filter(p => p.player_id && resultKey(p.player_name) === key);
    return hits.length === 1 ? String(hits[0].player_id) : null;
  } catch {
    return null;
  }
}
