"use client";

import { useState } from "react";
import { DgHole, HoleWaveStats } from "@/lib/api";

type Wave = "total" | "morning" | "afternoon";

type Props = {
  holes:   DgHole[];
  round:   number | null;
  updated: string;
};

const BG     = "#0d1a30";
const BG_ALT = "#0a1525";
const BORDER = "#1e3a5f";
const MUTED  = "#5a7090";
const GREEN  = "#00c44f";
const RED    = "#e74c3c";
const GOLD   = "#f1c40f";
const BLUE   = "#4cb8ff";

// vs_par → difficulty color (positive = hard = red, negative = easy = green)
function diffColor(vp: number | null): string {
  if (vp == null) return MUTED;
  if (vp <= -0.15) return GREEN;
  if (vp <= -0.05) return "#4cb856";
  if (vp < 0.05)   return "#8ba0b8";
  if (vp < 0.15)   return "#e0a040";
  if (vp < 0.30)   return "#e06040";
  return RED;
}

function fmtVsPar(vp: number | null): string {
  if (vp == null) return "—";
  return vp >= 0 ? `+${vp.toFixed(3)}` : vp.toFixed(3);
}

function fmtPct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toFixed(1)}%`;
}

// Mini stacked bar: birdie=green, par=grey, bogey=blue, double=purple
function DistBar({ birdie, par, bogey, dbl, thru }: {
  birdie: number; par: number; bogey: number; dbl: number; thru: number;
}) {
  if (!thru) return <span style={{ color: "#2a3a4a", fontSize: "0.7em" }}>—</span>;
  const total = birdie + par + bogey + dbl;
  const pct = (n: number) => total > 0 ? Math.round(n / total * 100) : 0;
  const segments = [
    { w: pct(birdie), color: GREEN   },
    { w: pct(par),    color: "#3a5060" },
    { w: pct(bogey),  color: BLUE    },
    { w: pct(dbl),    color: "#7030a0" },
  ].filter(s => s.w > 0);

  return (
    <div style={{ display: "flex", height: 8, borderRadius: 3, overflow: "hidden", minWidth: 80 }}>
      {segments.map((s, i) => (
        <div key={i} style={{ width: `${s.w}%`, background: s.color }} />
      ))}
    </div>
  );
}

function waveData(hole: DgHole, wave: Wave): HoleWaveStats & { avg_score: number | null; vs_par: number | null } {
  if (wave === "morning")   return hole.morning;
  if (wave === "afternoon") return hole.afternoon;
  return {
    players_thru: hole.players_thru,
    avg_score:    hole.avg_score,
    vs_par:       hole.vs_par,
    birdies:      hole.birdies,
    pars:         hole.pars,
    bogeys:       hole.bogeys,
    doubles:      hole.doubles,
    eagles:       hole.eagles,
    birdie_pct:   hole.birdie_pct,
    bogey_pct:    hole.bogey_pct,
    double_pct:   hole.double_pct,
  };
}

export default function HoleStatsTable({ holes, round, updated }: Props) {
  const [wave, setWave] = useState<Wave>("total");

  if (!holes.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: BG, border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        No hole stats available yet.
      </div>
    );
  }

  const th: React.CSSProperties = {
    background: "#0a1628", color: MUTED,
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: `1px solid ${BORDER}`,
    textAlign: "center", whiteSpace: "nowrap",
  };

  // Summary stats
  const hardest = [...holes].sort((a, b) => (b.vs_par ?? -99) - (a.vs_par ?? -99))[0];
  const easiest = [...holes].sort((a, b) => (a.vs_par ?? 99) - (b.vs_par ?? 99))[0];

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.75em", color: MUTED, marginRight: 4 }}>Wave:</span>
        {(["total", "morning", "afternoon"] as Wave[]).map(w => (
          <button key={w} onClick={() => setWave(w)} style={{
            background: wave === w ? "#0d2e18" : "#0a1525",
            border: `1px solid ${wave === w ? GREEN : BORDER}`,
            color: wave === w ? GREEN : MUTED,
            borderRadius: 6, padding: "4px 12px",
            fontSize: "0.8em", fontWeight: wave === w ? 700 : 400, cursor: "pointer",
          }}>
            {w.charAt(0).toUpperCase() + w.slice(1)}
          </button>
        ))}
        <span style={{ fontSize: "0.68em", color: "#3a5060", marginLeft: 8 }}>
          {round && `Round ${round}`}{updated && ` · DG ${updated}`}
        </span>
      </div>

      {/* Summary chips */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        {hardest && (
          <div style={{ background: "#1a0808", border: `1px solid ${RED}44`, borderRadius: 8, padding: "6px 14px", fontSize: "0.78em" }}>
            <span style={{ color: "#5a3030" }}>Hardest: </span>
            <span style={{ color: RED, fontWeight: 700 }}>Hole {hardest.hole}</span>
            <span style={{ color: "#4a3030" }}> ({fmtVsPar(hardest.vs_par)})</span>
          </div>
        )}
        {easiest && (
          <div style={{ background: "#081a08", border: `1px solid ${GREEN}44`, borderRadius: 8, padding: "6px 14px", fontSize: "0.78em" }}>
            <span style={{ color: "#2a5030" }}>Easiest: </span>
            <span style={{ color: GREEN, fontWeight: 700 }}>Hole {easiest.hole}</span>
            <span style={{ color: "#2a4030" }}> ({fmtVsPar(easiest.vs_par)})</span>
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: BG }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "center", width: 36 }}>Hole</th>
              <th style={{ ...th, textAlign: "center", width: 32 }}>Par</th>
              <th style={{ ...th }}>Yards</th>
              <th style={{ ...th }}>Players</th>
              <th style={{ ...th }}>Avg Score</th>
              <th style={{ ...th, color: "#e0a040" }}>vs Par</th>
              <th style={{ ...th, color: GOLD }}>Eagles</th>
              <th style={{ ...th, color: GREEN }}>Birdies</th>
              <th style={{ ...th, color: MUTED }}>Pars</th>
              <th style={{ ...th, color: BLUE }}>Bogeys</th>
              <th style={{ ...th, color: "#a060d0" }}>Dbl+</th>
              <th style={{ ...th, minWidth: 90 }}>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {holes.map((hole, i) => {
              const bg = i % 2 === 0 ? BG : BG_ALT;
              const w = waveData(hole, wave);
              const vp = w.vs_par;
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid #0f2236",
                background: bg, textAlign: "center", fontSize: "0.83em",
              };

              return (
                <tr key={hole.hole}>
                  <td style={{ ...td, fontWeight: 800, color: "#dde6f5" }}>{hole.hole}</td>
                  <td style={{ ...td, color: MUTED }}>par {hole.par}</td>
                  <td style={{ ...td, color: "#4a6080" }}>{hole.yardage ?? "—"}</td>
                  <td style={{ ...td, color: MUTED }}>{w.players_thru ?? "—"}</td>
                  <td style={{ ...td, color: diffColor(vp), fontWeight: 600 }}>
                    {w.avg_score != null ? w.avg_score.toFixed(3) : "—"}
                  </td>
                  <td style={{ ...td, color: diffColor(vp), fontWeight: 700 }}>
                    {fmtVsPar(vp)}
                  </td>
                  <td style={{ ...td, color: w.eagles > 0 ? GOLD : "#2a3a4a" }}>
                    {w.eagles > 0 ? w.eagles : "—"}
                  </td>
                  <td style={{ ...td, color: w.birdies > 0 ? GREEN : "#2a3a4a" }}>
                    {w.birdies > 0 ? `${w.birdies} (${fmtPct(w.birdie_pct)})` : "—"}
                  </td>
                  <td style={{ ...td, color: MUTED }}>{w.pars > 0 ? w.pars : "—"}</td>
                  <td style={{ ...td, color: w.bogeys > 0 ? BLUE : "#2a3a4a" }}>
                    {w.bogeys > 0 ? `${w.bogeys} (${fmtPct(w.bogey_pct)})` : "—"}
                  </td>
                  <td style={{ ...td, color: w.doubles > 0 ? "#a060d0" : "#2a3a4a" }}>
                    {w.doubles > 0 ? `${w.doubles} (${fmtPct(w.double_pct)})` : "—"}
                  </td>
                  <td style={{ ...td }}>
                    <DistBar
                      birdie={w.birdies} par={w.pars}
                      bogey={w.bogeys}   dbl={w.doubles}
                      thru={w.players_thru}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>
        vs Par: negative = playing easy (green), positive = playing hard (red) · distribution bar: <span style={{ color: GREEN }}>birdie</span> / <span style={{ color: "#3a5060" }}>par</span> / <span style={{ color: BLUE }}>bogey</span> / <span style={{ color: "#7030a0" }}>double+</span>
      </p>
    </div>
  );
}
