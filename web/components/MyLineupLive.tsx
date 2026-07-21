"use client";

import React from "react";
import Link from "next/link";
import { MyPickPlayer, HoleData } from "@/lib/api";

type Props = {
  picks: MyPickPlayer[];
  tournament: string;
  holeScores?: Record<string, Record<string, HoleData[]>>;
};

// ── Scorecard helpers ────────────────────────────────────────────────────────

function relColor(rel: number | null): string {
  if (rel == null) return "#5a7090";
  if (rel <= -2) return "#f1c40f";
  if (rel === -1) return "#e74c3c";
  if (rel === 0)  return "#7f8c8d";
  if (rel === 1)  return "#4cb8ff";
  return "#9b59b6";
}

function runningColor(s: string | null | undefined): string {
  if (!s || s === "E") return "#4a6080";
  return s.startsWith("-") ? "#00c44f" : "#e74c3c";
}

function MiniScoreCard({ holes, round }: { holes: HoleData[]; round: string }) {
  const front = holes.slice(0, 9);
  const back  = holes.slice(9, 18);
  const frontStrokes = front.reduce((s, h) => s + (h.strokes ?? 0), 0);
  const backStrokes  = back.reduce((s,  h) => s + (h.strokes ?? 0), 0);
  const frontPar     = front.reduce((s, h) => s + (h.par ?? 0), 0);
  const backPar      = back.reduce((s,  h) => s + (h.par ?? 0), 0);
  const frontPlayed  = front.some(h => h.strokes != null);
  const backPlayed   = back.some(h => h.strokes != null);
  const totalStrokes = frontStrokes + backStrokes;
  const totalPar     = frontPar + backPar;
  const vsPar        = (frontPlayed || backPlayed) ? totalStrokes - totalPar : null;
  const vsParStr     = vsPar == null ? "—" : vsPar === 0 ? "E" : vsPar > 0 ? `+${vsPar}` : String(vsPar);
  const vsParColor   = vsPar == null ? "#4a6080" : vsPar < 0 ? "#00c44f" : vsPar > 0 ? "#e74c3c" : "#8ba0b8";

  function HCell({ h }: { h: HoleData }) {
    const played = h.strokes != null;
    const color  = played ? relColor(h.rel) : "#1e3050";
    let boxStyle: React.CSSProperties = {
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 24, height: 24, fontSize: "0.8em", fontWeight: played && h.rel !== 0 ? 700 : 400, color,
    };
    if (played && h.rel != null) {
      if (h.rel <= -2) boxStyle = { ...boxStyle, border: "2px solid #f1c40f", borderRadius: "50%", background: "#1a1200" };
      else if (h.rel === -1) boxStyle = { ...boxStyle, border: "2px solid #e74c3c", borderRadius: "50%", background: "#180808" };
      else if (h.rel === 1)  boxStyle = { ...boxStyle, border: "1px solid #1a3a52", background: "#060d18" };
      else if (h.rel >= 2)   boxStyle = { ...boxStyle, border: "2px solid #6a3080", background: "#100818" };
    }
    return (
      <td style={{ padding: "2px 1px", textAlign: "center", minWidth: 28 }}>
        <div style={boxStyle}>{played ? h.strokes : "·"}</div>
        {played && h.running && (
          <div style={{ fontSize: "0.48em", color: runningColor(h.running), textAlign: "center", marginTop: 1 }}>
            {h.running}
          </div>
        )}
      </td>
    );
  }

  const thStyle: React.CSSProperties = { fontSize: "0.55em", color: "#2a3a50", textAlign: "center", padding: "2px 1px", minWidth: 28, fontWeight: 700 };
  const parStyle: React.CSSProperties = { fontSize: "0.6em", color: "#3a5060", textAlign: "center", padding: "1px 1px" };
  const subStyle: React.CSSProperties = { fontSize: "0.72em", color: "#8ba0b8", fontWeight: 700, textAlign: "center", padding: "2px 6px", minWidth: 36, borderLeft: "1px solid #1e3a5f" };

  return (
    <div style={{ marginTop: 14, borderTop: "1px solid #0f2236", paddingTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: "0.62em", color: "#4a6080", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Round {round}
        </span>
        {(frontPlayed || backPlayed) && (
          <span style={{ fontSize: "0.72em", fontWeight: 800, color: vsParColor }}>
            {vsParStr} ({totalStrokes})
          </span>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
          <thead>
            <tr>
              {front.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.55em", color: "#2a3a50" }}>OUT</td>
              {back.map(h => <td key={h.hole} style={thStyle}>{h.hole}</td>)}
              <td style={{ ...subStyle, fontSize: "0.55em", color: "#2a3a50" }}>IN</td>
              <td style={{ ...subStyle, fontSize: "0.55em", color: "#2a3a50" }}>TOT</td>
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
              {front.map(h => <HCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {frontPlayed ? frontStrokes : "—"}
                {frontPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = frontStrokes - frontPar; return v < 0 ? "#00c44f" : v > 0 ? "#e74c3c" : "#4a6080"; })() }}>
                    {(() => { const v = frontStrokes - frontPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              {back.map(h => <HCell key={h.hole} h={h} />)}
              <td style={{ ...subStyle }}>
                {backPlayed ? backStrokes : "—"}
                {backPlayed && (
                  <div style={{ fontSize: "0.62em", color: (() => { const v = backStrokes - backPar; return v < 0 ? "#00c44f" : v > 0 ? "#e74c3c" : "#4a6080"; })() }}>
                    {(() => { const v = backStrokes - backPar; return v === 0 ? "E" : v > 0 ? `+${v}` : String(v); })()}
                  </div>
                )}
              </td>
              <td style={{ ...subStyle, color: vsParColor, fontWeight: 800 }}>
                {(frontPlayed || backPlayed) ? totalStrokes : "—"}
                {vsPar != null && <div style={{ fontSize: "0.62em" }}>{vsParStr}</div>}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function scoreColor(n: number | null): string {
  if (n == null) return "#7f8c8d";
  if (n < 0) return "#00c44f";
  if (n > 0) return "#e74c3c";
  return "#8ba0b8";
}

function RoundPip({ score, label }: { score: number | null; label: string }) {
  const color = score == null ? "#3a5060" : scoreColor(score);
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "0.6em", color: "#4a6080", textTransform: "uppercase", marginBottom: 2 }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: "0.85em", color }}>
        {score == null ? "—" : String(score)}
      </div>
    </div>
  );
}

function StatusBadge({ status, madeCut }: { status: string | null; madeCut: boolean | null }) {
  if (madeCut === false) {
    return <span style={{ fontSize: "0.7em", fontWeight: 700, color: "#e74c3c", background: "#2a0f0f", padding: "2px 7px", borderRadius: 3, border: "1px solid #5a1a1a" }}>MISSED CUT</span>;
  }
  if (status === "W") {
    return <span style={{ fontSize: "0.7em", fontWeight: 800, color: "#f1c40f", background: "#1f1800", padding: "2px 7px", borderRadius: 3, border: "1px solid #5a4a00" }}>WON</span>;
  }
  if (madeCut === true) {
    return <span style={{ fontSize: "0.7em", fontWeight: 700, color: "#00c44f", background: "#0d2218", padding: "2px 7px", borderRadius: 3, border: "1px solid #004422" }}>MADE CUT</span>;
  }
  return null;
}

function MoveDelta({ delta }: { delta: number | null }) {
  if (delta == null || delta === 0) return null;
  const color = delta > 0 ? "#00c44f" : "#e74c3c";
  const arrow = delta > 0 ? "↑" : "↓";
  return <span style={{ fontSize: "0.75em", color, marginLeft: 8 }}>{arrow}{Math.abs(delta)}</span>;
}

export default function MyLineupLive({ picks, tournament, holeScores }: Props) {
  if (!picks.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No lineup found. Run the season strategy pipeline to generate picks.
      </div>
    );
  }

  return (
    <div>
      {tournament && (
        <p style={{ color: "#4a6080", fontSize: "0.8em", marginBottom: 14 }}>{tournament}</p>
      )}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        {picks.map((p, i) => {
          const totalNum = p.total_numeric;
          const totalStr = p.total ?? "—";
          const totalColor = scoreColor(totalNum);
          const borderColor = i === 0 ? "#f1c40f" : i === 1 ? "#00c44f" : "#4cb8ff";
          const playerHoles = holeScores ? holeScores[p.player] ?? null : null;
          const hasCards = playerHoles && Object.keys(playerHoles).length > 0;

          return (
            <div key={p.player} style={{
              flex: hasCards ? "1 1 100%" : "1 1 260px",
              minWidth: hasCards ? 0 : 220,
              background: "#0d1a30",
              borderLeft: `1px solid #1e3a5f`, borderRight: `1px solid #1e3a5f`, borderBottom: `1px solid #1e3a5f`,
              borderTop: `3px solid ${borderColor}`,
              borderRadius: 10, padding: "16px 18px",
            }}>
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                <div>
                  <Link
                    href={`/players?player=${encodeURIComponent(p.player)}`}
                    style={{ color: "#dde6f5", fontWeight: 800, fontSize: "1.05em", textDecoration: "none", display: "block" }}
                    onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                    onMouseLeave={e => (e.currentTarget.style.color = "#dde6f5")}
                  >
                    {p.player}
                  </Link>
                  <div style={{ marginTop: 4 }}>
                    <StatusBadge status={p.status} madeCut={p.made_cut} />
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: totalColor, fontWeight: 800, fontSize: "1.6em", lineHeight: 1 }}>{totalStr}</div>
                  <div style={{ color: "#4a6080", fontSize: "0.72em", marginTop: 3 }}>
                    {p.position ? `${p.position}` : "—"}
                    <MoveDelta delta={p.position_change} />
                  </div>
                  {p.thru && <div style={{ color: "#3a5060", fontSize: "0.68em" }}>Thru {p.thru}</div>}
                </div>
              </div>

              {/* Round score pips */}
              <div style={{ display: "flex", gap: 12, justifyContent: "flex-start" }}>
                <RoundPip score={p.R1} label="R1" />
                <RoundPip score={p.R2} label="R2" />
                <RoundPip score={p.R3} label="R3" />
                <RoundPip score={p.R4} label="R4" />
              </div>

              {/* Hole-by-hole scorecards */}
              {hasCards && Object.entries(playerHoles)
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([rnd, holes]) => (
                  <MiniScoreCard key={rnd} holes={holes} round={rnd} />
                ))
              }
            </div>
          );
        })}
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 10 }}>
        Your 3 picks for this week. Round scores are raw strokes.
      </p>
    </div>
  );
}
