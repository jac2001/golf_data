"use client";

/**
 * BetsPanel — graded-bet ledger + tracked bet slip, shared by the
 * Betting Board (primary home) and the legacy History page until retired.
 * Extracted verbatim from history/page.tsx during the Broadcast merge.
 */

import React, { useState, useEffect } from "react";
import {
  getHistoryBets, getBetSlip, removeFromBetSlip,
  HistoryBetsResponse, SlipBet, SlipStats, TournamentPnl,
} from "@/lib/api";

const cell: React.CSSProperties = {
  padding: "9px 12px", borderBottom: "1px solid var(--bc-line)", textAlign: "left",
  fontSize: "0.84em", color: "var(--bc-text)",
};
const hdr: React.CSSProperties = {
  ...cell, color: "var(--bc-muted)", fontWeight: 600, fontSize: "0.78em",
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
            <div style={{ color: "var(--bc-muted)", fontSize: "0.75em", marginBottom: 2 }}>{s.label}</div>
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
                style={{ cursor: "pointer", background: expanded === t.tournament_id ? "#0f1e2e" : "transparent" }}
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
                          background: "#111e2c", border: "1px solid var(--bc-line)",
                          borderRadius: 6, padding: "4px 10px", fontSize: "0.82em",
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

// ── My Slip Tab ───────────────────────────────────────────────────────────────
const MARKET_LABELS: Record<string, string> = {
  top10: "Top 10", top5: "Top 5", top20: "Top 20",
  make_cut: "Make Cut", outright: "Win",
  h2h: "H2H", h2h_r1: "R1 H2H", h2h_r2: "R2 H2H", h2h_r3: "R3 H2H", h2h_r4: "R4 H2H",
};

function SlipStatsStrip({ stats }: { stats: SlipStats }) {
  const hasBankroll = stats.starting_bankroll != null;
  const pnlDollars  = stats.total_pnl_dollars ?? 0;

  const statItems = [
    { label: "Tracked",  value: String(stats.total_bets) },
    { label: "Pending",  value: String(stats.pending) },
    { label: "Won",      value: `${stats.won} / ${stats.graded}`, color: stats.won > 0 ? "var(--bc-green)" : undefined },
    { label: "P&L",
      value: stats.total_pnl != null ? `${stats.total_pnl >= 0 ? "+" : ""}${stats.total_pnl.toFixed(2)}u` : "—",
      color: stats.total_pnl != null ? pnlColor(stats.total_pnl) : undefined },
    { label: "ROI",
      value: stats.roi_pct != null ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct.toFixed(1)}%` : "—",
      color: stats.roi_pct != null ? pnlColor(stats.roi_pct) : undefined },
    { label: "Hit Rate", value: stats.hit_rate != null ? `${stats.hit_rate.toFixed(0)}%` : "—" },
  ];

  return (
    <div style={{ marginBottom: 20 }}>
      {/* Main stats row */}
      <div style={{
        display: "flex", gap: 16, flexWrap: "wrap",
        padding: "14px 16px",
        background: "var(--bc-panel)", borderRadius: hasBankroll ? "8px 8px 0 0" : 8,
        borderTop: "1px solid var(--bc-line)", borderLeft: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)",
        borderBottom: hasBankroll ? "none" : "1px solid var(--bc-line)",
      }}>
        {statItems.map(s => (
          <div key={s.label} style={{ minWidth: 70 }}>
            <div style={{ color: "var(--bc-muted)", fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>{s.label}</div>
            <div style={{ color: s.color ?? "var(--bc-text)", fontWeight: 700, fontSize: "1.05em" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Bankroll row — only shown when configured */}
      {hasBankroll && (
        <div style={{
          display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap",
          padding: "10px 16px",
          background: "#070f18", borderRadius: "0 0 8px 8px",
          borderLeft: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)",
          borderTop: "1px solid #0d2030",
        }}>
          <div>
            <span style={{ color: "var(--bc-muted)", fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em" }}>Bankroll</span>
            {" "}
            <span style={{ color: "var(--bc-muted)", fontSize: "0.82em" }}>${stats.starting_bankroll?.toLocaleString()}</span>
            <span style={{ color: "var(--bc-line)", fontSize: "0.82em", margin: "0 6px" }}>→</span>
            <span style={{ color: pnlColor(pnlDollars), fontWeight: 700, fontSize: "1.05em" }}>
              ${stats.current_bankroll?.toLocaleString()}
            </span>
          </div>
          <div style={{ color: pnlColor(pnlDollars), fontSize: "0.88em", fontWeight: 600 }}>
            {pnlDollars >= 0 ? "+" : ""}${pnlDollars.toFixed(2)} season
          </div>
          <div style={{ color: "var(--bc-muted)", fontSize: "0.75em" }}>
            ${stats.unit_size}/unit
          </div>

          {/* Per-tournament mini breakdown */}
          {stats.by_tournament.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginLeft: "auto" }}>
              {stats.by_tournament.map((t: TournamentPnl) => (
                <span key={t.tid} style={{
                  background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
                  borderRadius: 5, padding: "3px 8px", fontSize: "0.75em",
                }}>
                  <span style={{ color: "var(--bc-muted)" }}>{t.tid.replace("R2026", "")}</span>
                  {" "}
                  <span style={{ color: pnlColor(t.pnl_dollars), fontWeight: 600 }}>
                    {t.pnl_dollars >= 0 ? "+" : ""}${t.pnl_dollars.toFixed(0)}
                  </span>
                  <span style={{ color: "var(--bc-line)" }}> {t.won}/{t.total}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LiveStatusDot({ status }: { status: SlipBet["live_status"] }) {
  if (!status) return null;
  const color = status === "on_track"  ? "var(--bc-green)"
              : status === "marginal"  ? "var(--warning)"
              : status === "off_track" ? "#e05555"
              : "#5a7a9a"; // tracking / finished
  return (
    <span style={{
      display: "inline-block", width: 7, height: 7, borderRadius: "50%",
      background: color, marginRight: 5, verticalAlign: "middle", flexShrink: 0,
    }} />
  );
}

function SlipRow({ bet, onRemove }: { bet: SlipBet; onRemove: (id: string) => void }) {
  const isPending = bet.outcome_status === "pending";
  const isWon     = bet.outcome_status === "won";
  const isLost    = bet.outcome_status === "lost";

  const hasLive   = isPending && !!bet.live_position;
  const scoreNum  = bet.live_total ? parseFloat(bet.live_total) : null;
  const scoreColor = scoreNum != null && scoreNum < 0 ? "var(--bc-green)"
                   : scoreNum != null && scoreNum > 0 ? "#e05555"
                   : "var(--bc-text)";

  const rowBg = isWon    ? "#071410"
              : isLost   ? "#130a0a"
              : hasLive && bet.live_status === "on_track"  ? "#071a10"
              : hasLive && bet.live_status === "off_track" ? "#180a0a"
              : "transparent";

  const odds = bet.odds_american >= 0 ? `+${bet.odds_american}` : String(bet.odds_american);

  return (
    <tr style={{ background: rowBg }}>
      <td style={cell}>{bet.tournament_id?.replace("R2026", "") ?? "—"}</td>
      <td style={{ ...cell, color: "var(--bc-text)", fontWeight: 600, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {bet.player_name}
      </td>
      <td style={cell}>{MARKET_LABELS[bet.market] ?? bet.market}</td>
      <td style={{ ...cell, color: "var(--bc-muted)" }}>{odds}</td>

      {/* Result column: live context for pending bets, or Won/Lost */}
      <td style={cell}>
        {isWon  && <span style={{ color: "var(--bc-green)", fontWeight: 700 }}>Won</span>}
        {isLost && <span style={{ color: "#e05555", fontWeight: 700 }}>Lost</span>}
        {isPending && hasLive && (
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
            <LiveStatusDot status={bet.live_status} />
            <span style={{ color: "var(--bc-text)", fontWeight: 700, fontSize: "0.95em" }}>
              {bet.live_position}
            </span>
            <span style={{ color: scoreColor, fontWeight: 700, fontSize: "0.95em" }}>
              {bet.live_total ?? "E"}
            </span>
            <span style={{ color: "var(--bc-muted)", fontSize: "0.82em" }}>
              {bet.live_thru === "F" ? "F" : bet.live_thru ? `thru ${bet.live_thru}` : ""}
            </span>
          </div>
        )}
        {isPending && !hasLive && (
          <span style={{ color: "var(--warning)" }}>Pending</span>
        )}
      </td>

      <td style={{ ...cell, color: bet.pnl_usd != null ? pnlColor(bet.pnl_usd) : "var(--bc-muted)" }}>
        {bet.pnl_usd != null ? `${bet.pnl_usd >= 0 ? "+" : ""}${bet.pnl_usd.toFixed(2)}u` : "—"}
      </td>
      <td style={{ ...cell, textAlign: "center" }}>
        {isPending && (
          <button
            onClick={() => onRemove(bet.id)}
            style={{
              background: "transparent", border: "1px solid var(--bc-line)",
              borderRadius: 4, color: "var(--bc-muted)", fontSize: "0.72em",
              padding: "2px 8px", cursor: "pointer",
            }}
          >
            Remove
          </button>
        )}
      </td>
    </tr>
  );
}

const REFRESH_MS = 2 * 60 * 1000; // 2 minutes

function MySlipTab() {
  const [bets,      setBets]      = useState<SlipBet[]>([]);
  const [stats,     setStats]     = useState<SlipStats | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  // Silently refresh without showing full loading state (avoids flicker on interval)
  function refresh(showLoader = false) {
    if (showLoader) setLoading(true);
    getBetSlip()
      .then(r => { setBets(r.bets); setStats(r.stats); setUpdatedAt(new Date()); })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh(true); // initial load shows spinner

    // Poll every 2 min, but only when the tab is visible
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, REFRESH_MS);

    return () => clearInterval(id); // cleanup when component unmounts
  }, []);

  async function handleRemove(id: string) {
    await removeFromBetSlip(id);
    refresh();
  }

  if (loading) return <p style={{ color: "var(--bc-muted)", padding: 24 }}>Loading…</p>;

  if (!bets.length) return (
    <div style={{ padding: 40, textAlign: "center", color: "var(--bc-muted)" }}>
      <div style={{ fontSize: "1.1em", marginBottom: 8, color: "var(--bc-muted)" }}>No tracked bets yet</div>
      <div style={{ fontSize: "0.85em" }}>Tap "Track Bet" on any bet card to start logging your picks.</div>
    </div>
  );

  // Group by tournament
  const byTid: Record<string, SlipBet[]> = {};
  for (const b of bets) {
    const key = b.tournament_id ?? "unknown";
    if (!byTid[key]) byTid[key] = [];
    byTid[key].push(b);
  }

  return (
    <div>
      {stats && <SlipStatsStrip stats={stats} />}

      {/* Last updated indicator */}
      {updatedAt && (
        <div style={{ fontSize: "0.72em", color: "var(--bc-line)", marginBottom: 12, paddingLeft: 2 }}>
          Live · updated {updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          <span style={{ color: "#1e3050", marginLeft: 8 }}>auto-refreshes every 2 min</span>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Event", "Player", "Market", "Odds", "Result", "P&L", ""].map(h => (
              <th key={h} style={hdr}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.entries(byTid).map(([tid, tbets]) => (
            <React.Fragment key={tid}>
              {/* Tournament group header */}
              <tr>
                <td colSpan={7} style={{
                  padding: "8px 12px", background: "#081220",
                  color: "var(--bc-muted)", fontSize: "0.75em", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.06em",
                  borderBottom: "1px solid #1a2a3a",
                }}>
                  {tid}
                  <span style={{ marginLeft: 10, color: "var(--bc-line)", fontWeight: 400 }}>
                    {tbets.length} bet{tbets.length !== 1 ? "s" : ""}
                  </span>
                </td>
              </tr>
              {tbets.map(b => (
                <SlipRow key={b.id} bet={b} onRemove={handleRemove} />
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}


export { BetsTab as BetsLedger, MySlipTab as BetSlipPanel };
