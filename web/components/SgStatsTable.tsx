"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { SgStatPlayer, HoleData } from "@/lib/api";

// SortKey no longer includes "position" — we sort leaderboard order by "total" (numeric score)
type SortKey = "sg_total" | "sg_ott" | "sg_app" | "sg_arg" | "sg_putt" | "sg_t2g" | "total";

type Props = {
  players: SgStatPlayer[];
  roundParam: string;
  updated: string | null;
  onRoundChange: (r: string) => void;
  holeScores?: Record<string, Record<string, HoleData[]>>;
  myPicks?: string[];
};

const ROUND_OPTIONS = [
  { key: "event_avg", label: "Event Avg" },
  { key: "1",        label: "Round 1"   },
  { key: "2",        label: "Round 2"   },
  { key: "3",        label: "Round 3"   },
  { key: "4",        label: "Round 4"   },
];

const BG     = "#0d1a30";
const BG_ALT = "#0a1525";
const BORDER = "#1e3a5f";
const MUTED  = "#5a7090";
const GREEN  = "#00c44f";
const RED    = "#e74c3c";
const GOLD   = "#f1c40f";
const BLUE   = "#4cb8ff";
const PURPLE = "#a070d0";

function normName(n: string) {
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

function sgColor(n: number | null): string {
  if (n == null) return "#4a6080";
  if (n >  2)    return GREEN;
  if (n >  0.5)  return "#4cb856";
  if (n >  0)    return "#8ba0b8";
  if (n > -0.5)  return "#8ba0b8";
  if (n > -2)    return "#e06050";
  return RED;
}

function fmtSg(n: number | null): string {
  if (n == null) return "—";
  return n >= 0 ? `+${n.toFixed(2)}` : n.toFixed(2);
}

function fmtScore(n: number | null): string {
  if (n == null) return "—";
  return n === 0 ? "E" : n > 0 ? `+${n}` : String(n);
}

function fmtThru(n: number | null): string {
  if (n == null) return "—";
  if (n === 18)  return "F";   // 18 holes played = finished
  return String(Math.round(n));
}

// Extract numeric rank from position string for sorting: "1"→1, "T3"→3, "WD"→999
function posNumeric(pos: string | null): number {
  if (!pos) return 9999;
  const m = pos.match(/\d+/);
  return m ? parseInt(m[0]) : 9999;
}

// ── Improved scorecard (matches InPlayLeaderboard design) ─────────────────────

function relColor(rel: number | null): string {
  if (rel == null) return "#5a7090";
  if (rel <= -2) return GOLD;
  if (rel === -1) return RED;
  if (rel === 0)  return "#7f8c8d";
  if (rel === 1)  return BLUE;
  return PURPLE;
}

function runningColor(s: string | null | undefined): string {
  if (!s || s === "E") return "#4a6080";
  return s.startsWith("-") ? GREEN : RED;
}

function ScoreCell({ h }: { h: HoleData }) {
  const played = h.strokes != null;
  const color  = played ? relColor(h.rel) : "#2a3a50";

  let boxStyle: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", justifyContent: "center",
    width: 26, height: 26, fontWeight: played && h.rel !== 0 ? 700 : 500,
    fontSize: "0.85em", color,
  };
  if (played && h.rel != null) {
    if (h.rel <= -2) boxStyle = { ...boxStyle, border: `2px solid ${GOLD}`, borderRadius: "50%", background: "#1a1200" };
    else if (h.rel === -1) boxStyle = { ...boxStyle, border: `2px solid ${RED}`, borderRadius: "50%", background: "#180808" };
    else if (h.rel === 1)  boxStyle = { ...boxStyle, border: "1px solid #1a3a52", background: "#060d18" };
    else if (h.rel >= 2)   boxStyle = { ...boxStyle, border: `2px solid ${PURPLE}`, background: "#100818" };
  }
  return (
    <td style={{ padding: "2px 1px", textAlign: "center", minWidth: 30 }}>
      <div style={boxStyle}>{played ? h.strokes : "·"}</div>
      {played && h.running && (
        <div style={{ fontSize: "0.5em", color: runningColor(h.running), textAlign: "center", marginTop: 1 }}>
          {h.running}
        </div>
      )}
    </td>
  );
}

function ScorecardRow({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);
  const frontStrokes = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backStrokes  = back.reduce((s, h)  => s + (h.strokes ?? 0), 0);
  const frontPar     = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar      = back.reduce((s, h)  => s + (h.par ?? 0), 0);
  const frontPlayed  = front.some(h => h.strokes != null);
  const backPlayed   = back.some(h => h.strokes != null);
  const totalStrokes = frontStrokes + backStrokes;
  const totalPar     = frontPar + backPar;
  const vsPar        = (frontPlayed || backPlayed) ? totalStrokes - totalPar : null;
  const vsParStr     = vsPar == null ? "—" : vsPar === 0 ? "E" : vsPar > 0 ? `+${vsPar}` : String(vsPar);
  const vsParColor   = vsPar == null ? "#4a6080" : vsPar < 0 ? GREEN : vsPar > 0 ? RED : "#8ba0b8";

  const thStyle: React.CSSProperties = { fontSize: "0.58em", color: "#2a3a50", textAlign: "center", padding: "2px 1px", minWidth: 30, fontWeight: 700 };
  const parStyle: React.CSSProperties = { fontSize: "0.62em", color: "#3a5060", textAlign: "center", padding: "2px 1px" };
  const subStyle: React.CSSProperties = { fontSize: "0.72em", color: "#8ba0b8", fontWeight: 700, textAlign: "center", padding: "3px 6px", minWidth: 38, borderLeft: `1px solid ${BORDER}` };

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: "0.62em", color: MUTED, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Round {round}
        </span>
        {(frontPlayed || backPlayed) && (
          <span style={{ fontSize: "0.7em", fontWeight: 800, color: vsParColor }}>
            {vsParStr} ({totalStrokes})
          </span>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
          <thead>
            <tr>
              {front.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.58em", color: "#2a3a50" }}>OUT</td>
              {back.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.58em", color: "#2a3a50" }}>IN</td>
              <td style={{ ...subStyle, fontSize: "0.58em", color: "#2a3a50" }}>TOT</td>
            </tr>
          </thead>
          <tbody>
            <tr>
              {front.map(h => <td key={h.hole} style={parStyle}>{h.par ?? "—"}</td>)}
              <td style={{ ...subStyle, color: "#2a3a50", fontSize: "0.6em" }}>{frontPar || "—"}</td>
              {back.map(h => <td key={h.hole} style={parStyle}>{h.par ?? "—"}</td>)}
              <td style={{ ...subStyle, color: "#2a3a50", fontSize: "0.6em" }}>{backPar || "—"}</td>
              <td style={{ ...subStyle, color: "#2a3a50", fontSize: "0.6em" }}>{totalPar || "—"}</td>
            </tr>
            <tr>
              {front.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {frontPlayed ? frontStrokes : "—"}
                {frontPlayed && (
                  <div style={{ fontSize: "0.6em", color: (() => { const v = frontStrokes - frontPar; return v < 0 ? GREEN : v > 0 ? RED : "#4a6080"; })() }}>
                    {(() => { const v = frontStrokes - frontPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              {back.map(h => <ScoreCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {backPlayed ? backStrokes : "—"}
                {backPlayed && (
                  <div style={{ fontSize: "0.6em", color: (() => { const v = backStrokes - backPar; return v < 0 ? GREEN : v > 0 ? RED : "#4a6080"; })() }}>
                    {(() => { const v = backStrokes - backPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              <td style={{ ...subStyle, color: vsParColor, fontWeight: 800 }}>
                {(frontPlayed || backPlayed) ? totalStrokes : "—"}
                {vsPar != null && <div style={{ fontSize: "0.6em" }}>{vsParStr}</div>}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SgStatsTable({ players, roundParam, updated, onRoundChange, holeScores, myPicks = [] }: Props) {
  const [sortKey, setSortKey]   = useState<SortKey>("sg_total");
  const [sortDesc, setSortDesc] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  const myPicksNorm = useMemo(() => new Set(myPicks.map(normName)), [myPicks]);

  // Check if driving stats are all null (DG doesn't always include them)
  const hasDrivingData = players.some(p => p.driving_dist != null || p.driving_acc != null);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDesc(d => !d);
    else { setSortKey(key); setSortDesc(true); }
    setExpanded(null);
  }

  const sorted = useMemo(() => {
    return [...players].sort((a, b) => {
      // "total" (leaderboard score) sorts ascending by default (lower = better)
      // SG columns sort descending (higher = better)
      if (sortKey === "total") {
        const av = a.total ?? 999;
        const bv = b.total ?? 999;
        return sortDesc ? av - bv : bv - av;
      }
      const av = a[sortKey] as number | null;
      const bv = b[sortKey] as number | null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortDesc ? bv - av : av - bv;
    });
  }, [players, sortKey, sortDesc]);

  const th: React.CSSProperties = {
    background: "#0a1628", color: MUTED,
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: `1px solid ${BORDER}`,
    textAlign: "center", whiteSpace: "nowrap",
    userSelect: "none",
  };

  function SortTh({ label, col, color }: { label: string; col: SortKey; color?: string }) {
    const active = sortKey === col;
    const arrow  = active ? (sortDesc ? " ▾" : " ▴") : "";
    return (
      <th
        style={{ ...th, cursor: "pointer", color: active ? (color ?? "#dde6f5") : (color ?? MUTED) }}
        onClick={() => handleSort(col)}
      >
        {label}{arrow}
      </th>
    );
  }

  // Column count for the colspan in expanded scorecard rows
  const totalCols = 10 + (hasDrivingData ? 2 : 0);

  return (
    <div>
      {/* Round selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: "0.75em", color: "#4a6080", marginRight: 4 }}>Round:</span>
        {ROUND_OPTIONS.map(opt => (
          <button
            key={opt.key}
            onClick={() => onRoundChange(opt.key)}
            style={{
              background: roundParam === opt.key ? "#0d2e18" : "#0a1525",
              border: `1px solid ${roundParam === opt.key ? GREEN : BORDER}`,
              color: roundParam === opt.key ? GREEN : MUTED,
              borderRadius: 6, padding: "4px 12px",
              fontSize: "0.8em", fontWeight: roundParam === opt.key ? 700 : 400,
              cursor: "pointer",
            }}
          >
            {opt.label}
          </button>
        ))}
        {updated && (
          <span style={{ fontSize: "0.68em", color: "#3a5060", marginLeft: 8 }}>Updated {updated}</span>
        )}
        {holeScores && (
          <span style={{ fontSize: "0.65em", color: "#3a5060", marginLeft: 8 }}>· click row for scorecard</span>
        )}
      </div>

      {!players.length ? (
        <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
          No SG data for this round yet.
        </div>
      ) : (
        <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", background: BG }}>
            <thead>
              <tr>
                <th style={{ ...th, textAlign: "left", width: 36 }}>Pos</th>
                <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
                <SortTh label="Score" col="total" />
                <th style={{ ...th }}>Thru</th>
                <SortTh label="SG Total" col="sg_total" color={GREEN} />
                <SortTh label="OTT"   col="sg_ott" />
                <SortTh label="App"   col="sg_app" />
                <SortTh label="ArG"   col="sg_arg" />
                <SortTh label="Putt"  col="sg_putt" />
                <SortTh label="T2G"   col="sg_t2g" />
                {hasDrivingData && <th style={{ ...th }}>Dist</th>}
                {hasDrivingData && <th style={{ ...th }}>Acc%</th>}
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, i) => {
                const isPick     = myPicksNorm.has(normName(p.player));
                const bg         = isPick ? "#060e09" : i % 2 === 0 ? BG : BG_ALT;
                const isExpanded = expanded === p.player;
                const playerHoles = holeScores ? holeScores[p.player] ?? null : null;
                const clickable  = !!holeScores;
                const isWd       = p.position === "WD" || p.position === "DQ";

                const td: React.CSSProperties = {
                  padding: "6px 10px", borderBottom: "1px solid #0f2236",
                  background: bg, textAlign: "center", fontSize: "0.83em",
                };

                return (
                  <React.Fragment key={`sg-${i}`}>
                    <tr
                      style={{
                        cursor: clickable ? "pointer" : "default",
                        opacity: isWd ? 0.5 : 1,
                        borderLeft: isPick ? "2px solid #00c44f" : "2px solid transparent",
                      }}
                      onClick={() => clickable && setExpanded(isExpanded ? null : p.player)}
                    >
                      {/* Position — show string directly ("T3", "WD", "1") */}
                      <td style={{ ...td, textAlign: "left", color: MUTED, fontWeight: 700 }}>
                        {p.position ?? "—"}
                      </td>

                      {/* Player name */}
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
                        {clickable && (
                          <span style={{ marginRight: 5, color: isExpanded ? GREEN : "#2a3a50", fontSize: "0.8em" }}>
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                        <Link
                          href={`/players?player=${encodeURIComponent(p.player)}`}
                          onClick={e => e.stopPropagation()}
                          style={{ color: isPick ? GREEN : "#dde6f5", textDecoration: "none" }}
                          onMouseEnter={e => (e.currentTarget.style.color = BLUE)}
                          onMouseLeave={e => (e.currentTarget.style.color = isPick ? GREEN : "#dde6f5")}
                        >
                          {p.player}
                        </Link>
                        {isPick && (
                          <span style={{ fontSize: "0.55em", fontWeight: 800, color: GREEN, background: "#0d2e18", border: "1px solid #00c44f44", borderRadius: 3, padding: "1px 4px", marginLeft: 6 }}>
                            MY PICK
                          </span>
                        )}
                      </td>

                      {/* Score (total vs par) */}
                      <td style={{ ...td, color: p.total != null ? (p.total < 0 ? GREEN : p.total > 0 ? RED : "#8ba0b8") : "#4a6080", fontWeight: 700 }}>
                        {fmtScore(p.total)}
                      </td>

                      {/* Thru — "F" for finished (18 holes), number otherwise */}
                      <td style={{ ...td, color: p.thru === 18 ? "#4a6080" : MUTED }}>
                        {fmtThru(p.thru)}
                      </td>

                      <td style={{ ...td, color: sgColor(p.sg_total), fontWeight: 700 }}>{fmtSg(p.sg_total)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_ott)  }}>{fmtSg(p.sg_ott)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_app)  }}>{fmtSg(p.sg_app)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_arg)  }}>{fmtSg(p.sg_arg)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_putt) }}>{fmtSg(p.sg_putt)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_t2g)  }}>{fmtSg(p.sg_t2g)}</td>
                      {hasDrivingData && <td style={{ ...td, color: MUTED }}>{p.driving_dist != null ? Math.round(p.driving_dist) : "—"}</td>}
                      {hasDrivingData && <td style={{ ...td, color: MUTED }}>{p.driving_acc != null ? `${p.driving_acc.toFixed(1)}%` : "—"}</td>}
                    </tr>

                    {/* Expanded scorecard row */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={totalCols} style={{ background: "#080f1e", borderBottom: `1px solid ${BORDER}`, padding: "12px 16px" }}>
                          {playerHoles ? (
                            Object.entries(playerHoles)
                              .sort(([a], [b]) => Number(a) - Number(b))
                              .map(([rnd, holes]) => (
                                <ScorecardRow key={rnd} holes={holes} round={rnd} />
                              ))
                          ) : (
                            <span style={{ color: "#3a5060", fontSize: "0.8em" }}>
                              No hole-by-hole data for {p.player}
                            </span>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>
        SG = Strokes Gained vs field average · OTT = Off the Tee · App = Approach · ArG = Around Green · T2G = Tee to Green
        {!hasDrivingData && " · Driving stats not available for this round"}
        {" · click column headers to sort · click row for scorecard"}
      </p>
    </div>
  );
}
