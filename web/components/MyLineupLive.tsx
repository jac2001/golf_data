"use client";

import { MyPickPlayer } from "@/lib/api";

type Props = {
  picks: MyPickPlayer[];
  tournament: string;
};

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

export default function MyLineupLive({ picks, tournament }: Props) {
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

          return (
            <div key={p.player} style={{
              flex: "1 1 260px", minWidth: 220,
              background: "#0d1a30", border: `1px solid #1e3a5f`,
              borderTop: `3px solid ${borderColor}`,
              borderRadius: 10, padding: "16px 18px",
            }}>
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                <div>
                  <div style={{ color: "#dde6f5", fontWeight: 800, fontSize: "1.05em" }}>{p.player}</div>
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

              {/* Round scores */}
              <div style={{ display: "flex", gap: 12, justifyContent: "flex-start" }}>
                <RoundPip score={p.R1} label="R1" />
                <RoundPip score={p.R2} label="R2" />
                <RoundPip score={p.R3} label="R3" />
                <RoundPip score={p.R4} label="R4" />
              </div>
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
