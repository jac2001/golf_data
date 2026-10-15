"use client";

/**
 * My Bets: this person's logged bets.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useCallback, useEffect, useState } from "react";
import { btn, btnQuiet, card, inputStyle, useApi } from "./shared";

// ── My Bets ──────────────────────────────────────────────────────────────────

export type UserBet = { id: number; tournament_id: string; description: string;
  odds_american: number | null; stake_units: number; shared: boolean; outcome: string };

export function MyBetsTab() {
  const api = useApi();
  const [bets, setBets] = useState<UserBet[] | null>(null);
  const [desc, setDesc]   = useState("");
  const [odds, setOdds]   = useState("");
  const [stake, setStake] = useState("1");
  const [shared, setShared] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    api("/api/friends/bets")
      .then(d => setBets((d.bets as UserBet[]) ?? []))
      .catch(e => { setErr((e as Error).message); setBets([]); });
  }, [api]);
  useEffect(load, [load]);

  async function add() {
    if (!desc.trim()) return;
    setErr("");
    try {
      await api("/api/friends/bets", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: desc.trim(),
          odds_american: odds.trim() ? parseInt(odds, 10) : null,
          stake_units: parseFloat(stake) || 1,
          shared,
        }),
      });
      setDesc(""); setOdds(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function patch(id: number, body: object) {
    try {
      await api("/api/friends/bets", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...body }),
      });
    } catch (e) { setErr((e as Error).message); }
    load();
  }

  async function del(id: number) {
    try {
      await api("/api/friends/bets", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
    } catch (e) { setErr((e as Error).message); }
    load();
  }

  if (!bets) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;

  return (
    <>
      <div style={card}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input value={desc} onChange={e => setDesc(e.target.value)}
            placeholder='What did you bet? e.g. "Scheffler top 10, DraftKings"'
            style={{ ...inputStyle, flex: "1 1 280px" }}
            onKeyDown={e => e.key === "Enter" && add()} />
          <input value={odds} onChange={e => setOdds(e.target.value)}
            placeholder="+450" style={{ ...inputStyle, width: 70 }} />
          <input value={stake} onChange={e => setStake(e.target.value)}
            placeholder="1" title="Stake (units)" style={{ ...inputStyle, width: 50 }} />
          <label style={{ display: "flex", alignItems: "center", gap: 6,
            color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", cursor: "pointer" }}>
            <input type="checkbox" checked={shared} onChange={e => setShared(e.target.checked)} />
            share with my groups
          </label>
          <button onClick={add} style={btn}>Log bet</button>
        </div>
        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", margin: "10px 0 0" }}>{err}</p>}
      </div>

      {bets.length === 0 ? (
        <div style={card}>
          <p style={{ color: "var(--bc-muted)", margin: 0, fontSize: "max(var(--fs-min), 0.88em)" }}>
            No bets logged. Anything you bet anywhere can live here — mark it
            shared and your groups see it in their feed.
          </p>
        </div>
      ) : bets.map(b => (
        <div key={b.id} style={{ ...card, padding: "12px 16px", display: "flex",
          gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 600, fontSize: "0.9em" }}>{b.description}</span>
          {b.odds_american != null && (
            <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)" }}>
              {b.odds_american > 0 ? `+${b.odds_american}` : b.odds_american}
            </span>
          )}
          <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)" }}>{b.stake_units}u</span>
          <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
            {(["won", "lost", "pending"] as const).map(o => (
              <button key={o} onClick={() => patch(b.id, { outcome: o })} style={{
                ...btnQuiet, padding: "3px 9px", fontSize: "max(var(--fs-min), 0.72em)",
                color: b.outcome === o
                  ? (o === "won" ? "var(--bc-green)" : o === "lost" ? "var(--bc-red-text)" : "var(--bc-text)")
                  : "var(--bc-muted)",
                borderColor: b.outcome === o ? "currentColor" : "var(--bc-line)",
              }}>
                {o}
              </button>
            ))}
            <button onClick={() => patch(b.id, { shared: !b.shared })} title="Visible to your groups?" style={{
              ...btnQuiet, padding: "3px 9px", fontSize: "max(var(--fs-min), 0.72em)",
              color: b.shared ? "var(--bc-text)" : "var(--bc-muted)",
              borderColor: b.shared ? "currentColor" : "var(--bc-line)",
            }}>
              {b.shared ? "shared" : "private"}
            </button>
            <button onClick={() => del(b.id)} aria-label="Delete bet" style={{
              ...btnQuiet, padding: "3px 9px", fontSize: "max(var(--fs-min), 0.72em)" }}>✕</button>
          </span>
        </div>
      ))}
    </>
  );
}
