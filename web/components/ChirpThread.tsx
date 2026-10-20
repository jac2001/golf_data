"use client";

/**
 * ChirpThread — "Send a chirp" on a matchup card, and the group's thread
 * for that tournament (docs/CHIRPS_DESIGN.md). Presets come from Jack's
 * lib/chirpPresets.ts: only lines that are true for you right now. Each
 * chirp shows the matchup snapshot the server froze when it was sent.
 * Always sent by the person; never automatic; no push in v1, just the badge.
 */

import React, { useCallback, useEffect, useState } from "react";
import { chirpPresets } from "@/lib/chirpPresets";
import type { ChirpContext, Preset } from "@/lib/chirpPresets";
import type { Slate } from "@/lib/matchTypes";
import { money, ordinal } from "@/lib/matchTypes";

type Card = { event: string; status: string; rank: number | null; players: number; total: number | null;
  leader: string | null; gap: number | null; estimated: boolean };
type Chirp = { id: string; user_id: string; user_name: string; created_at: string; removed: boolean;
  preset_id?: string | null; text?: string; card?: Card; reactions?: { emoji: string; n: number; mine: boolean }[] };

const MAX_TEXT = 140;

async function call(url: string, init?: RequestInit) {
  const res = await fetch(url, init);
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((d as { error?: string }).error ?? `Request failed (${res.status})`);
  return d as Record<string, unknown>;
}

/** What the matchup says about you, for Jack's chirpPresets. */
function contextFor(s: Slate): ChirpContext {
  const me = s.lines.find(l => l.user_id === s.me_id) ?? null;
  const out = (pos: string) => /^(CUT|MC|WD|W\/D|DQ|MDF)$/i.test(pos.trim());
  const model = s.lines.find(l => l.user_id === "model");
  return {
    status: s.status,
    myRank: me?.rank ?? null,
    players: s.lines.length,
    tied: !!me && s.lines.filter(l => l.rank === me.rank).length > 1,
    myGolferLeading: me?.golfers.find(g => /^T?1$/.test(g.position.trim()))?.name ?? null,
    myGolfersOut: me ? me.golfers.filter(g => out(g.position)).length : 0,
    myGolfers: me?.golfers.length ?? 0,
    aheadOfModel: me && model && me.user_id !== "model" ? me.total > model.total : null,
  };
}

/** "2nd of 4 · $412,000 · Rick leads by $38,000 (est.)" */
function cardLine(c?: Card): string {
  if (!c || c.status === "open" || c.rank == null) return "";
  const parts = [`${ordinal(c.rank)} of ${c.players}`];
  if (c.total != null) parts.push(money(c.total));
  if (c.leader && c.gap != null) parts.push(`${c.leader} leads by ${money(c.gap)}`);
  return parts.join(" · ") + (c.estimated && c.status !== "final" ? " (est.)" : "");
}

const when = (iso: string) => {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
};

export default function ChirpThread({ groupId, slate }: { groupId: number; slate: Slate }) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [chirps, setChirps] = useState<Chirp[] | null>(null);
  const [isOwner, setIsOwner] = useState(false);
  const [me, setMe] = useState("");
  const [reactions, setReactions] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const tid = slate.tournament_id;

  useEffect(() => {
    call(`/api/friends/chirps?group_id=${groupId}&unread=1`).then(d => setUnread(Number(d.unread ?? 0))).catch(() => {});
  }, [groupId, tid]);

  const load = useCallback(() => {
    call(`/api/friends/chirps?group_id=${groupId}&tournament_id=${encodeURIComponent(tid)}`).then(d => {
      setChirps((d.chirps as Chirp[]) ?? []); setIsOwner(!!d.is_owner); setMe(String(d.me ?? ""));
      setReactions((d.reactions as string[]) ?? []); setUnread(0);
    }).catch(e => { setErr(e.message); setChirps([]); });
  }, [groupId, tid]);

  useEffect(() => { if (open) load(); }, [open, load]);

  let presets: Preset[] = [];
  try { presets = chirpPresets(contextFor(slate)); } catch { /* no chips; the custom box still works */ }

  async function send(body: { preset_id?: string; text?: string }) {
    setBusy(true); setErr("");
    try {
      const d = await call("/api/friends/chirps", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: groupId, tournament_id: tid, ...body }) });
      setChirps(c => [...(c ?? []), d.chirp as Chirp]); setText("");
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }
  async function react(id: string, emoji: string) {
    try { await call("/api/friends/chirps/react", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, emoji }) }); load(); } catch { /* list reload shows truth */ }
  }
  async function remove(id: string) {
    if (!confirm("Remove this chirp for everyone?")) return;
    try { await call("/api/friends/chirps", { method: "DELETE", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }) }); load(); } catch (e) { setErr((e as Error).message); }
  }
  async function report(id: string) {
    if (!confirm("Report this chirp to the group's owner?")) return;
    try { await call("/api/friends/chirps/report", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }) }); setErr("Reported. Thanks."); } catch (e) { setErr((e as Error).message); }
  }

  const quiet: React.CSSProperties = { background: "transparent", border: "none", color: "var(--bc-muted)",
    cursor: "pointer", fontFamily: "inherit", fontSize: "max(var(--fs-min), 0.78em)", padding: "4px 6px" };

  return (
    <>
      <button onClick={() => setOpen(true)} style={{ marginTop: 14, width: "100%", minHeight: 44, cursor: "pointer",
        fontFamily: "inherit", fontWeight: 800, background: "transparent", color: "var(--bc-text)",
        border: "1px solid var(--bc-line-hi)", borderRadius: 8, display: "flex", alignItems: "center",
        justifyContent: "center", gap: 8 }}>
        Send a chirp
        {unread > 0 && <span aria-label={`${unread} unread`} style={{ background: "var(--bc-yellow)", color: "#081f14",
          borderRadius: 999, padding: "1px 8px", fontSize: "0.8em", fontWeight: 900 }}>{unread}</span>}
      </button>

      {open && <>
        <div onClick={() => setOpen(false)} aria-hidden="true" style={{ position: "fixed", inset: 0, zIndex: 400, background: "rgba(0,0,0,0.55)" }} />
        <div role="dialog" aria-label="Group chirps" style={{
          position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 401, maxWidth: 560, margin: "0 auto",
          maxHeight: "85vh", display: "flex", flexDirection: "column", background: "var(--bc-panel)",
          borderTop: "1px solid var(--bc-line-hi)", borderRadius: "16px 16px 0 0",
          padding: "10px 16px calc(16px + env(safe-area-inset-bottom))" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontWeight: 900 }}>Chirps · {slate.name}</div>
            <button onClick={() => setOpen(false)} aria-label="Close" style={{ ...quiet, fontSize: "1.4em", minWidth: 44, minHeight: 44 }}>×</button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, padding: "6px 0" }}>
            {chirps === null && <div style={{ color: "var(--bc-muted)" }}>Loading…</div>}
            {chirps?.length === 0 && <div style={{ color: "var(--bc-muted)" }}>Nothing yet. Start it.</div>}
            {chirps?.map(c => (
              <div key={c.id} style={{ background: c.user_id === me ? "var(--bc-card-hi)" : "var(--bc-card)",
                border: "1px solid var(--bc-line)", borderRadius: 10, padding: "8px 10px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: "max(var(--fs-min), 0.78em)", color: "var(--bc-muted)" }}>
                  <span style={{ fontWeight: 800, color: "var(--bc-text)" }}>{c.user_id === me ? "You" : c.user_name}</span>
                  <span>{when(c.created_at)}</span>
                </div>
                {c.removed ? <div style={{ color: "var(--bc-muted)", fontStyle: "italic", marginTop: 2 }}>Removed</div> : <>
                  <div style={{ fontWeight: 700, margin: "3px 0" }}>{c.text}</div>
                  {cardLine(c.card) && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)" }}>{cardLine(c.card)}</div>}
                  <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                    {reactions.map(e => {
                      const r = c.reactions?.find(x => x.emoji === e);
                      return (
                        <button key={e} onClick={() => react(c.id, e)} aria-pressed={!!r?.mine} style={{ cursor: "pointer",
                          fontFamily: "inherit", borderRadius: 999, padding: "2px 8px", minHeight: 30,
                          background: r?.mine ? "var(--bc-raised)" : "transparent",
                          border: `1px solid ${r?.mine ? "var(--bc-line-hi)" : "var(--bc-line)"}`, color: "var(--bc-text)" }}>
                          {e}{r ? ` ${r.n}` : ""}
                        </button>
                      );
                    })}
                    <span style={{ marginLeft: "auto" }}>
                      {(c.user_id === me || isOwner) && <button onClick={() => remove(c.id)} style={quiet}>Remove</button>}
                      {c.user_id !== me && <button onClick={() => report(c.id)} style={quiet}>Report</button>}
                    </span>
                  </div>
                </>}
              </div>
            ))}
          </div>

          {presets.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "6px 0" }}>
              {presets.map(p => (
                <button key={p.id} onClick={() => send({ preset_id: p.id })} disabled={busy} style={{ cursor: "pointer",
                  fontFamily: "inherit", fontWeight: 700, borderRadius: 999, padding: "6px 12px", minHeight: 36,
                  background: "var(--bc-raised)", border: "1px solid var(--bc-line-hi)", color: "var(--bc-text)" }}>
                  {p.text}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={e => { e.preventDefault(); if (text.trim()) send({ text }); }} style={{ display: "flex", gap: 8 }}>
            <label htmlFor="chirp-text" style={{ position: "absolute", left: -9999 }}>Your chirp</label>
            <input id="chirp-text" value={text} onChange={e => setText(e.target.value.slice(0, MAX_TEXT))}
              placeholder="Say something…" maxLength={MAX_TEXT} style={{ flex: 1, minWidth: 0, minHeight: 44,
                padding: "0 12px", borderRadius: 8, background: "var(--bc-bg)", border: "1px solid var(--bc-line)",
                color: "var(--bc-text)", fontFamily: "inherit" }} />
            <button type="submit" disabled={busy || !text.trim()} style={{ minHeight: 44, padding: "0 16px",
              cursor: "pointer", fontFamily: "inherit", fontWeight: 900, border: "none", borderRadius: 8,
              background: "var(--bc-yellow)", color: "#081f14" }}>Send</button>
          </form>
          {err && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 6 }}>{err}</div>}
        </div>
      </>}
    </>
  );
}
