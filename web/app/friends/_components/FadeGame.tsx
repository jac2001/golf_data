"use client";

/**
 * The Fade Game: fade three stars, least money wins.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useCallback, useEffect, useState } from "react";
import LockCountdown from "@/components/LockCountdown";
import EventNav, { favoriteTour, fromOpenEvents, landingEvent } from "@/components/EventNav";
import PickConfirm, { buildConfirm } from "@/components/PickConfirm";
import type { ConfirmCopy } from "@/lib/pickConfirm";
import { OpenEvent } from "@/lib/api";
import { EventInfo, ModelBadge, PlayerLink, btnQuiet, card, cell, hdr, lastName, money, shareReceipt, openPlusPast, useApi } from "./shared";
import { useActiveGroup } from "./ActiveGroup";

// ── Fade Game ────────────────────────────────────────────────────────────────

export type FadePoolRow = { player_name: string; win_prob: number | null; expected_earnings: number | null };
export type FadeEvent = EventInfo & { purse: number | null; hasModel: boolean };
export type FadeBoardRow = { user_id: string; user_name: string; total: number | null;
  fades: { player: string; earnings: number | null; position: string | null }[] };

export function FadeTab() {
  const api = useApi();
  const { groupQuery } = useActiveGroup();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [event, setEvent] = useState<FadeEvent | null>(null);
  const [pool, setPool]   = useState<FadePoolRow[]>([]);
  const [partial, setPartial] = useState(false);
  const [fades, setFades] = useState<string[]>([]);
  const [board, setBoard] = useState<{ settled: boolean; earnings_estimated: boolean;
    standings: FadeBoardRow[]; me: string } | null>(null);
  const [err, setErr]     = useState("");
  const [loading, setLoading] = useState(true);

  // The fade pool is defined by model win chances, so only PGA
  // (has_model) events are playable.
  useEffect(() => {
    openPlusPast(api, "fades").then(all => {
      const evs = all.filter(e => e.has_model);
      setEvents(evs);
      const first = landingEvent(fromOpenEvents(evs), favoriteTour());
      if (first) setSelected(first.tournament_id);
      else setLoading(false);
    }).catch(() => setLoading(false));
  }, [api]);

  const load = useCallback(() => {
    if (!selected) return;
    setLoading(true); setErr(""); setBoard(null);
    api(`/api/friends/fades?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => {
        const ev = d.event as FadeEvent;
        setEvent(ev);
        setPool((d.pool as FadePoolRow[]) ?? []);
        setPartial(!!d.partial);
        setFades((d.fades as string[]) ?? []);
        if (ev.locked) {
          api(`/api/friends/fadeboard?tournament_id=${encodeURIComponent(selected)}${groupQuery}`)
            .then(b => setBoard(b as never)).catch(() => {});
        }
      })
      .catch(e => setErr(`Could not load the fade game — ${e.message}`))
      .finally(() => setLoading(false));
  }, [api, selected, groupQuery]);

  useEffect(() => { load(); }, [load]);

  const [confirm, setConfirm] = useState<ConfirmCopy | null>(null);
  async function toggle(player: string, faded: boolean) {
    setErr("");
    try {
      const d = await api("/api/friends/fades", {
        method: faded ? "DELETE" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_name: player, tournament_id: selected }),
      });
      setFades(d.fades as string[]);
      if (!faded && event?.startDate) {
        setConfirm(await buildConfirm({ picked: d.fades as string[], needed: 3, startDate: event.startDate,
          tour: event.tour === "euro" ? "euro" : "pga" }));
      }
    } catch (e) { setErr((e as Error).message); }
  }

  if (loading) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (!event) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0, lineHeight: 1.6 }}>
        The Fade Game is off this week. It needs a regular PGA stroke-play
        event with model numbers — team weeks (Ryder Cup, Presidents Cup)
        and off-weeks don&apos;t qualify because there&apos;s no individual
        prize money to fade. It opens back up on Tuesday of the next
        PGA tournament week.
      </p>
      {err && <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 10 }}>{err}</p>}
    </div>
  );

  return (
    <>
      <PickConfirm copy={confirm} onClose={() => setConfirm(null)} />
      <EventNav events={fromOpenEvents(events)} selected={selected} onPick={setSelected} />

      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: "1.05em" }}>
          {event.name || events.find(e => e.tournament_id === event.tid)?.name || "Loading…"}
        </div>
        {!event.locked && event.startDate && (
          <div style={{ fontSize: "max(var(--fs-min), 0.78em)", marginTop: 3 }}>
            <LockCountdown startDate={event.startDate} tour={event.tour} />
          </div>
        )}
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 2 }}>
          {event.locked
            ? (events.find(e => e.tournament_id === selected)?.finished
                ? "Final — the fadeboard below is graded."
                : "Fades are locked — tournament underway.")
            : `Pick 3 top-20 players you think will FLOP · lowest combined earnings wins · ${3 - fades.length} of 3 remaining`}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16 }}>
          {fades.map(p => (
            <span key={p} style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              background: "var(--bc-panel)", border: "1px solid var(--bc-red-text)",
              borderRadius: 6, padding: "8px 12px", fontSize: "0.9em", fontWeight: 700,
            }}>
              <PlayerLink name={p} />
              {!event.locked && (
                <button onClick={() => toggle(p, true)} aria-label={`Remove fade ${p}`} style={{
                  background: "none", border: "none", color: "var(--bc-muted)",
                  cursor: "pointer", fontSize: "1em", padding: 0, lineHeight: 1,
                }}>✕</button>
              )}
            </span>
          ))}
          {fades.length === 0 && (
            <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>No fades yet.</span>
          )}
        </div>

        {/* Same anti-chalk fact for fades: the 3 lowest expected earners
            are the model's own fades — matching them can only tie it. */}
        {!event.locked && fades.length === 3 && pool.length >= 3 && (() => {
          const obvious = [...pool]
            .sort((a, b) => (a.expected_earnings ?? 0) - (b.expected_earnings ?? 0))
            .slice(0, 3).map(p => p.player_name);
          return obvious.every(n => fades.includes(n));
        })() && (
          <p style={{ color: "var(--bc-orange)", fontSize: "max(var(--fs-min), 0.85em)", marginTop: 10, fontWeight: 600 }}>
            These are the model&apos;s own three fades — you can tie it, never
            beat it. Your edge is a favorite the model still believes in.
          </p>
        )}

        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 10 }}>{err}</p>}
      </div>

      {/* Post-lock: how everyone's fades are cashing (least money on top). */}
      {board && board.standings.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            Fadeboard
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
              lowest total wins{board.earnings_estimated ? " · est. purse split" : ""}
            </span>
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>#</th><th style={hdr}>Player</th>
              <th style={hdr}>Fades</th>
              <th style={{ ...hdr, textAlign: "right" }}>Total</th>
            </tr></thead>
            <tbody>
              {board.standings.map((row, i) => (
                <tr key={row.user_id} style={{ background: row.user_id === board.me ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, fontWeight: 800, color: "var(--bc-muted)" }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 700 }}>
                    {row.user_name}
                    {row.user_id === "model" && <ModelBadge />}
                    {row.user_id === board.me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                  </td>
                  <td style={{ ...cell, fontSize: "max(var(--fs-min), 0.8em)", color: "var(--bc-muted)" }}>
                    {row.fades.map(f => (
                      <span key={f.player} style={{ marginRight: 10, whiteSpace: "nowrap" }}>
                        {lastName(f.player)}
                        {f.earnings != null && (
                          <span style={{ fontWeight: 700, marginLeft: 4,
                            color: f.earnings > 0 ? "var(--bc-red-text)" : "var(--bc-green)" }}>
                            {money(f.earnings)}
                          </span>
                        )}
                      </span>
                    ))}
                  </td>
                  <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                    {row.total != null ? money(row.total) : "…"}
                    {board.settled && row.total != null && (
                      <button onClick={() => shareReceipt(selected, row.user_id, "fades")}
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

      {/* The pool: only these 20 are fair game. */}
      {!event.locked && pool.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            The pool
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
              top 20 by model win chance — pick the ones you don&apos;t believe in
            </span>
          </div>
          {partial && (
            <div style={{ margin: "4px 16px 0", padding: "8px 12px", borderRadius: 6,
              background: "var(--bc-raised)", border: "1px solid var(--bc-line-hi)",
              color: "var(--bc-text)", fontSize: "max(var(--fs-min), 0.85em)", fontWeight: 600 }}>
              Early field — only the first commitments are in. Numbers and the
              pool firm up once the full field posts (usually Tuesday).
            </div>
          )}
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={hdr}>Player</th>
              <th style={{ ...hdr, textAlign: "right" }}>Win chance</th>
              <th style={{ ...hdr, textAlign: "right" }}>Model expects</th>
              <th style={hdr} />
            </tr></thead>
            <tbody>
              {pool.map(r => {
                const faded = fades.includes(r.player_name);
                return (
                  <tr key={r.player_name}
                      style={{ background: faded ? "var(--bc-card-hi)" : "transparent" }}>
                    <td style={{ ...cell, fontWeight: 600 }}>
                      <PlayerLink name={r.player_name} />
                    </td>
                    <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {r.win_prob != null ? `${(r.win_prob * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--bc-muted)" }}>
                      {r.expected_earnings != null ? money(r.expected_earnings) : "—"}
                    </td>
                    <td style={{ ...cell, textAlign: "right" }}>
                      {faded ? (
                        <button onClick={() => toggle(r.player_name, true)}
                          style={{ ...btnQuiet, padding: "3px 10px", fontSize: "max(var(--fs-min), 0.74em)", color: "var(--bc-red-text)" }}>
                          Faded ✕</button>
                      ) : (
                        <button onClick={() => toggle(r.player_name, false)}
                          disabled={fades.length >= 3}
                          style={{ ...btnQuiet, padding: "3px 10px", fontSize: "max(var(--fs-min), 0.74em)",
                            opacity: fades.length >= 3 ? 0.4 : 1,
                            cursor: fades.length >= 3 ? "default" : "pointer" }}>
                          Fade</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!event.locked && pool.length === 0 && (
        <div style={{ ...card, background: "var(--bc-panel)" }}>
          <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)", lineHeight: 1.6 }}>
            The pool for {event.name} isn&apos;t set yet. Fades open once the
            model&apos;s numbers post for this event — usually Tuesday, when
            the full field is announced and predictions run. Your 3 fades
            stay open until midnight ET the night before round 1 (UK time for DP World Tour events), so there&apos;s no rush.
          </p>
        </div>
      )}
    </>
  );
}
