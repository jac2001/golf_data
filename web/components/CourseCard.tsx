"use client";

import { CourseResponse, CourseHole } from "@/lib/api";

type Props = { data: CourseResponse };

// Returns a color based on vs-par difficulty
function diffColor(diff: number | null): string {
  if (diff == null) return "#4a6080";
  if (diff >  0.5)  return "#e74c3c";
  if (diff >  0.2)  return "#f39c12";
  if (diff > -0.1)  return "#5a7090";
  if (diff > -0.3)  return "#27ae60";
  return "#00c44f";
}

function diffLabel(diff: number | null): string {
  if (diff == null) return "";
  if (diff >  0.5)  return "Very Hard";
  if (diff >  0.2)  return "Hard";
  if (diff > -0.1)  return "Neutral";
  if (diff > -0.3)  return "Easy";
  return "Very Easy";
}

function fmt(v: number | null, d = 2): string {
  if (v == null) return "—";
  return v.toFixed(d);
}

function fmtDiff(diff: number | null): string {
  if (diff == null) return "—";
  return diff > 0 ? `+${diff.toFixed(2)}` : diff.toFixed(2);
}

// Visual bar: birdie% (green, left) vs bogey% (red, right) with neutral in between
function BirdieBogeyBar({ birdies, bogeys }: { birdies: number | null; bogeys: number | null }) {
  const b = birdies ?? 0;
  const bg = bogeys  ?? 0;
  const max = Math.max(b, bg, 25); // normalize against at least 25%
  const bPct  = Math.min((b  / max) * 100, 100);
  const bgPct = Math.min((bg / max) * 100, 100);
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center", width: "100%", minWidth: 120 }}>
      {/* Birdie bar — grows right from center */}
      <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
        <div style={{ width: `${bPct}%`, minWidth: b > 0 ? 4 : 0, height: 6, background: "#00c44f", borderRadius: 3 }} />
      </div>
      <div style={{ width: 1, height: 10, background: "#1e3a5f", flexShrink: 0 }} />
      {/* Bogey bar — grows left from center */}
      <div style={{ flex: 1 }}>
        <div style={{ width: `${bgPct}%`, minWidth: bg > 0 ? 4 : 0, height: 6, background: "#e74c3c", borderRadius: 3 }} />
      </div>
    </div>
  );
}

function HoleRow({ hole, isAlt }: { hole: CourseHole; isAlt: boolean }) {
  const diff = hole.scoring_diff;
  const dColor = diffColor(diff);
  const bg = isAlt ? "#0a1525" : "#0d1a30";

  return (
    <tr style={{ background: bg }}>
      {/* Difficulty stripe */}
      <td style={{ width: 3, padding: 0, background: dColor }} />

      {/* Hole number */}
      <td style={{ ...cell, color: "#4cb8ff", fontWeight: 700, width: 36 }}>
        {hole.hole_num}
      </td>

      {/* Par */}
      <td style={{ ...cell, color: "#8ba0b8", width: 36 }}>
        {hole.hole_par}
      </td>

      {/* Yards */}
      <td style={{ ...cell, color: "#7f8c8d", width: 60 }}>
        {hole.hole_yards ?? "—"}
      </td>

      {/* Avg score */}
      <td style={{ ...cell, color: "#dde6f5", width: 72 }}>
        {fmt(hole.scoring_avg)}
      </td>

      {/* vs Par */}
      <td style={{ ...cell, color: dColor, fontWeight: diff != null && Math.abs(diff) > 0.1 ? 700 : 400, width: 56 }}>
        {fmtDiff(diff)}
      </td>

      {/* Difficulty label */}
      <td style={{ ...cell, color: dColor, fontSize: "0.68em", width: 70 }}>
        {diffLabel(diff)}
      </td>

      {/* Birdie vs Bogey visual bar */}
      <td style={{ ...cell, minWidth: 160, paddingLeft: 10, paddingRight: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: "0.72em", color: "#00c44f", width: 36, textAlign: "right", flexShrink: 0 }}>
            {hole.birdies != null ? `${hole.birdies.toFixed(0)}%` : "—"}
          </span>
          <BirdieBogeyBar birdies={hole.birdies} bogeys={hole.bogeys} />
          <span style={{ fontSize: "0.72em", color: "#e74c3c", width: 36, flexShrink: 0 }}>
            {hole.bogeys != null ? `${hole.bogeys.toFixed(0)}%` : "—"}
          </span>
        </div>
      </td>

      {/* Difficulty rank */}
      <td style={{ ...cell, color: "#3a5060", width: 40 }}>
        {hole.difficulty_rank ?? "—"}
      </td>
    </tr>
  );
}

function NineSubtotal({ holes, label }: { holes: CourseHole[]; label: string }) {
  const yards = holes.reduce((s, h) => s + (h.hole_yards ?? 0), 0);
  const par   = holes.reduce((s, h) => s + (h.hole_par   ?? 0), 0);
  const avgSum = holes.reduce((s, h) => s + (h.scoring_avg ?? 0), 0);
  return (
    <tr style={{ background: "#0a1628", borderTop: "1px solid #1e3a5f" }}>
      <td style={{ width: 3, padding: 0 }} />
      <td colSpan={2} style={{ ...cell, color: "#4a6080", fontWeight: 700, fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </td>
      <td style={{ ...cell, color: "#7f8c8d", fontWeight: 600 }}>{yards}</td>
      <td style={{ ...cell, color: "#dde6f5", fontWeight: 600 }}>{fmt(avgSum)}</td>
      <td colSpan={4} style={{ ...cell, color: "#3a5060", fontSize: "0.75em" }}>par {par}</td>
    </tr>
  );
}

export default function CourseCard({ data }: Props) {
  if (!data.holes.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No course data available.
      </div>
    );
  }

  const front = data.holes.filter(h => h.hole_num <= 9);
  const back  = data.holes.filter(h => h.hole_num >  9);

  // Find hardest + easiest holes for callouts
  const sorted = [...data.holes].filter(h => h.scoring_diff != null).sort((a, b) => (b.scoring_diff ?? 0) - (a.scoring_diff ?? 0));
  const hardest = sorted[0];
  const easiest = sorted[sorted.length - 1];

  return (
    <div>
      {/* Header strip */}
      <div style={{
        background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: "10px 10px 0 0",
        padding: "14px 18px", display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start",
      }}>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: "0.62em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em" }}>Course</div>
          <div style={{ color: "#dde6f5", fontWeight: 800, fontSize: "1em", marginTop: 2 }}>{data.course_name || "—"}</div>
          <div style={{ color: "#5a7090", fontSize: "0.75em", marginTop: 4 }}>
            Par {data.par ?? "—"} &nbsp;·&nbsp; {data.yardage?.toLocaleString() ?? "—"} yards
          </div>
        </div>

        {/* Hardest / easiest callouts */}
        {hardest && (
          <Callout label="Hardest Hole" hole={hardest} color="#e74c3c" />
        )}
        {easiest && (
          <Callout label="Easiest Hole" hole={easiest} color="#00c44f" />
        )}

        {/* Legend */}
        <div style={{ fontSize: "0.65em", color: "#2a4060", display: "flex", gap: 10, alignSelf: "flex-end", flexWrap: "wrap" }}>
          <span><span style={{ color: "#00c44f" }}>■</span> Birdie%</span>
          <span><span style={{ color: "#e74c3c" }}>■</span> Bogey%</span>
          <span><span style={{ color: "#f39c12" }}>■</span> Hard</span>
          <span><span style={{ color: "#e74c3c" }}>■</span> Very hard</span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderTop: "none", borderRadius: "0 0 10px 10px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
          <thead>
            <tr style={{ background: "#0a1628" }}>
              <th style={{ width: 3, padding: 0 }} />
              <th style={{ ...th, textAlign: "center" }}>Hole</th>
              <th style={{ ...th }}>Par</th>
              <th style={{ ...th }}>Yds</th>
              <th style={{ ...th }}>Avg</th>
              <th style={{ ...th }}>vs Par</th>
              <th style={{ ...th }}></th>
              <th style={{ ...th, textAlign: "center", minWidth: 180 }}>
                <span style={{ color: "#00c44f" }}>Birdie</span>
                <span style={{ color: "#3a5060", margin: "0 6px" }}>·</span>
                <span style={{ color: "#e74c3c" }}>Bogey</span>
              </th>
              <th style={{ ...th }}>Rank</th>
            </tr>
          </thead>
          <tbody>
            {front.map((h, i) => <HoleRow key={h.hole_num} hole={h} isAlt={i % 2 === 1} />)}
            <NineSubtotal holes={front} label="Front 9" />
            {back.map((h, i) => <HoleRow key={h.hole_num} hole={h} isAlt={i % 2 === 1} />)}
            <NineSubtotal holes={back} label="Back 9" />
          </tbody>
        </table>
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.68em", marginTop: 6 }}>
        vs Par = avg strokes above/below par · Rank 1 = hardest hole on course
      </p>
    </div>
  );
}

function Callout({ label, hole, color }: { label: string; hole: CourseHole; color: string }) {
  return (
    <div style={{ background: `${color}11`, border: `1px solid ${color}33`, borderRadius: 8, padding: "8px 14px", minWidth: 100 }}>
      <div style={{ fontSize: "0.6em", color: "#4a6080", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
      <div style={{ fontWeight: 800, color, fontSize: "1.1em", marginTop: 2 }}>Hole {hole.hole_num}</div>
      <div style={{ fontSize: "0.72em", color: "#7f8c8d", marginTop: 2 }}>
        Par {hole.hole_par} · {fmtDiff(hole.scoring_diff)} vs par
      </div>
    </div>
  );
}

const th: React.CSSProperties = {
  color: "#5a7090", fontSize: "0.65em", fontWeight: 700,
  textTransform: "uppercase", letterSpacing: "0.05em",
  padding: "6px 8px", borderBottom: "1px solid #1e3a5f",
  textAlign: "center", whiteSpace: "nowrap",
};

const cell: React.CSSProperties = {
  padding: "6px 8px",
  borderBottom: "1px solid #0f2236",
  fontSize: "0.83em",
  textAlign: "center",
};
