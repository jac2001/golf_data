"use client";

import React, { useState, useMemo } from "react";
import { SgStatPlayer, HoleData } from "@/lib/api";

type SortKey = "sg_total" | "sg_ott" | "sg_app" | "sg_arg" | "sg_putt" | "sg_t2g" | "position";

type Props = {
  players: SgStatPlayer[];
  roundParam: string;
  updated: string | null;
  onRoundChange: (r: string) => void;
  holeScores?: Record<string, Record<string, HoleData[]>>;
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

// ── Scorecard sub-components ─────────────────────────────────────────────────

function holeRelColor(rel: number | null): { bg: string; fg: string } {
  if (rel == null) return { bg: "#0a1525", fg: "#2a3a4a" };
  if (rel <= -2)   return { bg: "#3a2800", fg: GOLD };
  if (rel === -1)  return { bg: "#2a0a0a", fg: RED };
  if (rel === 0)   return { bg: "#0d1a30", fg: "#5a7090" };
  if (rel === 1)   return { bg: "#0d1e38", fg: BLUE };
  return             { bg: "#0a0d1a", fg: PURPLE };
}

function ScorecardRow({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);
  const frontTotal = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backTotal  = back.reduce((s, h)  => s + (h.strokes ?? 0), 0);
  const frontPar   = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar    = back.reduce((s, h)  => s + (h.par ?? 0), 0);

  function HoleCell({ h }: { h: HoleData }) {
    const { bg, fg } = holeRelColor(h.rel);
    const hasData = h.strokes != null;
    return (
      <div style={{ textAlign: "center", minWidth: 26 }}>
        <div style={{ fontSize: "0.52em", color: "#3a5060", marginBottom: 1 }}>{h.hole}</div>
        <div style={{
          background: hasData ? bg : "transparent",
          color: hasData ? fg : "#1e2a3a",
          fontWeight: 700, fontSize: "0.78em",
          padding: "3px 2px", borderRadius: 3, minWidth: 22,
        }}>
          {h.strokes ?? "·"}
        </div>
        <div style={{ fontSize: "0.48em", color: "#2a3a4a", marginTop: 1 }}>{h.par ?? ""}</div>
      </div>
    );
  }

  function TotalCell({ label, total, par }: { label: string; total: number; par: number }) {
    const rel = total - par;
    const color = rel < 0 ? RED : rel > 0 ? BLUE : MUTED;
    return (
      <div style={{ minWidth: 30, textAlign: "center", borderLeft: `1px solid ${BORDER}`, paddingLeft: 4 }}>
        <div style={{ fontSize: "0.52em", color: MUTED, marginBottom: 1 }}>{label}</div>
        <div style={{ fontSize: "0.78em", fontWeight: 700, color: total > 0 ? color : MUTED }}>
          {total || "—"}
        </div>
        <div style={{ fontSize: "0.48em", color: "#2a3a4a", marginTop: 1 }}>{par || ""}</div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: "0.6em", color: MUTED, marginBottom: 4, fontWeight: 700 }}>Round {round}</div>
      <div style={{ display: "flex", gap: 3, alignItems: "flex-end", flexWrap: "nowrap", overflowX: "auto" }}>
        {front.map(h => <HoleCell key={h.hole} h={h} />)}
        <TotalCell label="OUT" total={frontTotal} par={frontPar} />
        {back.map(h => <HoleCell key={h.hole} h={h} />)}
        <TotalCell label="IN" total={backTotal} par={backPar} />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SgStatsTable({ players, roundParam, updated, onRoundChange, holeScores }: Props) {
  const [sortKey, setSortKey]     = useState<SortKey>("sg_total");
  const [sortDesc, setSortDesc]   = useState(true);
  const [expanded, setExpanded]   = useState<string | null>(null);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortDesc(d => !d);
    else { setSortKey(key); setSortDesc(true); }
    setExpanded(null);
  }

  const sorted = useMemo(() => {
    return [...players].sort((a, b) => {
      const av = a[sortKey as keyof SgStatPlayer] as number | null;
      const bv = b[sortKey as keyof SgStatPlayer] as number | null;
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

  const totalCols = 12;

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
                <th style={{ ...th, textAlign: "left", width: 32 }}>#</th>
                <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
                <SortTh label="Score" col="position" />
                <th style={{ ...th }}>Thru</th>
                <SortTh label="SG Total" col="sg_total" color={GREEN} />
                <SortTh label="OTT"   col="sg_ott" />
                <SortTh label="App"   col="sg_app" />
                <SortTh label="ArG"   col="sg_arg" />
                <SortTh label="Putt"  col="sg_putt" />
                <SortTh label="T2G"   col="sg_t2g" />
                <th style={{ ...th }}>Dist</th>
                <th style={{ ...th }}>Acc%</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, i) => {
                const bg = i % 2 === 0 ? BG : BG_ALT;
                const isExpanded = expanded === p.player;
                const playerHoles = holeScores ? holeScores[p.player] ?? null : null;
                const clickable = !!holeScores;

                const td: React.CSSProperties = {
                  padding: "6px 10px", borderBottom: "1px solid #0f2236",
                  background: bg, textAlign: "center", fontSize: "0.83em",
                };

                return (
                  <React.Fragment key={`sg-${i}`}>
                    <tr
                      style={{ cursor: clickable ? "pointer" : "default" }}
                      onClick={() => clickable && setExpanded(isExpanded ? null : p.player)}
                    >
                      <td style={{ ...td, color: MUTED, fontWeight: 700, textAlign: "left" }}>{i + 1}</td>
                      <td style={{ ...td, textAlign: "left", color: "#dde6f5", fontWeight: 600, whiteSpace: "nowrap" }}>
                        {clickable && (
                          <span style={{ marginRight: 6, color: isExpanded ? GREEN : "#2a3a50", fontSize: "0.8em" }}>
                            {isExpanded ? "▾" : "▸"}
                          </span>
                        )}
                        {p.player}
                      </td>
                      <td style={{ ...td, color: p.total != null ? (p.total < 0 ? GREEN : p.total > 0 ? RED : "#8ba0b8") : "#4a6080", fontWeight: 700 }}>
                        {fmtScore(p.total)}
                      </td>
                      <td style={{ ...td, color: MUTED }}>{p.thru ?? "—"}</td>
                      <td style={{ ...td, color: sgColor(p.sg_total), fontWeight: 700 }}>{fmtSg(p.sg_total)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_ott)  }}>{fmtSg(p.sg_ott)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_app)  }}>{fmtSg(p.sg_app)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_arg)  }}>{fmtSg(p.sg_arg)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_putt) }}>{fmtSg(p.sg_putt)}</td>
                      <td style={{ ...td, color: sgColor(p.sg_t2g)  }}>{fmtSg(p.sg_t2g)}</td>
                      <td style={{ ...td, color: MUTED }}>{p.driving_dist != null ? Math.round(p.driving_dist) : "—"}</td>
                      <td style={{ ...td, color: MUTED }}>{p.driving_acc != null ? `${p.driving_acc.toFixed(1)}%` : "—"}</td>
                    </tr>

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
        SG = Strokes Gained vs field average · OTT = Off the Tee · App = Approach · ArG = Around Green · T2G = Tee to Green · click column headers to sort
      </p>
    </div>
  );
}
