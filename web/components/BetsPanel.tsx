"use client";

/**
 * BetsPanel — the graded-bet ledger, shared by the Betting Board (primary
 * home) and the legacy History page. The tracked bet slip (one shared file
 * every visitor could change) was retired Oct 20, 2026; Tail replaced it.
 * Extracted verbatim from history/page.tsx during the Broadcast merge.
 */

import React, { useState, useEffect } from "react";
import { getHistoryBets, HistoryBetsResponse } from "@/lib/api";

const cell: React.CSSProperties = {
  padding: "9px 12px", borderBottom: "1px solid var(--bc-line)", textAlign: "left",
  fontSize: "max(var(--fs-min), 0.84em)", color: "var(--bc-text)",
};
const hdr: React.CSSProperties = {
  ...cell, color: "var(--bc-muted)", fontWeight: 600, fontSize: "max(var(--fs-min), 0.78em)",
  textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid var(--bc-line)",
};
function pnlColor(v: number) { return v > 0 ? "var(--bc-green)" : v < 0 ? "var(--bc-red)" : "var(--bc-muted)"; }

// ── Bets Tab ──────────────────────────────────────────────────────────────────
function BetsTab() {
  const [data, setData]       = useState<HistoryBetsResponse | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    getHistoryBets().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ color: "var(--bc-muted)", padding: 24 }}>Loading...</p>;
  if (!data?.tournaments.length) return <p style={{ color: "var(--bc-muted)", padding: 24 }}>No graded bets yet.</p>;

  const ov = data.overall;

  return (
    <div>
      {/* Overall summary strip */}
      <div style={{
        display: "flex", gap: 24, padding: "12px 16px", marginBottom: 20,
        background: "var(--bc-panel)", borderRadius: 8, border: "1px solid var(--bc-line)",
        flexWrap: "wrap",
      }}>
        {[
          { label: "Total Bets", value: ov.bets },
          { label: "Wins", value: `${ov.wins} (${ov.bets ? ((ov.wins / ov.bets) * 100).toFixed(0) : 0}%)` },
          { label: "P&L", value: `${ov.pnl >= 0 ? "+" : ""}${ov.pnl.toFixed(2)}u`, color: pnlColor(ov.pnl) },
          { label: "ROI", value: `${ov.roi >= 0 ? "+" : ""}${ov.roi.toFixed(1)}%`, color: pnlColor(ov.roi) },
        ].map(s => (
          <div key={s.label}>
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)", marginBottom: 2 }}>{s.label}</div>
            <div style={{ color: s.color ?? "var(--bc-text)", fontWeight: 700, fontSize: "1.1em" }}>{s.value}</div>
          </div>
        ))}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Tournament", "Bets", "Wins", "P&L", "ROI"].map(h => (
              <th key={h} style={hdr}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.tournaments.map(t => (
            <React.Fragment key={t.tournament_id}>
              <tr
                style={{ cursor: "pointer", background: expanded === t.tournament_id ? "var(--bc-hover)" : "transparent" }}
                onClick={() => setExpanded(expanded === t.tournament_id ? null : t.tournament_id)}
              >
                <td style={{ ...cell, color: "var(--bc-text)", fontWeight: 600 }}>{t.name}</td>
                <td style={cell}>{t.bets}</td>
                <td style={cell}>{t.wins}</td>
                <td style={{ ...cell, color: pnlColor(t.pnl) }}>
                  {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}u
                </td>
                <td style={{ ...cell, color: pnlColor(t.roi) }}>
                  {t.roi >= 0 ? "+" : ""}{t.roi.toFixed(1)}%
                </td>
              </tr>
              {expanded === t.tournament_id && (
                <tr>
                  <td colSpan={5} style={{ background: "var(--bc-panel)", padding: "12px 24px" }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {t.markets.map(m => (
                        <span key={m.market} style={{
                          background: "var(--bc-card)", border: "1px solid var(--bc-line)",
                          borderRadius: 6, padding: "4px 10px", fontSize: "max(var(--fs-min), 0.82em)",
                        }}>
                          <span style={{ color: "var(--bc-muted)" }}>{m.market}</span>
                          {" "}{m.wins}/{m.bets}
                          {" "}<span style={{ color: pnlColor(m.pnl) }}>
                            {m.pnl >= 0 ? "+" : ""}{m.pnl.toFixed(2)}u
                          </span>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { BetsTab as BetsLedger };
