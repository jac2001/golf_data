"use client";

/**
 * LeagueRetro — the 2026 league season, retired into the main app.
 * The league zone's wrap + ladder + miss ledger, re-tokened from lg-*
 * to bc-*: same structure, main design system. Gated by the SERVER
 * (see /history/league/page.tsx) — this component just renders.
 */

import React, { useEffect, useState } from "react";
import { getFantasyStrategy, FantasyStrategy, getSeasonWrap, SeasonWrap } from "@/lib/api";

const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 10, padding: 20, marginBottom: 20,
};
const cell: React.CSSProperties = {
  padding: "8px 12px", borderBottom: "1px solid var(--bc-line)",
  fontSize: "0.84em", color: "var(--bc-text)", textAlign: "left",
};
const hdr: React.CSSProperties = {
  ...cell, color: "var(--bc-muted)", fontWeight: 600, fontSize: "0.76em",
  textTransform: "uppercase", letterSpacing: "0.04em",
};
const num: React.CSSProperties = { ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" };

const money = (v: number | null | undefined) =>
  v == null ? "—" : v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

export default function LeagueRetro() {
  const [w, setW] = useState<SeasonWrap | null>(null);
  const [s, setS] = useState<FantasyStrategy | null>(null);

  useEffect(() => {
    getSeasonWrap().then(setW).catch(() => {});
    getFantasyStrategy().then(setS).catch(() => {});
  }, []);

  if (!w?.my_team) return <p style={{ color: "var(--bc-muted)" }}>Loading the season…</p>;

  const champion = w.my_team.place === "1st";

  // The climb, as one SVG polyline (see the fantasy original — identical math).
  const W = 900, H = 120, pad = 4;
  const maxCum = Math.max(...w.weekly.map(p => p.cumulative), 1);
  const pts = w.weekly.map((p, i) =>
    `${(pad + (i / Math.max(w.weekly.length - 1, 1)) * (W - 2 * pad)).toFixed(1)},` +
    `${(H - pad - (p.cumulative / maxCum) * (H - 2 * pad)).toFixed(1)}`).join(" ");

  return (
    <>
      {/* Championship banner */}
      <div style={{ ...card, border: "1px solid var(--bc-yellow)",
        background: "color-mix(in srgb, var(--bc-yellow) 7%, var(--bc-card))" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.72em", fontWeight: 800, letterSpacing: "0.14em",
            textTransform: "uppercase", color: "var(--bc-yellow)" }}>
            {w.season} League Season
          </span>
          {champion && <span style={{ fontSize: "0.72em", fontWeight: 800, letterSpacing: "0.1em",
            color: "#081f14", background: "var(--bc-yellow)", borderRadius: 3, padding: "2px 8px",
            textTransform: "uppercase" }}>Champions</span>}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: "2em", fontWeight: 900 }}>{w.my_team.team}</span>
          <span style={{ fontSize: "1.4em", fontWeight: 800, color: "var(--bc-yellow)",
            fontVariantNumeric: "tabular-nums" }}>{money(w.total)}</span>
          {champion && w.margin != null && (
            <span style={{ color: "var(--bc-muted)", fontSize: "0.88em" }}>
              won by {money(Math.abs(w.margin))}
            </span>
          )}
        </div>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.84em", marginTop: 6, lineHeight: 1.5 }}>
          {w.weeks} weeks · {w.total_uses} uses · {money(w.per_use)} per use · {w.bust_count} busts —
          and {w.wins === 0
            ? "not a single weekly win: a championship built entirely on never having a bad Sunday."
            : `${w.wins} weekly win${w.wins === 1 ? "" : "s"}.`}
        </div>
      </div>

      {/* The climb */}
      <div style={card}>
        <div style={{ fontWeight: 700, marginBottom: 2 }}>The Climb</div>
        <div style={{ color: "var(--bc-muted)", fontSize: "0.78em", marginBottom: 10 }}>
          cumulative earnings, week 1 → {w.weeks}
          {w.best_week && <> · biggest week: {w.best_week.tournament} ({money(w.best_week.earnings)})</>}
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
          <polyline points={pts} fill="none" stroke="var(--bc-yellow)" strokeWidth="2.5"
            strokeLinejoin="round" strokeLinecap="round" />
          {w.weekly.map((p, i) => p.week === w.best_week?.week ? (
            <circle key={i} r="4" fill="var(--bc-green)"
              cx={pad + (i / Math.max(w.weekly.length - 1, 1)) * (W - 2 * pad)}
              cy={H - pad - (p.cumulative / maxCum) * (H - 2 * pad)} />
          ) : null)}
        </svg>
      </div>

      <div style={{ display: "grid", gap: 20, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", marginBottom: 20 }}>
        {/* Final table */}
        <div style={{ ...card, marginBottom: 0 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Final Table</div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {w.standings.map(t => (
                <tr key={t.team} style={{ background: t.team === w.my_team!.team
                  ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, color: "var(--bc-muted)", width: 40 }}>{t.place}</td>
                  <td style={{ ...cell, fontWeight: 600 }}>
                    {t.team} <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "0.85em" }}>{t.owner}</span>
                  </td>
                  <td style={num}>{money(t.earnings)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Fame + stars */}
        <div style={{ ...card, marginBottom: 0 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>Hall of Fame Picks</div>
          {w.best_picks.map(p => (
            <div key={p.player + p.week} style={{ display: "flex", gap: 8, fontSize: "0.84em",
              padding: "4px 0", borderBottom: "1px solid var(--bc-line)" }}>
              <span style={{ fontWeight: 600 }}>{p.player}</span>
              <span style={{ color: "var(--bc-muted)" }}>{p.tournament} · {p.result}</span>
              <span style={{ marginLeft: "auto", color: "var(--bc-yellow)", fontWeight: 700,
                fontVariantNumeric: "tabular-nums" }}>{money(p.earnings)}</span>
            </div>
          ))}
          <div style={{ fontWeight: 700, margin: "14px 0 8px" }}>Stars, by the numbers</div>
          {w.stars.slice(0, 5).map(st => (
            <div key={st.player} style={{ display: "flex", gap: 8, fontSize: "0.82em", padding: "3px 0" }}>
              <span>{st.player}</span>
              <span style={{ color: "var(--bc-muted)" }}>{st.uses} use{st.uses === 1 ? "" : "s"}</span>
              <span style={{ marginLeft: "auto", color: "var(--bc-muted)", fontVariantNumeric: "tabular-nums" }}>
                {money(st.earnings)} · {money(st.per_use)}/use
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Ladder + miss ledger — only when the strategy payload loads */}
      {s && (
        <>
          <div style={card}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>The 2026 Ladder</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.78em", marginBottom: 14 }}>{s.ladder.note}</div>
            {[
              { label: "Static preseason plan", v: s.ladder.static_plan },
              { label: "Rolling replay", v: s.ladder.rolling_replay },
              { label: "WineTime actual", v: s.ladder.jack_actual },
              { label: "Hindsight-perfect", v: s.ladder.hindsight_ceiling },
            ].map(r => (
              <div key={r.label} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.84em" }}>
                  <span style={{ color: r.label.includes("WineTime") ? "var(--bc-yellow)" : "var(--bc-text)" }}>{r.label}</span>
                  <span style={{ fontVariantNumeric: "tabular-nums" }}>{money(r.v)}</span>
                </div>
                <div style={{ background: "var(--bc-panel)", borderRadius: 3, height: 7, marginTop: 3 }}>
                  <div style={{ width: `${(r.v / s.ladder.hindsight_ceiling) * 100}%`, height: "100%",
                    borderRadius: 3, background: "var(--bc-yellow)" }} />
                </div>
              </div>
            ))}
          </div>

          <div style={{ ...card, overflowX: "auto" }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Miss Ledger — you vs the machine</div>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr>
                <th style={hdr}>Week</th><th style={hdr}>Your picks</th>
                <th style={{ ...hdr, textAlign: "right" }}>You</th>
                <th style={hdr}>Suggestion</th>
                <th style={{ ...hdr, textAlign: "right" }}>Suggestion $</th>
                <th style={{ ...hdr, textAlign: "right" }}>Delta</th>
              </tr></thead>
              <tbody>
                {s.ledger.map(r => (
                  <tr key={r.tid}>
                    <td style={cell}>{r.date}</td>
                    <td style={{ ...cell, fontSize: "0.78em" }}>{r.jack_picks || "—"}</td>
                    <td style={num}>{money(r.jack_earn)}</td>
                    <td style={{ ...cell, fontSize: "0.78em", color: "var(--bc-muted)" }}>{r.replay_picks}</td>
                    <td style={num}>{money(r.replay_earn)}</td>
                    <td style={{ ...num, color: r.delta == null ? "var(--bc-muted)"
                      : r.delta > 0 ? "var(--bc-green)" : "var(--bc-red-text)" }}>
                      {r.delta == null ? "—" : (r.delta > 0 ? "+" : "−") + money(Math.abs(r.delta))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}