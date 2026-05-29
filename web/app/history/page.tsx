"use client";

import React, { useState, useEffect } from "react";
import {
  getHistoryTournaments, getHistoryModel, getHistoryBets,
  HistoryTournament, HistoryModelRow, HistoryBetsResponse,
} from "@/lib/api";

type Tab = "results" | "model" | "bets";

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

// ── Page ──────────────────────────────────────────────────────────────────────
export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>("results");

  const TABS: { key: Tab; label: string }[] = [
    { key: "results", label: "Tournament Results" },
    { key: "model",   label: "Model Performance" },
    { key: "bets",    label: "Bet P&L" },
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
      </div>
    </div>
  );
}
