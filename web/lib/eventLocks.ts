/**
 * Which events have locked — the reveal-at-lock rule's single source.
 *
 * events/open lists every pickable event (next 10 days) plus three weeks
 * of history, each with a tour-local `locked` flag. An event missing
 * from that list is older than the window, so it locked long ago; picks
 * can't exist for events beyond the forward window (pick routes refuse
 * unknown events). Hence: unknown = locked.
 *
 * Fails CLOSED: if the list can't be fetched, this returns null and
 * pickVisible() shows only the viewer's own picks — a privacy rule must
 * never reveal because a dependency was down.
 */
import { MODEL_API } from "@/lib/db";

export async function openEventLocks(): Promise<Map<string, boolean> | null> {
  try {
    const res = await fetch(`${MODEL_API}/api/events/open`, { next: { revalidate: 120 } });
    if (!res.ok) return null;
    const { events } = await res.json();
    if (!Array.isArray(events)) return null;
    const locks = new Map<string, boolean>();
    for (const e of events) locks.set(String(e.tournament_id).toUpperCase(), !!e.locked);
    return locks;
  } catch {
    return null;
  }
}

/** Another member's pick is visible only once its event has locked.
 *  Your own picks are always visible to you. */
export function pickVisible(
  locks: Map<string, boolean> | null, tid: string, pickUserId: string, viewerId: string,
): boolean {
  if (pickUserId === viewerId) return true;
  if (!locks) return false;
  return locks.get(tid.toUpperCase()) ?? true;
}
