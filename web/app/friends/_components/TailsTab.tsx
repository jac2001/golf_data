"use client";

/**
 * My Tails: the model bets this person has tailed.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useEffect, useState } from "react";
import { Tail, card, cell, hdr, useApi } from "./shared";

// ── My Tails ─────────────────────────────────────────────────────────────────

export function TailsTab() {
  const api = useApi();
  const [tails, setTails] = useState<Tail[] | null>(null);
  const [summary, setSummary] = useState<{ pnl: number; settled: number; won: number } | null>(null);

  useEffect(() => {
    api("/api/friends/tail")
      .then(d => { setTails((d.tails as Tail[]) ?? []); setSummary((d.summary as { pnl: number; settled: number; won: number }) ?? null); })
      .catch(() => setTails([]));
  }, [api]);

  if (!tails) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (tails.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        You haven&apos;t tailed any bets yet. Hit &quot;Tail&quot; on a card on the
        Betting Board and your record shows up here — graded by the same honest
        ledger the public site uses.
      </p>
    </div>
  );

  return (
    <>
      {summary && summary.settled > 0 && (
        <div style={{ ...card, display: "flex", gap: 28 }}>
          <div>
            <div style={{ fontWeight: 900, fontSize: "1.3em",
              color: summary.pnl >= 0 ? "var(--bc-green)" : "var(--bc-red-text)" }}>
              {summary.pnl >= 0 ? "+" : ""}{summary.pnl.toFixed(2)}u
            </div>
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.72em)" }}>NET P&L</div>
          </div>
          <div>
            <div style={{ fontWeight: 900, fontSize: "1.3em" }}>{summary.won}/{summary.settled}</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.72em)" }}>SETTLED WINS</div>
          </div>
        </div>
      )}
      <div style={{ ...card, padding: 0, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={hdr}>Bet</th><th style={hdr}>Event</th>
            <th style={{ ...hdr, textAlign: "right" }}>Odds</th>
            <th style={{ ...hdr, textAlign: "right" }}>Stake</th>
            <th style={{ ...hdr, textAlign: "right" }}>Result</th>
          </tr></thead>
          <tbody>
            {tails.map(t => (
              <tr key={t.recommendation_id}>
                <td style={cell}>{t.label}</td>
                <td style={{ ...cell, color: "var(--bc-muted)" }}>{t.tournament_id}</td>
                <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {t.odds_american != null ? (t.odds_american > 0 ? `+${t.odds_american}` : t.odds_american) : "—"}
                </td>
                <td style={{ ...cell, textAlign: "right" }}>{t.stake_units}u</td>
                <td style={{ ...cell, textAlign: "right", fontWeight: 700,
                  color: t.outcome === "won" ? "var(--bc-green)"
                       : t.outcome === "lost" ? "var(--bc-red-text)" : "var(--bc-muted)" }}>
                  {t.outcome === "pending" ? "pending"
                    : `${t.outcome}${t.pnl != null ? ` (${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}u)` : ""}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
