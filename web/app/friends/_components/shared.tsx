"use client";

/**
 * Shared by the Friends Game screens: the API hook, card styles, small helpers.
 * Split out of app/friends/page.tsx unchanged.
 */

import React, { useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { subscribeThisDevice } from "@/lib/pushClient";
import { getOpenEvents } from "@/lib/api";
import type { OpenEvent } from "@/lib/api";
import { getGolferForm } from "@/lib/api";
import type { GolferForm } from "@/lib/api";
import { nameKey } from "@/lib/names";
import { whyLine } from "@/lib/whyLine";

/** Link a player name to their profile page. The profile page already
 *  reads ?player= (a "deep link" — state carried in the URL, so it
 *  survives refresh and can be shared). */
export function PlayerLink({ name, style }: { name: string; style?: React.CSSProperties }) {
  return (
    <Link href={`/players?player=${encodeURIComponent(name)}`}
      style={{ color: "inherit", textDecoration: "none", borderBottom: "1px dotted var(--bc-muted)", ...style }}>
      {name}
    </Link>
  );
}


export function useApi() {
  const { getToken } = useAuth();
  return useCallback(async (url: string, init: RequestInit = {}) => {
    const token = await getToken();
    return fetchJson(url, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  }, [getToken]);
}

/** fetch that FAILS LOUDLY: any non-OK response or non-JSON body becomes
 *  an Error whose message says what actually came back — so the UI can
 *  show "401 Unauthorized" or "404 <!DOCTYPE html…" instead of a shrug. */
export async function fetchJson(url: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const res = await fetch(url, init);
  const text = await res.text();
  try {
    const d = JSON.parse(text);
    if (!res.ok && d?.error) throw new Error(`${res.status}: ${d.error}`);
    return d;
  } catch (e) {
    if (e instanceof SyntaxError) {
      throw new Error(`${res.status}: non-JSON response (${text.slice(0, 60).replace(/\s+/g, " ")}…)`);
    }
    throw e;
  }
}

/** One-line toggle for pick reminders. Renders nothing where push can't
 *  work (iOS Safari needs the app added to the Home Screen first). */
export function ReminderBell() {
  const api = useApi();
  const [state, setState] = useState<"unsupported" | "off" | "on" | "busy">("unsupported");

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    navigator.serviceWorker.register("/sw.js")
      .then(reg => reg.pushManager.getSubscription())
      .then(sub => setState(sub ? "on" : "off"))
      .catch(() => setState("off"));
  }, []);

  async function toggle() {
    const prev = state;
    setState("busy");
    try {
      const reg = await navigator.serviceWorker.ready;
      if (prev === "on") {
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          await api("/api/friends/reminders", {
            method: "DELETE", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ endpoint: sub.endpoint }),
          });
          await sub.unsubscribe();
        }
        setState("off");
      } else {
        setState((await subscribeThisDevice(api)) ? "on" : "off");
      }
    } catch { setState(prev === "busy" ? "off" : prev); }
  }

  if (state === "unsupported") return null;
  const on = state === "on";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
      color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)" }}>
      <span>Pick reminders — a nudge the day before an event locks if your picks aren&apos;t in.</span>
      <button onClick={toggle} disabled={state === "busy"} style={{
        ...btnQuiet, padding: "4px 12px", fontSize: "0.9em",
        color: on ? "var(--bc-sel-fg)" : "var(--bc-muted)",
        background: on ? "var(--bc-sel-bg)" : "transparent",
        borderColor: on ? "var(--bc-sel-line)" : "var(--bc-line)",
      }}>
        {state === "busy" ? "…" : on ? "On" : "Off"}
      </button>
    </div>
  );
}

export type EventInfo = { tid: string; name: string; tour: string; locked: boolean; startDate: string };
export type Standing = {
  user_id: string; user_name: string; total: number;
  events: Record<string, { picks: { player: string; earnings: number | null; position: string | null }[]; event_total: number; settled: boolean; projected: boolean }>;
};
export type Tail = { recommendation_id: string; label: string; tournament_id: string;
  odds_american: number | null; stake_units: number; outcome: string; pnl: number | null };

export const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

/** Compact board cells show the surname, whichever format the name
 *  arrived in: "Scheffler, Scottie" and "Scottie Scheffler" → "Scheffler". */
export const lastName = (n: string) =>
  n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);

export const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 20, marginBottom: 16,
};
export const cell: React.CSSProperties = {
  padding: "8px 12px", borderBottom: "1px solid var(--bc-line)",
  fontSize: "max(var(--fs-min), 0.86em)", color: "var(--bc-text)", textAlign: "left",
};
export const hdr: React.CSSProperties = {
  ...cell, color: "var(--bc-muted)", fontWeight: 600, fontSize: "max(var(--fs-min), 0.74em)",
  textTransform: "uppercase", letterSpacing: "0.04em",
};

export const ModelBadge = () => (
  <span style={{ marginLeft: 6, fontSize: "max(var(--fs-min-xs), 0.62em)", fontWeight: 900, letterSpacing: "0.08em",
    color: "var(--bc-text)", background: "var(--bc-line-hi)", borderRadius: 3, padding: "2px 6px",
    textTransform: "uppercase", verticalAlign: "middle" }}>
    Model
  </span>
);

// ── My Picks ─────────────────────────────────────────────────────────────────

export type FieldRow = { player_name: string; world_rank: number | null;
  win_prob: number | null; top10_prob: number | null; cut_prob: number | null };


// ── Standings ────────────────────────────────────────────────────────────────

/** Opens the PNG in a new tab; on phones with Web Share, offers the sheet
 *  with the image attached so it drops straight into a chat. */
export async function shareReceipt(tid: string, uid: string, game: "rounds" | "fades") {
  const url = `/api/receipt?tid=${encodeURIComponent(tid)}&u=${encodeURIComponent(uid)}&game=${game}`;
  if (typeof navigator.share === "function" && typeof navigator.canShare === "function") {
    try {
      const blob = await fetch(url).then(r => r.blob());
      const file = new File([blob], `golf-edge-${tid}.png`, { type: "image/png" });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file] });
        return;
      }
    } catch { /* fall through to opening it */ }
  }
  window.open(url, "_blank");
}

export const btn: React.CSSProperties = {
  background: "var(--bc-yellow-fill)", color: "#081f14", border: "none",
  borderRadius: 6, padding: "9px 16px", fontWeight: 800, fontSize: "max(var(--fs-min), 0.8em)",
  textTransform: "uppercase", letterSpacing: "0.05em", cursor: "pointer",
};
export const btnQuiet: React.CSSProperties = {
  ...btn, background: "transparent", color: "var(--bc-quiet-fg)",
  border: "1px solid var(--bc-quiet-line)", fontWeight: 700,
};
export const inputStyle: React.CSSProperties = {
  padding: "9px 12px", borderRadius: 6, fontSize: "max(var(--fs-min), 0.88em)",
  background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
  color: "var(--bc-text)", outline: "none",
};

/** A per-event game's event list: the open window (events/open, 21 days
 *  back to 10 ahead) plus finished events this person's groups played in
 *  `game` (/api/friends/past-events), so old results stay reachable. The
 *  open list wins on overlap: it knows what's live right now. */
export async function openPlusPast(
  api: (url: string, init?: RequestInit) => Promise<Record<string, unknown>>,
  game: "rounds" | "fades" | "college",
): Promise<OpenEvent[]> {
  const [open, past] = await Promise.all([
    getOpenEvents().then(d => d.events ?? []).catch(() => [] as OpenEvent[]),
    api(`/api/friends/past-events?game=${game}`).then(d => (d.events as OpenEvent[]) ?? []).catch(() => [] as OpenEvent[]),
  ]);
  const live = new Set(open.map(e => e.tournament_id));
  return [...past.filter(e => !live.has(e.tournament_id)), ...open]
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
}

/** Jack's one-line why (lib/whyLine.ts) for every golfer in a list, from
 *  his real results (/api/golfer-form) plus the list's own model chances.
 *  name -> line; a golfer with nothing honest to say has no entry. */
export function useWhyLines(
  tid: string,
  rows: { player_name: string; win_prob: number | null; top10_prob?: number | null; world_rank?: number | null }[],
): Map<string, string> {
  const [form, setForm] = useState<GolferForm[]>([]);
  useEffect(() => {
    if (!tid) return;
    let cancelled = false;
    getGolferForm(tid).then(d => { if (!cancelled) setForm(d.players ?? []); }).catch(() => setForm([]));
    return () => { cancelled = true; };
  }, [tid]);
  return useMemo(() => {
    const out = new Map<string, string>();
    if (!form.length) return out;
    const facts = new Map(form.map(f => [nameKey(f.player_name), f]));
    for (const r of rows) {
      const f = facts.get(nameKey(r.player_name));
      try {
        const line = whyLine({
          recent: f?.recent ?? [], courseStarts: f?.event_starts ?? 0, courseCuts: f?.event_cuts ?? 0,
          winProb: r.win_prob ?? null, top10Prob: r.top10_prob ?? null, worldRank: r.world_rank ?? null,
        });
        if (line) out.set(r.player_name, line);
      } catch { /* no line beats a wrong one */ }
    }
    return out;
  }, [form, rows]);
}

