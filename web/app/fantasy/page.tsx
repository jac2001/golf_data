"use client";

/**
 * fantasy/page.tsx — Strategy Mode (Tuesday decision-support)
 * ============================================================
 * Normal predictions stay untouched elsewhere; this tab answers the
 * league question: who should WE play this week, and what does using a
 * star now cost us later? Offseason it renders the 2026 retrospective
 * (the ladder + the weekly miss ledger) and the 2027 season map the
 * optimizer will plan over. The suggested-trio panel activates in-season.
 */

import React, { useEffect, useState } from "react";
import { getFantasyStrategy, FantasyStrategy } from "@/lib/api";
import { PageHead } from "@/components/broadcast";

/** Full-bleed charcoal zone: cancels main's padding, repaints, restores it. */
const zoneWrap: React.CSSProperties = {
  margin: "-24px -24px -48px",
  padding: "24px 24px 48px",
  minHeight: "calc(100vh - 56px)",
};

const cell: React.CSSProperties = {
  padding: "8px 12px", borderBottom: "1px solid var(--lg-line)", textAlign: "left",
  fontSize: "0.84em", color: "var(--lg-text)",
};
const hdr: React.CSSProperties = {
  ...cell, color: "var(--lg-muted)", fontWeight: 600, fontSize: "0.76em",
  textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid var(--lg-line)",
};
const num: React.CSSProperties = { ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" };
const card: React.CSSProperties = {
  background: "var(--lg-card)", border: "1px solid var(--lg-line)", borderRadius: 8, padding: 16,
};

function money(v: number | null | undefined): string {
  if (v == null) return "—";
  return v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v / 1000)}K`;
}
function deltaColor(v: number | null): string {
  if (v == null) return "var(--lg-muted)";
  return v > 0 ? "var(--lg-accent)" : v < 0 ? "var(--negative)" : "var(--lg-muted)";
}

export default function FantasyPage() {
  const [data, setData] = useState<FantasyStrategy | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getFantasyStrategy().then(setData).catch(e => setErr(String(e)));
  }, []);

  if (err) return <div data-zone="league" style={{ ...zoneWrap, color: "var(--negative)" }}>Failed to load: {err}</div>;
  if (!data) return <div data-zone="league" style={{ ...zoneWrap, color: "var(--lg-muted)" }}>Loading strategy…</div>;

  const L = data.ladder;
  const rungs = [
    { label: "Static preseason plan", v: L.static_plan, hint: "optimizer, frozen in January" },
    { label: "Rolling replay", v: L.rolling_replay, hint: "strategy mode, Tuesday knowledge only" },
    { label: "WineTime actual", v: L.jack_actual, hint: "3rd of 10 — champion 2024 & 2025" },
    { label: "Hindsight-perfect", v: L.hindsight_ceiling, hint: "theoretical ceiling" },
  ];
  const max = L.hindsight_ceiling;
  const jackWins = data.ledger.filter(r => (r.delta ?? 0) > 0).length;

  return (
    <div data-zone="league" style={zoneWrap}>
    <div style={{ maxWidth: 980, margin: "0 auto" }}>
      <PageHead
        zone="league"
        kicker="Tuesday decision support · the model advises, you decide"
        title="The Tuesday Call"
      />

      {/* Suggested trio: in-season panel / offseason notice */}
      <div style={{ ...card, marginBottom: 20 }}>
        <div style={{ color: "var(--lg-text)", fontWeight: 600, marginBottom: 6 }}>This Week&apos;s Suggestion</div>
        {data.suggested_trio ? (
          <div style={{ color: "var(--lg-text)" }}>{JSON.stringify(data.suggested_trio)}</div>
        ) : (
          <div style={{ color: "var(--lg-muted)", fontSize: "0.88em" }}>{data.trio_status}</div>
        )}
      </div>

      {/* The ladder */}
      <div style={{ ...card, marginBottom: 20 }}>
        <div style={{ color: "var(--lg-text)", fontWeight: 600, marginBottom: 4 }}>The 2026 Ladder</div>
        <div style={{ color: "var(--lg-muted)", fontSize: "0.78em", marginBottom: 14 }}>{L.note}</div>
        {rungs.map(r => (
          <div key={r.label} style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.84em" }}>
              <span style={{ color: r.label.includes("WineTime") ? "var(--lg-accent)" : "var(--lg-text)" }}>
                {r.label} <span style={{ color: "var(--lg-muted)", fontSize: "0.85em" }}>· {r.hint}</span>
              </span>
              <span style={{ color: "var(--lg-text)", fontVariantNumeric: "tabular-nums" }}>{money(r.v)}</span>
            </div>
            <div style={{ background: "var(--lg-panel)", borderRadius: 3, height: 7, marginTop: 3 }}>
              <div style={{
                width: `${(r.v / max) * 100}%`, height: "100%", borderRadius: 3,
                background: r.label.includes("WineTime") ? "var(--lg-accent)"
                  : r.label.includes("Hindsight") ? "var(--bc-yellow)" : "var(--lg-accent)",
              }} />
            </div>
          </div>
        ))}
      </div>

      {/* Miss ledger */}
      <div style={{ ...card, marginBottom: 20, overflowX: "auto" }}>
        <div style={{ color: "var(--lg-text)", fontWeight: 600, marginBottom: 4 }}>
          2026 Miss Ledger — you vs the machine, week by week
        </div>
        <div style={{ color: "var(--lg-muted)", fontSize: "0.78em", marginBottom: 10 }}>
          You won {jackWins} of {data.ledger.length} weeks. Green delta = your lineup beat the
          Tuesday suggestion; the machine&apos;s wins were mostly third-slot swaps.
        </div>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>Week</th><th style={hdr}>Your picks</th>
            <th style={{ ...hdr, textAlign: "right" }}>You</th>
            <th style={hdr}>Suggestion</th>
            <th style={{ ...hdr, textAlign: "right" }}>Suggestion $</th>
            <th style={{ ...hdr, textAlign: "right" }}>Delta</th>
          </tr></thead>
          <tbody>
            {data.ledger.map(r => (
              <tr key={r.tid}>
                <td style={cell}>{r.date}</td>
                <td style={{ ...cell, fontSize: "0.78em" }}>{r.jack_picks || "—"}</td>
                <td style={num}>{money(r.jack_earn)}</td>
                <td style={{ ...cell, fontSize: "0.78em", color: "var(--lg-muted)" }}>{r.replay_picks}</td>
                <td style={num}>{money(r.replay_earn)}</td>
                <td style={{ ...num, color: deltaColor(r.delta) }}>
                  {r.delta == null ? "—" : (r.delta > 0 ? "+" : "") + money(Math.abs(r.delta)).replace("$", "$")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 2027 season map */}
      <div style={{ ...card, overflowX: "auto" }}>
        <div style={{ color: "var(--lg-text)", fontWeight: 600, marginBottom: 4 }}>2027 Season Map</div>
        <div style={{ color: "var(--lg-muted)", fontSize: "0.78em", marginBottom: 10 }}>
          The calendar the optimizer plans over. Italic purses are estimates until announced.
        </div>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>Wk</th><th style={hdr}>Date</th><th style={hdr}>Tournament</th>
            <th style={hdr}>Type</th><th style={hdr}>Course</th>
            <th style={{ ...hdr, textAlign: "right" }}>Purse</th>
          </tr></thead>
          <tbody>
            {data.season_map.map(e => (
              <tr key={e.week}>
                <td style={cell}>{e.week}</td>
                <td style={cell}>{e.start_date}</td>
                <td style={{ ...cell, color: e.type === "Major" ? "var(--bc-yellow)"
                  : e.type === "Signature" ? "var(--lg-accent)"
                  : e.type === "Playoff" ? "var(--lg-accent)" : "var(--lg-text)" }}>{e.name}</td>
                <td style={cell}>{e.type}</td>
                <td style={{ ...cell, fontSize: "0.78em", color: "var(--lg-muted)" }}>{e.course}</td>
                <td style={{ ...num, fontStyle: e.purse_source !== "carried_forward" ? "italic" : "normal" }}>
                  {money(e.purse)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    </div>
  );
}
