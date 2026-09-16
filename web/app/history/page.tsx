"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  getHistoryTournaments, getHistoryModel, getHistoryBets,
  getTournamentLeaderboard, getLineup,
  getBetSlip, removeFromBetSlip,
  HistoryTournament, HistoryModelRow, HistoryBetsResponse,
  TournamentLeaderboardRow,
  SlipBet, SlipStats, TournamentPnl,
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

function normName(n: string): string {
  return n.toLowerCase().split(/[\s,]+/).filter(Boolean).sort().join(" ");
}

function toParColor(v: string): string {
  if (!v) return "#c8d8e8";
  const s = v.trim();
  if (s === "E" || s === "0") return "#c8d8e8";
  return s.startsWith("-") ? "#00c44f" : "#e05555";
}

function posColor(pos: string): string {
  const n = parseInt(pos, 10);
  if (isNaN(n)) return "#7a9ab8";
  if (n === 1) return "#f0c040";
  if (n <= 5) return "#00c44f";
  if (n <= 10) return "#4cb8ff";
  return "#c8d8e8";
}

type TournamentCache = Record<string, TournamentLeaderboardRow[] | "loading">;

function TournamentLeaderboard({
  tid, myPicksNorm,
}: {
  tid: string;
  myPicksNorm: Set<string>;
}) {
  const [rows, setRows] = useState<TournamentLeaderboardRow[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getTournamentLeaderboard(tid)
      .then(setRows)
      .catch(() => setError(true));
  }, [tid]);

  if (error) return <p style={{ color: "#e05555", fontSize: "0.82em" }}>Failed to load results.</p>;
  if (!rows) return <p style={{ color: "#7a9ab8", fontSize: "0.82em" }}>Loading results…</p>;
  if (!rows.length) return <p style={{ color: "#7a9ab8", fontSize: "0.82em" }}>No results found.</p>;

  // Detect which rounds have data
  const hasR3 = rows.some(r => r.r3 != null);
  const hasR4 = rows.some(r => r.r4 != null);
  const hasEarnings = rows.some(r => r.earnings != null);
  const hasSg = rows.some(r => r.sg_total != null);

  const sgColor = (v: number | null) => v == null ? "#4a6080" : v >= 0 ? "#00c44f" : "#e05555";
  const fmtSg = (v: number | null) => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
  const fmtPct = (v: number | null) => v == null ? "—" : `${v.toFixed(0)}%`;

  const thStyle: React.CSSProperties = {
    padding: "6px 10px", background: "#081220", fontSize: "0.7em", fontWeight: 700,
    color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: "1px solid #1e3a5f", whiteSpace: "nowrap", textAlign: "center",
  };
  const tdBase: React.CSSProperties = { padding: "5px 10px", borderBottom: "1px solid #0d1e2e", textAlign: "center", fontSize: "0.83em" };

  return (
    <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid #1e3a5f" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#0a1525" }}>
        <thead>
          <tr>
            <th style={{ ...thStyle, textAlign: "left", width: 40 }}>Pos</th>
            <th style={{ ...thStyle, textAlign: "left" }}>Player</th>
            <th style={thStyle}>R1</th>
            <th style={thStyle}>R2</th>
            {hasR3 && <th style={thStyle}>R3</th>}
            {hasR4 && <th style={thStyle}>R4</th>}
            <th style={thStyle}>Total</th>
            {hasSg && (
              <>
                <th style={thStyle}>SG Tot</th>
                <th style={thStyle}>OTT</th>
                <th style={thStyle}>APP</th>
                <th style={thStyle}>ARG</th>
                <th style={thStyle}>Putt</th>
                <th style={thStyle}>Dist</th>
                <th style={thStyle}>Acc%</th>
                <th style={thStyle}>GIR%</th>
                <th style={thStyle}>Scrmb%</th>
              </>
            )}
            {hasEarnings && <th style={{ ...thStyle, textAlign: "right" }}>Earnings</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isPick = myPicksNorm.has(normName(r.player_name));
            const rowBg = isPick ? "#060e09" : i % 2 === 0 ? "#0a1525" : "#091422";
            return (
              <tr key={i} style={{ background: rowBg }}>
                <td style={{ ...tdBase, textAlign: "left", fontWeight: 700, color: posColor(r.position), borderLeft: isPick ? "2px solid #00c44f" : undefined }}>
                  {r.position}
                </td>
                <td style={{ ...tdBase, textAlign: "left", whiteSpace: "nowrap", fontWeight: isPick ? 700 : 500 }}>
                  <Link
                    href={`/players?player=${encodeURIComponent(r.player_name)}`}
                    style={{ color: isPick ? "#00c44f" : "#dde6f5", textDecoration: "none" }}
                  >
                    {r.player_name}
                  </Link>
                  {isPick && (
                    <span style={{
                      marginLeft: 7, fontSize: "0.65em", fontWeight: 800,
                      color: "#00c44f", background: "#00c44f18", border: "1px solid #00c44f33",
                      borderRadius: 4, padding: "1px 5px",
                    }}>MY PICK</span>
                  )}
                </td>
                <td style={{ ...tdBase, color: "#c8d8e8" }}>{r.r1 ?? "—"}</td>
                <td style={{ ...tdBase, color: "#c8d8e8" }}>{r.r2 ?? "—"}</td>
                {hasR3 && <td style={{ ...tdBase, color: "#c8d8e8" }}>{r.r3 ?? "—"}</td>}
                {hasR4 && <td style={{ ...tdBase, color: "#c8d8e8" }}>{r.r4 ?? "—"}</td>}
                <td style={{ ...tdBase, fontWeight: 700, color: toParColor(r.to_par) }}>{r.to_par || "—"}</td>
                {hasSg && (
                  <>
                    <td style={{ ...tdBase, fontWeight: 700, color: sgColor(r.sg_total) }}>{fmtSg(r.sg_total)}</td>
                    <td style={{ ...tdBase, color: sgColor(r.sg_ott) }}>{fmtSg(r.sg_ott)}</td>
                    <td style={{ ...tdBase, color: sgColor(r.sg_app) }}>{fmtSg(r.sg_app)}</td>
                    <td style={{ ...tdBase, color: sgColor(r.sg_arg) }}>{fmtSg(r.sg_arg)}</td>
                    <td style={{ ...tdBase, color: sgColor(r.sg_putt) }}>{fmtSg(r.sg_putt)}</td>
                    <td style={{ ...tdBase, color: "#c8d8e8" }}>{r.driving_dist != null ? r.driving_dist.toFixed(0) : "—"}</td>
                    <td style={{ ...tdBase, color: "#c8d8e8" }}>{fmtPct(r.driving_acc)}</td>
                    <td style={{ ...tdBase, color: "#c8d8e8" }}>{fmtPct(r.gir_pct)}</td>
                    <td style={{ ...tdBase, color: "#c8d8e8" }}>{fmtPct(r.scrambling)}</td>
                  </>
                )}
                {hasEarnings && (
                  <td style={{ ...tdBase, textAlign: "right", color: "#7a9ab8", fontSize: "0.78em" }}>
                    {r.earnings ?? "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ResultsTab() {
  const [data, setData]         = useState<HistoryTournament[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);
  const [myPicks, setMyPicks]   = useState<string[]>([]);

  useEffect(() => {
    getHistoryTournaments().then(setData).finally(() => setLoading(false));
    getLineup()
      .then(l => { if (l.confirmed) setMyPicks(l.picks.map(p => p.player_name)); })
      .catch(() => {});
  }, []);

  const myPicksNorm = React.useMemo(() => new Set(myPicks.map(normName)), [myPicks]);

  if (loading) return <p style={{ color: "#7a9ab8", padding: 24 }}>Loading...</p>;
  if (!data?.length) return <p style={{ color: "#7a9ab8", padding: 24 }}>No results yet.</p>;

  function toggle(tid: string) {
    setExpanded(prev => prev === tid ? null : tid);
  }

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
                onClick={() => toggle(t.tournament_id)}
              >
                <td style={cell}>{t.start_date?.slice(0, 10) ?? ""}</td>
                <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {t.name}
                    <span style={{ fontSize: "0.72em", color: expanded === t.tournament_id ? "#4cb8ff" : "#2a4060" }}>
                      {expanded === t.tournament_id ? "▲" : "▼"}
                    </span>
                  </span>
                </td>
                <td style={{ ...cell, color: "#00c44f" }}>
                  <Link href={`/players?player=${encodeURIComponent(t.winner ?? "")}`} style={{ color: "#00c44f", textDecoration: "none" }} onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")} onMouseLeave={e => (e.currentTarget.style.color = "#00c44f")}>
                    {t.winner}
                  </Link>
                </td>
                <td style={{ ...cell, color: "#f0c040" }}>{t.winner_score}</td>
                <td style={cell}>{t.winner_earnings}</td>
                <td style={cell}>{t.field_size}</td>
              </tr>
              {expanded === t.tournament_id && (
                <tr>
                  <td colSpan={6} style={{ background: "#091525", padding: "16px 20px" }}>
                    {/* Recap narrative */}
                    {t.recap && (
                      <p style={{
                        color: "#b0c8e0", fontSize: "0.85em", lineHeight: 1.6,
                        margin: "0 0 16px", borderLeft: "2px solid #00c44f",
                        paddingLeft: 12, fontStyle: "italic",
                      }}>
                        {t.recap}
                      </p>
                    )}
                    <TournamentLeaderboard tid={t.tournament_id} myPicksNorm={myPicksNorm} />
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
  const [data,    setData]    = useState<HistoryModelRow[] | null>(null);
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

// ── Bets + Slip: extracted to shared components (Betting Board is the
//    primary home; this page keeps them until retired) ──────────────────
import { BetsLedger as BetsTab, BetSlipPanel as MySlipTab } from "@/components/BetsPanel";

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
              background: "none", borderTop: "none", borderLeft: "none", borderRight: "none", cursor: "pointer",
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
