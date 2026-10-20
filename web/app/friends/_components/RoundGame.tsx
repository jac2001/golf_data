"use client";

/**
 * The Round Game: one pick per round, scored to par.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useCallback, useEffect, useState } from "react";
import LockCountdown from "@/components/LockCountdown";
import EventNav, { favoriteTour, fromOpenEvents, landingEvent } from "@/components/EventNav";
import PickConfirm, { buildConfirm } from "@/components/PickConfirm";
import { WhosInCard } from "./WhosInCard";
import { roundLockAt } from "@/lib/lockTime";
import type { ConfirmCopy } from "@/lib/pickConfirm";
import { getPredictions, getEventField, OpenEvent } from "@/lib/api";
import { EventInfo, FieldRow, ModelBadge, PlayerLink, btnQuiet, card, cell, hdr, inputStyle, lastName, shareReceipt, openPlusPast, useApi, useWhyLines } from "./shared";
import { useActiveGroup } from "./ActiveGroup";

// ── Round Game ───────────────────────────────────────────────────────────────

export type RoundPicksState = { rounds: Record<string, string | null>; used: string[];
  locks: Record<string, boolean>; event?: EventInfo };
export type RoundRow = { user_id: string; user_name: string; total: number; scored: number;
  rounds: Record<string, { player: string; score: number | null; visible: boolean }> };

export function RoundGameTab() {
  const api = useApi();
  const { groupQuery } = useActiveGroup();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState("");
  const [state, setState] = useState<RoundPicksState | null>(null);
  const [eventName, setEventName] = useState("");
  const [field, setField] = useState<FieldRow[]>([]);
  const [board, setBoard] = useState<RoundRow[] | null>(null);
  const [me, setMe] = useState("");
  const [pickingRound, setPickingRound] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    openPlusPast(api, "rounds").then(all => {
      const evs = all;
      setEvents(evs);
      // Default to this week's action (favorite tour, PGA by default);
      // history stays one chip away.
      const current = landingEvent(fromOpenEvents(evs), favoriteTour());
      if (current) setSelected(current.tournament_id);
    }).catch(() => {});
  }, [api]);

  const load = useCallback(() => {
    if (!selected) return;
    setErr("");
    api(`/api/friends/roundpicks?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => { setState(d as never); setEventName((d.event as EventInfo).name); })
      .catch(e => setErr(e.message));
    api(`/api/friends/roundboard?tournament_id=${encodeURIComponent(selected)}${groupQuery}`)
      .then(d => { setBoard((d.standings as RoundRow[]) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setBoard([]));
    // Field with numbers when the event has them (our model or DG's
    // euro model), plain names otherwise — same pattern as the Let It Ride field list.
    getPredictions(200, selected)
      .then(d => {
        if (String(d.tournament_id ?? "").toUpperCase() !== selected.toUpperCase()) {
          throw new Error("wrong event");
        }
        setField((d.players ?? [])
          .filter((r: FieldRow) => r.player_name)
          .sort((a: FieldRow, b: FieldRow) => (b.win_prob ?? 0) - (a.win_prob ?? 0)));
      })
      .catch(() =>
        getEventField(selected)
          .then(d => setField((d.players ?? []).map(p => ({
            player_name: p, world_rank: null, win_prob: null, top10_prob: null, cut_prob: null,
          }))))
          .catch(() => setField([])));
  }, [api, selected, groupQuery]);
  useEffect(load, [load]);

  const [confirm, setConfirm] = useState<ConfirmCopy | null>(null);
  async function pick(round: number, player: string) {
    setErr("");
    try {
      const d = await api("/api/friends/roundpicks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tournament_id: selected, round, player_name: player }),
      });
      setState(d as never); setPickingRound(null); setQuery("");
      // "Did it save?": this round's own lock, and the rounds picked so far.
      const st = d as unknown as RoundPicksState;
      const picked = Object.entries(st.rounds ?? {}).sort(([a], [b]) => Number(a) - Number(b))
        .map(([, n]) => n).filter((n): n is string => !!n);
      const ev = st.event;
      if (ev?.startDate) {
        const tour = ev.tour === "euro" ? "euro" : "pga";
        setConfirm(await buildConfirm({ picked, needed: 4, startDate: ev.startDate, tour,
          lock: roundLockAt(ev.startDate, tour, round) }));
      }
    } catch (e) { setErr((e as Error).message); }
  }

  async function clear(round: number) {
    setErr("");
    try {
      const d = await api("/api/friends/roundpicks", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tournament_id: selected, round }),
      });
      setState(d as never);
    } catch (e) { setErr((e as Error).message); }
  }

  // The whole field, always browsable — filter narrows, never gates.
  const why = useWhyLines(selected, field);
  // The round still open for picks (the organizer's view counts that one).
  const openRound = [1, 2, 3, 4].find(r => !state?.locks?.[String(r)]);
  const visibleField = field.filter(r =>
    !query || r.player_name.toLowerCase().includes(query.toLowerCase()));

  const fmt = (v: number) => (v > 0 ? `+${v}` : v === 0 ? "E" : String(v));

  return (
    <>
      <PickConfirm copy={confirm} onClose={() => setConfirm(null)} />
      {state?.event && openRound && field.length > 0 && (
        <WhosInCard game="rounds" tid={selected} eventName={state.event.name} startDate={state.event.startDate}
          tour={state.event.tour} round={openRound} refreshKey={Object.values(state.rounds ?? {}).filter(Boolean).length} />
      )}
      <EventNav events={fromOpenEvents(events)} selected={selected}
        onPick={tid => { setSelected(tid); setPickingRound(null); }} />

      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: "1.05em", marginBottom: 4 }}>
          {eventName || events.find(e => e.tournament_id === selected)?.name || "Loading…"}
        </div>
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginBottom: 14 }}>
          One player per round, each player once per event. Score is their round
          to par; a missed round costs +{5}. Lowest total wins.
        </div>

        {[1, 2, 3, 4].map(r => {
          const locked = !!state?.locks?.[String(r)];
          const current = state?.rounds?.[String(r)] ?? null;
          return (
            <div key={r} style={{ display: "flex", alignItems: "center", gap: 10,
              padding: "8px 0", borderBottom: "1px solid var(--bc-line)", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 800, width: 32, color: locked ? "var(--bc-muted)" : "var(--bc-text)" }}>R{r}</span>
              {current
                ? <span style={{ fontWeight: 600 }}><PlayerLink name={current} /></span>
                : <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {locked ? "no pick — +5" : "no pick yet"}
                  </span>}
              {!locked && state?.event?.startDate && (
                <span style={{ fontSize: "max(var(--fs-min), 0.72em)" }}>
                  <LockCountdown startDate={state.event.startDate} tour={state.event.tour} addDays={r - 1} />
                </span>
              )}
              {!locked && (
                <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button onClick={() => { setPickingRound(pickingRound === r ? null : r); setQuery(""); }}
                    style={{ ...btnQuiet, padding: "3px 10px", fontSize: "max(var(--fs-min), 0.74em)" }}>
                    {current ? "Change" : "Pick"}
                  </button>
                  {current && (
                    <button onClick={() => clear(r)} style={{ ...btnQuiet, padding: "3px 10px", fontSize: "max(var(--fs-min), 0.74em)" }}>✕</button>
                  )}
                </span>
              )}
              {locked && <span style={{ marginLeft: "auto", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.72em)" }}>locked</span>}
              {pickingRound === r && !locked && (
                <div style={{ flexBasis: "100%" }}>
                  <input autoFocus value={query} onChange={e => setQuery(e.target.value)}
                    placeholder={field.length ? "Filter the field…" : "Field not announced yet"}
                    style={{ ...inputStyle, width: "100%", boxSizing: "border-box", marginTop: 6 }} />
                  {visibleField.length > 0 && (
                    <div style={{ maxHeight: 280, overflowY: "auto", marginTop: 6,
                      background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
                      borderRadius: 8, WebkitOverflowScrolling: "touch" as never }}>
                      {visibleField.map(row => {
                        const used = (state?.used ?? []).includes(row.player_name);
                        return (
                          <button key={row.player_name} disabled={used}
                            onClick={() => pick(r, row.player_name)} style={{
                              display: "flex", alignItems: "center", width: "100%", textAlign: "left",
                              background: "none", border: "none", cursor: used ? "default" : "pointer",
                              padding: "9px 14px", fontSize: "max(var(--fs-min), 0.88em)",
                              color: used ? "var(--bc-muted)" : "var(--bc-text)",
                              borderBottom: "1px solid var(--bc-line)" }}>
                            <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                              <span>
                                <span style={{ fontWeight: 600 }}>{row.player_name}</span>
                                {used && <span style={{ marginLeft: 8, fontSize: "max(var(--fs-min), 0.78em)" }}>· used</span>}
                              </span>
                              {why.get(row.player_name) && <span style={{ color: "var(--bc-muted)",
                                fontSize: "max(var(--fs-min), 0.86em)", marginTop: 2 }}>{why.get(row.player_name)}</span>}
                            </span>
                            {row.win_prob != null && (
                              <span style={{ marginLeft: "auto", color: "var(--bc-muted)",
                                fontVariantNumeric: "tabular-nums" }}>
                                {(row.win_prob * 100).toFixed(1)}%
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 10 }}>{err}</p>}
      </div>

      {/* Event board */}
      {board && board.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>#</th><th style={hdr}>Player</th>
              {[1, 2, 3, 4].map(r => <th key={r} style={{ ...hdr, textAlign: "right" }}>R{r}</th>)}
              <th style={{ ...hdr, textAlign: "right" }}>Total</th>
            </tr></thead>
            <tbody>
              {board.map((row, i) => (
                <tr key={row.user_id} style={{ background: row.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, fontWeight: 800, color: "var(--bc-muted)" }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 700 }}>
                    {row.user_name}
                    {row.user_id === "model" && <ModelBadge />}
                    {row.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                  </td>
                  {[1, 2, 3, 4].map(r => {
                    const c = row.rounds[String(r)];
                    return (
                      <td key={r} style={{ ...cell, textAlign: "right", fontSize: "max(var(--fs-min), 0.8em)" }}>
                        {!c ? <span style={{ color: "var(--bc-muted)" }}>—</span>
                          : !c.visible ? <span style={{ color: "var(--bc-muted)" }}>hidden</span>
                          : <>
                              <span style={{ color: "var(--bc-muted)" }}>{lastName(c.player)}</span>{" "}
                              <span style={{ fontWeight: 700, color: c.score == null ? "var(--bc-muted)"
                                : c.score < 0 ? "var(--bc-green)" : c.score > 0 ? "var(--bc-red-text)" : "var(--bc-text)" }}>
                                {c.score == null ? "…" : fmt(c.score)}
                              </span>
                            </>}
                      </td>
                    );
                  })}
                  <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                    {row.scored ? fmt(row.total) : "—"}
                    {row.scored > 0 && (
                      <button onClick={() => shareReceipt(selected, row.user_id, "rounds")}
                        title="Share receipt" style={{
                          background: "transparent", border: "1px solid var(--bc-line)",
                          borderRadius: 4, color: "var(--bc-muted)", cursor: "pointer",
                          fontSize: "max(var(--fs-min), 0.72em)", padding: "1px 7px", marginLeft: 8 }}>
                        ⇪
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
