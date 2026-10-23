"use client";

/**
 * "Also this week": the games this member hasn't picked yet, soonest lock
 * first, each with a Pick button that opens that game. Rick's first week
 * (Oct 21): he picked Let It Ride and never saw the other three games.
 * Which rows show is Jack's lib/weekChecklist.ts; this file is the plumbing.
 * Any failure renders nothing: the games themselves still work.
 */

import { useEffect, useState } from "react";
import { getOpenEvents, type OpenEvent } from "@/lib/api";
import { lockAt, roundLockAt, TOUR_TZ_LABEL } from "@/lib/lockTime";
import { weekChecklist, type ChecklistItem, type GameStatus } from "@/lib/weekChecklist";
import type { GameId } from "@/lib/landing";
import { useApi } from "./shared";

type Counts = { ride: number; rounds: Record<string, number>; fades: number; college: number };
type MyWeek = { ride: { needed: number; tours: string[] } | null; events: Record<string, Counts> };

const GAME_NAME: Record<GameId, string> = {
  ride: "Let It Ride", rounds: "Round Game", fades: "Fade Game", college: "College Game",
};

/** The per-game statuses for this week's events (Jack's function picks the rows). */
function statuses(evs: OpenEvent[], mine: MyWeek, now: Date): GameStatus[] {
  const out: GameStatus[] = [];
  const many = evs.length > 1;
  for (const e of evs) {
    const tour = e.tour === "euro" ? "euro" : "pga";
    const c = mine.events[e.tournament_id] ?? { ride: 0, rounds: {}, fades: 0, college: 0 };
    const where = many ? ` · ${e.name}` : "";
    const lock = lockAt(e.start_date, tour);
    const tid = e.tournament_id;
    if (mine.ride && mine.ride.tours.includes(tour)) {
      out.push({ key: `ride:${tid}`, game: "ride", label: `Let It Ride${where}`, locksAt: lock, have: c.ride, needed: mine.ride.needed });
    }
    // The Round Game asks for the next round that hasn't locked.
    const r = [1, 2, 3, 4].find(n => roundLockAt(e.start_date, tour, n) > now);
    if (r) {
      out.push({ key: `rounds:${tid}`, game: "rounds", label: `Round Game · Round ${r}${where}`,
        locksAt: roundLockAt(e.start_date, tour, r), have: c.rounds[String(r)] ?? 0, needed: 1 });
    }
    if (e.has_model) {
      out.push({ key: `fades:${tid}`, game: "fades", label: `Fade Game${where}`, locksAt: lock, have: c.fades, needed: 3 });
    }
    if (tour === "pga") {
      out.push({ key: `college:${tid}`, game: "college", label: `College Game${where}`, locksAt: lock, have: c.college, needed: 1 });
    }
  }
  return out;
}

function untilText(at: Date, now: Date, tour: string): string {
  const left = at.getTime() - now.getTime();
  const d = Math.floor(left / 86_400_000);
  const h = Math.floor((left % 86_400_000) / 3_600_000);
  const m = Math.floor((left % 3_600_000) / 60_000);
  const span = d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
  return `Locks in ${span} · midnight ${TOUR_TZ_LABEL[tour] ?? "ET"}`;
}

export function WeekChecklist({ groupId, refreshKey, onPick }: {
  groupId: number; refreshKey?: string; onPick: (g: GameId) => void;
}) {
  const api = useApi();
  const [rows, setRows] = useState<(ChecklistItem & { tour: string })[]>([]);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const evs = ((await getOpenEvents()).events ?? []).filter(e => !e.finished && e.field_available);
        if (!evs.length) { if (!cancelled) setRows([]); return; }
        const ids = evs.map(e => e.tournament_id).join(",");
        const mine = await api(`/api/friends/my-week?group_id=${groupId}&tournament_ids=${ids}`) as unknown as MyWeek;
        const tourOf = new Map(evs.map(e => [e.tournament_id, e.tour]));
        const items = weekChecklist(statuses(evs, mine, new Date()), new Date());
        if (!cancelled) setRows(items.map(i => ({ ...i, tour: tourOf.get(i.key.split(":")[1]) ?? "pga" })));
      } catch {
        if (!cancelled) setRows([]);   // includes the TODO scaffold throwing: show nothing
      }
    })();
    return () => { cancelled = true; };
  }, [api, groupId, refreshKey]);

  const live = rows.filter(r => r.locksAt > now);
  if (!live.length) return null;

  return (
    <section aria-label="Still to pick this week" style={{
      background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10,
      padding: "10px 12px", marginBottom: 12,
    }}>
      <p style={{ margin: "0 0 6px", fontSize: "max(var(--fs-min), 0.72em)", fontWeight: 800,
        letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--bc-muted)" }}>
        Still to pick this week
      </p>
      {live.map(r => (
        <div key={r.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0",
          borderTop: "1px solid var(--bc-line)" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: "max(var(--fs-min), 0.9em)" }}>
              {r.label}
              {r.left > 1 && <span style={{ color: "var(--bc-muted)", fontWeight: 600 }}> · {r.left} to go</span>}
            </div>
            <div style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700,
              color: r.soon ? "var(--bc-orange)" : "var(--bc-green)" }}>
              {untilText(r.locksAt, now, r.tour)}
            </div>
          </div>
          <button onClick={() => onPick(r.game)} aria-label={`Pick: ${r.label}`} style={{
            minHeight: 40, padding: "0 14px", borderRadius: 7, cursor: "pointer", fontFamily: "inherit",
            fontWeight: 900, background: "var(--bc-go-bg)", color: "var(--bc-go-fg)", border: "none",
          }}>Pick</button>
        </div>
      ))}
      <p style={{ margin: "6px 0 0", fontSize: "max(var(--fs-min), 0.75em)", color: "var(--bc-muted)" }}>
        Each game is separate: a missed Round Game round costs +5.
      </p>
    </section>
  );
}
