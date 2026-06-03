"use client";

import React, { useState, useEffect } from "react";
import {
  getHistoryTournaments, getHistoryModel, getHistoryBets,
  getBetSlip, removeFromBetSlip,
  HistoryTournament, HistoryModelRow, HistoryBetsResponse,
  SlipBet, SlipStats,
} from "@/lib/api";

type Tab = "results" | "model" | "bets" | "slip";

const cell: React.CSSProperties = {
  padding: "9px 12px", borderBottom: "1px solid #1a2a3a", textAlign: "left",
  fontSize: "0.84em", color: "#c8d8e8",
};
const hdr: React.CSSProperties = {
  ...cell, color: "#7a9ab8", fontWeight: 600, fontSize: "0.78em",
  textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid #1e3a5f",
};

function pnlColor(v: number) { return v > 0 ? "#00c44f" : v < 0 ? "#e05555" : "#7a9ab8"; }
function corrColor(v: number | null) {
  if (v === null) return "#7a9ab8";
  return v >= 0.5 ? "#00c44f" : v >= 0.3 ? "#f0c040" : "#e05555";
}

// ── Results Tab ───────────────────────────────────────────────────────────────
function ResultsTab() {
  const [data, setData]     = useState<HistoryTournament[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    getHistoryTournaments().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading...</p>;
  if (!data?.length) return <p style={{ color: "#7a9ab8", padding: 24 }}>No results yet.</p>;

  return (
    <div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Date", "Tournament", "Winner", "Score", "Earnings", "Field"].map(h => (
              <th key={h} style={hdr}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(t => (
            <React.Fragment key={t.tournament_id}>
              <tr
                style={{ cursor: "pointer", background: expanded === t.tournament_id ? "#0f1e2e" : "transparent" }}
                onClick={() => setExpanded(expanded === t.tournament_id ? null : t.tournament_id)}
              >
                <td style={cell}>{t.start_date?.slice(0, 10) ?? ""}</td>
                <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>{t.name}</td>
                <td style={{ ...cell, color: "#00c44f" }}>{t.winner}</td>
                <td style={{ ...cell, color: "#f0c040" }}>{t.winner_score}</td>
                <td style={cell}>{t.winner_earnings}</td>
                <td style={cell}>{t.field_size}</td>
              </tr>
              {expanded === t.tournament_id && (
                <tr>
                  <td colSpan={6} style={{ background: "#0a1720", padding: "12px 24px" }}>
                    {/* Recap narrative */}
                    {t.recap && (
                      <p style={{
                        color: "#b0c8e0", fontSize: "0.85em", lineHeight: 1.6,
                        margin: "0 0 14px", borderLeft: "2px solid #00c44f",
                        paddingLeft: 12, fontStyle: "italic",
                      }}>
                        {t.recap}
                      </p>
                    )}
                    <p style={{ color: "#7a9ab8", fontSize: "0.8em", marginBottom: 8 }}>Top 10</p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {t.top10.map((p, i) => (
                        <span key={i} style={{
                          background: i === 0 ? "#0d2e18" : "#111e2c",
                          border: `1px solid ${i === 0 ? "#00c44f" : "#1e3a5f"}`,
                          borderRadius: 6, padding: "4px 10px",
                          fontSize: "0.82em", color: i === 0 ? "#00c44f" : "#c8d8e8",
                        }}>
                          {p.position} {p.player} <span style={{ color: "#f0c040" }}>{p.to_par}</span>
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

// ── Model Tab ─────────────────────────────────────────────────────────────────
function ModelTab() {
  const [data, setData]   = useState<HistoryModelRow[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHistoryModel().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading...</p>;
  if (!data?.length) return <p style={{ color: "#7a9ab8", padding: 24 }}>No model results yet.</p>;

  function calibBadge(pred: number, actual: number | null) {
    if (actual === null) return <span style={{ color: "#7a9ab8" }}>—</span>;
    const ratio = actual / pred;
    const col = ratio >= 0.85 && ratio <= 1.15 ? "#00c44f" : ratio >= 0.7 && ratio <= 1.3 ? "#f0c040" : "#e05555";
    return <span style={{ color: col }}>{actual.toFixed(1)}% <span style={{ color: "#555", fontSize: "0.85em" }}>({ratio.toFixed(2)}x)</span></span>;
  }

  return (
    <div>
      <p style={{ color: "#7a9ab8", fontSize: "0.82em", padding: "8px 0 16px", marginTop: 0 }}>
        Calibration ratio: 1.0x = perfect. Actual% / Predicted%. Green = within 15%.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Tournament", "Field", "Win Cal.", "Top 5 Cal.", "Top 10 Cal.", "Rank Corr."].map(h => (
              <th key={h} style={hdr}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map(t => (
            <tr key={t.tournament_id}>
              <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>{t.name}</td>
              <td style={cell}>{t.field_size}</td>
              <td style={cell}>{calibBadge(t.win_pred_avg, t.win_actual_pct)}</td>
              <td style={cell}>{calibBadge(t.top5_pred_avg, t.top5_actual_pct)}</td>
              <td style={cell}>{calibBadge(t.top10_pred_avg, t.top10_actual_pct)}</td>
              <td style={cell}>
                <span style={{ color: corrColor(t.rank_corr) }}>
                  {t.rank_corr !== null ? t.rank_corr.toFixed(3) : "—"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Bets Tab ──────────────────────────────────────────────────────────────────
function BetsTab() {
  const [data, setData]       = useState<HistoryBetsResponse | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    getHistoryBets().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading...</p>;
  if (!data?.tournaments.length) return <p style={{ color: "#7a9ab8", padding: 24 }}>No graded bets yet.</p>;

  const ov = data.overall;

  return (
    <div>
      {/* Overall summary strip */}
      <div style={{
        display: "flex", gap: 24, padding: "12px 16px", marginBottom: 20,
        background: "#0a1720", borderRadius: 8, border: "1px solid #1e3a5f",
        flexWrap: "wrap",
      }}>
        {[
          { label: "Total Bets", value: ov.bets },
          { label: "Wins", value: `${ov.wins} (${ov.bets ? ((ov.wins / ov.bets) * 100).toFixed(0) : 0}%)` },
          { label: "P&L", value: `${ov.pnl >= 0 ? "+" : ""}${ov.pnl.toFixed(2)}u`, color: pnlColor(ov.pnl) },
          { label: "ROI", value: `${ov.roi >= 0 ? "+" : ""}${ov.roi.toFixed(1)}%`, color: pnlColor(ov.roi) },
        ].map(s => (
          <div key={s.label}>
            <div style={{ color: "#7a9ab8", fontSize: "0.75em", marginBottom: 2 }}>{s.label}</div>
            <div style={{ color: s.color ?? "#dde6f5", fontWeight: 700, fontSize: "1.1em" }}>{s.value}</div>
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
                <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>{t.name}</td>
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
                  <td colSpan={5} style={{ background: "#0a1720", padding: "12px 24px" }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {t.markets.map(m => (
                        <span key={m.market} style={{
                          background: "#111e2c", border: "1px solid #1e3a5f",
                          borderRadius: 6, padding: "4px 10px", fontSize: "0.82em",
                        }}>
                          <span style={{ color: "#7a9ab8" }}>{m.market}</span>
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
  return (
    <div style={{
      display: "flex", gap: 16, flexWrap: "wrap",
      padding: "14px 16px", marginBottom: 20,
      background: "#0a1720", borderRadius: 8, border: "1px solid #1e3a5f",
    }}>
      {[
        { label: "Tracked",  value: String(stats.total_bets) },
        { label: "Pending",  value: String(stats.pending) },
        { label: "Won",      value: `${stats.won} / ${stats.graded}`, color: stats.won > 0 ? "#00c44f" : undefined },
        { label: "P&L",      value: stats.total_pnl != null ? `${stats.total_pnl >= 0 ? "+" : ""}${stats.total_pnl.toFixed(2)}u` : "—", color: stats.total_pnl != null ? pnlColor(stats.total_pnl) : undefined },
        { label: "ROI",      value: stats.roi_pct != null ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct.toFixed(1)}%` : "—", color: stats.roi_pct != null ? pnlColor(stats.roi_pct) : undefined },
        { label: "Hit Rate", value: stats.hit_rate != null ? `${stats.hit_rate.toFixed(0)}%` : "—" },
      ].map(s => (
        <div key={s.label} style={{ minWidth: 70 }}>
          <div style={{ color: "#7a9ab8", fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>{s.label}</div>
          <div style={{ color: s.color ?? "#dde6f5", fontWeight: 700, fontSize: "1.05em" }}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

function SlipRow({ bet, onRemove }: { bet: SlipBet; onRemove: (id: string) => void }) {
  const isPending = bet.outcome_status === "pending";
  const isWon     = bet.outcome_status === "won";
  const isLost    = bet.outcome_status === "lost";

  const statusColor = isPending ? "#f39c12" : isWon ? "#00c44f" : "#e05555";
  const statusLabel = isPending ? "Pending" : isWon ? "Won" : "Lost";
  const odds = bet.odds_american >= 0 ? `+${bet.odds_american}` : String(bet.odds_american);

  return (
    <tr style={{ background: isWon ? "#071410" : isLost ? "#130a0a" : "transparent" }}>
      <td style={cell}>{bet.tournament_id?.replace("R2026", "") ?? "—"}</td>
      <td style={{ ...cell, color: "#dde6f5", fontWeight: 600, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {bet.player_name}
      </td>
      <td style={cell}>{MARKET_LABELS[bet.market] ?? bet.market}</td>
      <td style={{ ...cell, color: "#8ba0b8" }}>{odds}</td>
      <td style={{ ...cell, fontWeight: 700, color: statusColor }}>{statusLabel}</td>
      <td style={{ ...cell, color: bet.pnl_usd != null ? pnlColor(bet.pnl_usd) : "#4a6080" }}>
        {bet.pnl_usd != null ? `${bet.pnl_usd >= 0 ? "+" : ""}${bet.pnl_usd.toFixed(2)}u` : "—"}
      </td>
      <td style={{ ...cell, textAlign: "center" }}>
        {isPending && (
          <button
            onClick={() => onRemove(bet.id)}
            style={{
              background: "transparent", border: "1px solid #2a4060",
              borderRadius: 4, color: "#4a6080", fontSize: "0.72em",
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

function MySlipTab() {
  const [bets,    setBets]    = useState<SlipBet[]>([]);
  const [stats,   setStats]   = useState<SlipStats | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    getBetSlip()
      .then(r => { setBets(r.bets); setStats(r.stats); })
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function handleRemove(id: string) {
    await removeFromBetSlip(id);
    load();
  }

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading…</p>;

  if (!bets.length) return (
    <div style={{ padding: 40, textAlign: "center", color: "#4a6080" }}>
      <div style={{ fontSize: "1.1em", marginBottom: 8, color: "#7a9ab8" }}>No tracked bets yet</div>
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
                  color: "#4a6080", fontSize: "0.75em", fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.06em",
                  borderBottom: "1px solid #1a2a3a",
                }}>
                  {tid}
                  <span style={{ marginLeft: 10, color: "#2a4060", fontWeight: 400 }}>
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

// ── Page ──────────────────────────────────────────────────────────────────────
export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>("results");

  const TABS: { key: Tab; label: string }[] = [
    { key: "results", label: "Tournament Results" },
    { key: "model",   label: "Model Performance" },
    { key: "bets",    label: "Bet P&L" },
    { key: "slip",    label: "My Slip" },
  ];

  return (
    <div className="page-wrap" style={{ padding: "24px 20px" }}>
      <h1 style={{ color: "#dde6f5", fontWeight: 800, fontSize: "1.4em", marginBottom: 4 }}>
        Season History
      </h1>
      <p style={{ color: "#7a9ab8", fontSize: "0.88em", marginBottom: 20 }}>2026 season results, model calibration, and bet P&L.</p>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: "1px solid #1e3a5f", paddingBottom: 0 }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              background: "none", border: "none", cursor: "pointer",
              padding: "8px 16px", fontSize: "0.88em", fontWeight: tab === t.key ? 700 : 500,
              color: tab === t.key ? "#dde6f5" : "#7a9ab8",
              borderBottom: `2px solid ${tab === t.key ? "#00c44f" : "transparent"}`,
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ background: "#0d1929", borderRadius: 10, border: "1px solid #1e3a5f", overflow: "hidden" }}>
        {tab === "results" && <ResultsTab />}
        {tab === "model"   && <ModelTab />}
        {tab === "bets"    && <BetsTab />}
        {tab === "slip"    && <MySlipTab />}
      </div>
    </div>
  );
}
