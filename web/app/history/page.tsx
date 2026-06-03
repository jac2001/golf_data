"use client";

import React, { useState, useEffect } from "react";
import {
  getHistoryTournaments, getHistoryModel, getHistoryBets,
  getBetSlip, removeFromBetSlip, getModelComparison,
  HistoryTournament, HistoryModelRow, HistoryBetsResponse,
  SlipBet, SlipStats, TournamentPnl, ModelComparison, ModelDisagreement,
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

// ── Model vs DG Comparison ────────────────────────────────────────────────────
function ModelVsDG({ data }: { data: ModelComparison }) {
  const rhoColor = (r: number) => r >= 0.85 ? "#00c44f" : r >= 0.70 ? "#f0c040" : "#e05555";
  const diffColor = (d: number) => d > 0 ? "#00c44f" : "#e05555";

  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14 }}>
        <span style={{ color: "#dde6f5", fontWeight: 700, fontSize: "1em" }}>
          vs DataGolf — {data.tournament_name}
        </span>
        <span style={{ color: "#4a6080", fontSize: "0.78em" }}>{data.players_compared} players matched</span>
      </div>

      {/* Market correlations */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
        {data.markets.map(m => (
          <div key={m.market} style={{
            background: "#0a1720", border: "1px solid #1e3a5f",
            borderRadius: 7, padding: "8px 14px", minWidth: 80, textAlign: "center",
          }}>
            <div style={{ color: "#4a6080", fontSize: "0.68em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
              {m.market.replace("_", " ")}
            </div>
            <div style={{ color: rhoColor(m.spearman_rho), fontWeight: 800, fontSize: "1.1em" }}>
              {m.spearman_rho.toFixed(3)}
            </div>
            <div style={{ color: "#2a4060", fontSize: "0.65em", marginTop: 2 }}>Spearman ρ</div>
          </div>
        ))}
      </div>

      {/* Side-by-side top-10 picks */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 18 }}>
        {[
          { label: "Our Model", picks: data.our_top10, color: "#00c44f" },
          { label: "DataGolf",  picks: data.dg_top10,  color: "#4cb8ff" },
        ].map(col => (
          <div key={col.label} style={{ background: "#0a1720", border: "1px solid #1e3a5f", borderRadius: 7, overflow: "hidden" }}>
            <div style={{ padding: "7px 12px", borderBottom: "1px solid #1e3a5f", color: col.color, fontWeight: 700, fontSize: "0.78em" }}>
              {col.label} — Top 10 Win Prob
            </div>
            {col.picks.map((p, i) => (
              <div key={p.player} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "5px 12px", borderBottom: i < 9 ? "1px solid #0d1929" : "none",
              }}>
                <span style={{ color: i < 3 ? "#dde6f5" : "#7a9ab8", fontSize: "0.82em", fontWeight: i < 3 ? 600 : 400 }}>
                  {i + 1}. {p.player.includes(",") ? p.player.split(",").reverse().join(" ").trim() : p.player}
                </span>
                <span style={{ color: col.color, fontWeight: 700, fontSize: "0.82em" }}>{p.prob}%</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Disagreements */}
      {data.disagreements.length > 0 && (
        <div>
          <div style={{ color: "#7a9ab8", fontSize: "0.75em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            Notable Disagreements — where our model diverges from DG
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82em" }}>
            <thead>
              <tr>
                {["Player", "Our Win%", "DG Win%", "Diff", "Our Top10%", "DG Top10%"].map(h => (
                  <th key={h} style={{ ...hdr, fontSize: "0.75em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.disagreements.map((d: ModelDisagreement) => (
                <tr key={d.player_name}>
                  <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>
                    {d.player_name.includes(",") ? d.player_name.split(",").reverse().join(" ").trim() : d.player_name}
                  </td>
                  <td style={{ ...cell, color: d.direction === "higher" ? "#00c44f" : "#e05555" }}>{d.our_win_pct}%</td>
                  <td style={{ ...cell, color: "#7a9ab8" }}>{d.dg_win_pct}%</td>
                  <td style={{ ...cell, color: diffColor(d.diff_pp), fontWeight: 700 }}>
                    {d.diff_pp > 0 ? "+" : ""}{d.diff_pp}pp
                  </td>
                  <td style={{ ...cell, color: "#8ba0b8" }}>{d.our_top10 ?? "—"}%</td>
                  <td style={{ ...cell, color: "#4a6080" }}>{d.dg_top10}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Model Tab ─────────────────────────────────────────────────────────────────
function ModelTab() {
  const [data,       setData]       = useState<HistoryModelRow[] | null>(null);
  const [comparison, setComparison] = useState<ModelComparison | null>(null);
  const [loading,    setLoading]    = useState(true);

  useEffect(() => {
    Promise.all([
      getHistoryModel().then(setData),
      getModelComparison().then(setComparison).catch(() => null),
    ]).finally(() => setLoading(false));
  }, []);

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading...</p>;
  if (!data?.length && !comparison) return <p style={{ color: "#7a9ab8", padding: 24 }}>No model results yet.</p>;

  function calibBadge(pred: number, actual: number | null) {
    if (actual === null) return <span style={{ color: "#7a9ab8" }}>—</span>;
    const ratio = actual / pred;
    const col = ratio >= 0.85 && ratio <= 1.15 ? "#00c44f" : ratio >= 0.7 && ratio <= 1.3 ? "#f0c040" : "#e05555";
    return <span style={{ color: col }}>{actual.toFixed(1)}% <span style={{ color: "#555", fontSize: "0.85em" }}>({ratio.toFixed(2)}x)</span></span>;
  }

  return (
    <div>
      {comparison && <ModelVsDG data={comparison} />}

      {data?.length ? (
      <>
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
      </>
      ) : null}
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
  const hasBankroll = stats.starting_bankroll != null;
  const pnlDollars  = stats.total_pnl_dollars ?? 0;

  const statItems = [
    { label: "Tracked",  value: String(stats.total_bets) },
    { label: "Pending",  value: String(stats.pending) },
    { label: "Won",      value: `${stats.won} / ${stats.graded}`, color: stats.won > 0 ? "#00c44f" : undefined },
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
        background: "#0a1720", borderRadius: hasBankroll ? "8px 8px 0 0" : 8,
        border: "1px solid #1e3a5f", borderBottom: hasBankroll ? "none" : undefined,
      }}>
        {statItems.map(s => (
          <div key={s.label} style={{ minWidth: 70 }}>
            <div style={{ color: "#7a9ab8", fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 2 }}>{s.label}</div>
            <div style={{ color: s.color ?? "#dde6f5", fontWeight: 700, fontSize: "1.05em" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Bankroll row — only shown when configured */}
      {hasBankroll && (
        <div style={{
          display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap",
          padding: "10px 16px",
          background: "#070f18", borderRadius: "0 0 8px 8px",
          border: "1px solid #1e3a5f", borderTop: "1px solid #0d2030",
        }}>
          <div>
            <span style={{ color: "#4a6080", fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em" }}>Bankroll</span>
            {" "}
            <span style={{ color: "#7a9ab8", fontSize: "0.82em" }}>${stats.starting_bankroll?.toLocaleString()}</span>
            <span style={{ color: "#2a4060", fontSize: "0.82em", margin: "0 6px" }}>→</span>
            <span style={{ color: pnlColor(pnlDollars), fontWeight: 700, fontSize: "1.05em" }}>
              ${stats.current_bankroll?.toLocaleString()}
            </span>
          </div>
          <div style={{ color: pnlColor(pnlDollars), fontSize: "0.88em", fontWeight: 600 }}>
            {pnlDollars >= 0 ? "+" : ""}${pnlDollars.toFixed(2)} season
          </div>
          <div style={{ color: "#3a5060", fontSize: "0.75em" }}>
            ${stats.unit_size}/unit
          </div>

          {/* Per-tournament mini breakdown */}
          {stats.by_tournament.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginLeft: "auto" }}>
              {stats.by_tournament.map((t: TournamentPnl) => (
                <span key={t.tid} style={{
                  background: "#0d1929", border: "1px solid #1e3a5f",
                  borderRadius: 5, padding: "3px 8px", fontSize: "0.75em",
                }}>
                  <span style={{ color: "#4a6080" }}>{t.tid.replace("R2026", "")}</span>
                  {" "}
                  <span style={{ color: pnlColor(t.pnl_dollars), fontWeight: 600 }}>
                    {t.pnl_dollars >= 0 ? "+" : ""}${t.pnl_dollars.toFixed(0)}
                  </span>
                  <span style={{ color: "#2a4060" }}> {t.won}/{t.total}</span>
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
  const color = status === "on_track"  ? "#00c44f"
              : status === "marginal"  ? "#f39c12"
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
  const scoreColor = scoreNum != null && scoreNum < 0 ? "#00c44f"
                   : scoreNum != null && scoreNum > 0 ? "#e05555"
                   : "#dde6f5";

  const rowBg = isWon    ? "#071410"
              : isLost   ? "#130a0a"
              : hasLive && bet.live_status === "on_track"  ? "#071a10"
              : hasLive && bet.live_status === "off_track" ? "#180a0a"
              : "transparent";

  const odds = bet.odds_american >= 0 ? `+${bet.odds_american}` : String(bet.odds_american);

  return (
    <tr style={{ background: rowBg }}>
      <td style={cell}>{bet.tournament_id?.replace("R2026", "") ?? "—"}</td>
      <td style={{ ...cell, color: "#dde6f5", fontWeight: 600, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {bet.player_name}
      </td>
      <td style={cell}>{MARKET_LABELS[bet.market] ?? bet.market}</td>
      <td style={{ ...cell, color: "#8ba0b8" }}>{odds}</td>

      {/* Result column: live context for pending bets, or Won/Lost */}
      <td style={cell}>
        {isWon  && <span style={{ color: "#00c44f", fontWeight: 700 }}>Won</span>}
        {isLost && <span style={{ color: "#e05555", fontWeight: 700 }}>Lost</span>}
        {isPending && hasLive && (
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
            <LiveStatusDot status={bet.live_status} />
            <span style={{ color: "#dde6f5", fontWeight: 700, fontSize: "0.95em" }}>
              {bet.live_position}
            </span>
            <span style={{ color: scoreColor, fontWeight: 700, fontSize: "0.95em" }}>
              {bet.live_total ?? "E"}
            </span>
            <span style={{ color: "#4a6080", fontSize: "0.82em" }}>
              {bet.live_thru === "F" ? "F" : bet.live_thru ? `thru ${bet.live_thru}` : ""}
            </span>
          </div>
        )}
        {isPending && !hasLive && (
          <span style={{ color: "#f39c12" }}>Pending</span>
        )}
      </td>

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

      {/* Last updated indicator */}
      {updatedAt && (
        <div style={{ fontSize: "0.72em", color: "#2a4060", marginBottom: 12, paddingLeft: 2 }}>
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
