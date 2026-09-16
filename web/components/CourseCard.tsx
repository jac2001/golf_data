"use client";

import { CourseResponse, CourseHole, CourseHistory } from "@/lib/api";

type Props = { data: CourseResponse };

// Returns a color based on vs-par difficulty
function diffColor(diff: number | null): string {
  if (diff == null) return "var(--bc-muted)";
  if (diff >  0.5)  return "var(--bc-red)";
  if (diff >  0.2)  return "#f39c12";
  if (diff > -0.1)  return "var(--bc-muted)";
  if (diff > -0.3)  return "#27ae60";
  return "var(--bc-green)";
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
        <div style={{ width: `${bPct}%`, minWidth: b > 0 ? 4 : 0, height: 6, background: "var(--bc-green)", borderRadius: 3 }} />
      </div>
      <div style={{ width: 1, height: 10, background: "var(--bc-line)", flexShrink: 0 }} />
      {/* Bogey bar — grows left from center */}
      <div style={{ flex: 1 }}>
        <div style={{ width: `${bgPct}%`, minWidth: bg > 0 ? 4 : 0, height: 6, background: "var(--bc-red)", borderRadius: 3 }} />
      </div>
    </div>
  );
}

function HoleRow({ hole, isAlt }: { hole: CourseHole; isAlt: boolean }) {
  const diff = hole.scoring_diff;
  const dColor = diffColor(diff);
  const bg = isAlt ? "var(--bc-panel)" : "var(--bc-panel)";

  return (
    <tr style={{ background: bg }}>
      {/* Difficulty stripe */}
      <td style={{ width: 3, padding: 0, background: dColor }} />

      {/* Hole number */}
      <td style={{ ...cell, color: "var(--bc-yellow)", fontWeight: 700, width: 36 }}>
        {hole.hole_num}
      </td>

      {/* Par */}
      <td style={{ ...cell, color: "var(--bc-muted)", width: 36 }}>
        {hole.hole_par}
      </td>

      {/* Yards */}
      <td style={{ ...cell, color: "var(--bc-muted)", width: 60 }}>
        {hole.hole_yards ?? "—"}
      </td>

      {/* Avg score */}
      <td style={{ ...cell, color: "var(--bc-text)", width: 72 }}>
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
          <span style={{ fontSize: "0.72em", color: "var(--bc-green)", width: 36, textAlign: "right", flexShrink: 0 }}>
            {hole.birdies != null ? `${hole.birdies.toFixed(0)}%` : "—"}
          </span>
          <BirdieBogeyBar birdies={hole.birdies} bogeys={hole.bogeys} />
          <span style={{ fontSize: "0.72em", color: "var(--bc-red)", width: 36, flexShrink: 0 }}>
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
    <tr style={{ background: "#0a1628", borderTop: "1px solid var(--bc-line)" }}>
      <td style={{ width: 3, padding: 0 }} />
      <td colSpan={2} style={{ ...cell, color: "var(--bc-muted)", fontWeight: 700, fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </td>
      <td style={{ ...cell, color: "var(--bc-muted)", fontWeight: 600 }}>{yards}</td>
      <td style={{ ...cell, color: "var(--bc-text)", fontWeight: 600 }}>{fmt(avgSum)}</td>
      <td colSpan={4} style={{ ...cell, color: "#3a5060", fontSize: "0.75em" }}>par {par}</td>
    </tr>
  );
}

export default function CourseCard({ data }: Props) {
  if (!data.holes.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--bc-muted)", background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
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

  const unplayedCount = data.holes.filter(h => h.scoring_avg == null).length;

  return (
    <div>
      {data.history && <CourseHistorySection history={data.history} unplayedCount={unplayedCount} />}

      {/* Header strip */}
      <div style={{
        background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: "10px 10px 0 0",
        padding: "14px 18px", display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start",
      }}>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Course</div>
          <div style={{ color: "var(--bc-text)", fontWeight: 800, fontSize: "1em", marginTop: 2 }}>{data.course_name || "—"}</div>
          <div style={{ color: "var(--bc-muted)", fontSize: "0.75em", marginTop: 4 }}>
            Par {data.par ?? "—"} &nbsp;·&nbsp; {data.yardage?.toLocaleString() ?? "—"} yards
          </div>
        </div>

        {/* Hardest / easiest callouts */}
        {hardest && (
          <Callout label="Hardest Hole" hole={hardest} color="var(--bc-red)" />
        )}
        {easiest && (
          <Callout label="Easiest Hole" hole={easiest} color="var(--bc-green)" />
        )}

        {/* Legend */}
        <div style={{ fontSize: "0.65em", color: "#2a4060", display: "flex", gap: 10, alignSelf: "flex-end", flexWrap: "wrap" }}>
          <span><span style={{ color: "var(--bc-green)" }}>■</span> Birdie%</span>
          <span><span style={{ color: "var(--bc-red)" }}>■</span> Bogey%</span>
          <span><span style={{ color: "#f39c12" }}>■</span> Hard</span>
          <span><span style={{ color: "var(--bc-red)" }}>■</span> Very hard</span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", borderLeft: "1px solid var(--bc-line)", borderRight: "1px solid var(--bc-line)", borderBottom: "1px solid var(--bc-line)", borderTop: "none", borderRadius: "0 0 10px 10px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
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
                <span style={{ color: "var(--bc-green)" }}>Birdie</span>
                <span style={{ color: "#3a5060", margin: "0 6px" }}>·</span>
                <span style={{ color: "var(--bc-red)" }}>Bogey</span>
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

function CourseHistorySection({ history, unplayedCount = 0 }: { history: CourseHistory; unplayedCount?: number }) {
  const { avg_score_by_round: r, scoring_distribution: sd, winning_scores } = history;
  const roundVals = [r.r1, r.r2, r.r3, r.r4].filter((v): v is number => v != null);
  const minR = roundVals.length ? Math.min(...roundVals) : null;
  const maxR = roundVals.length ? Math.max(...roundVals) : null;

  // Color a round's average relative to the other 3 rounds at this course —
  // not vs par, since we don't have reliable per-round par history here.
  function roundColor(v: number | null): string {
    if (v == null || minR == null || maxR == null || minR === maxR) return "var(--bc-muted)";
    const t = (v - minR) / (maxR - minR); // 0 = easiest round, 1 = toughest
    return t > 0.66 ? "var(--bc-red)" : t > 0.33 ? "#f39c12" : "var(--bc-green)";
  }

  return (
    <div style={{ marginBottom: 16, background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10, padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <span style={{ color: "var(--bc-text)", fontWeight: 800, fontSize: "0.95em" }}>Course History</span>
        <span style={{ color: "var(--bc-muted)", fontSize: "0.75em" }}>
          {history.editions} past edition{history.editions !== 1 ? "s" : ""}
          {history.years.length > 0 && ` · ${history.years[0]}–${history.years[history.years.length - 1]}`}
        </span>
      </div>

      {unplayedCount > 0 && (
        <div style={{
          background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
          padding: "6px 10px", marginBottom: 14, fontSize: "0.75em", color: "var(--bc-muted)",
        }}>
          {unplayedCount} hole{unplayedCount > 1 ? "s" : ""} below {unplayedCount > 1 ? "haven't" : "hasn't"} been played yet this week (showing —) —
          the trends here are how this course has played across {history.editions} past edition{history.editions !== 1 ? "s" : ""} in the meantime.
        </div>
      )}

      <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
        {/* Round-by-round average score */}
        <div style={{ minWidth: 220 }}>
          <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Avg Score by Round
          </div>
          <div style={{ display: "flex", gap: 14 }}>
            {([["R1", r.r1], ["R2", r.r2], ["R3", r.r3], ["R4", r.r4]] as const).map(([label, v]) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "1.05em", fontWeight: 800, color: roundColor(v) }}>{v != null ? v.toFixed(1) : "—"}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Scoring distribution */}
        <div style={{ minWidth: 220 }}>
          <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Avg Per Round
          </div>
          <div style={{ display: "flex", gap: 18 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.65em", color: "var(--bc-green)", marginBottom: 2 }}>Birdies</div>
              <div style={{ fontSize: "1.05em", fontWeight: 800, color: "var(--bc-green)" }}>{sd.avg_birdies != null ? sd.avg_birdies.toFixed(2) : "—"}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.65em", color: "var(--bc-red)", marginBottom: 2 }}>Bogeys</div>
              <div style={{ fontSize: "1.05em", fontWeight: 800, color: "var(--bc-red)" }}>{sd.avg_bogeys != null ? sd.avg_bogeys.toFixed(2) : "—"}</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.65em", color: "var(--bc-yellow)", marginBottom: 2 }}>Eagles</div>
              <div style={{ fontSize: "1.05em", fontWeight: 800, color: "var(--bc-yellow)" }}>{sd.avg_eagles != null ? sd.avg_eagles.toFixed(2) : "—"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Winning score trend */}
      {winning_scores.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <div style={{ fontSize: "0.62em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Winning Score by Year
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {winning_scores.map(w => (
              <div key={w.year} style={{
                background: "#081220", border: "1px solid var(--bc-line)", borderRadius: 6,
                padding: "6px 10px", minWidth: 86, textAlign: "center",
              }}>
                <div style={{ fontSize: "0.62em", color: "var(--bc-muted)" }}>{w.year}</div>
                <div style={{ fontSize: "0.95em", fontWeight: 800, color: "var(--bc-green)", marginTop: 2 }}>{w.to_par || "—"}</div>
                <div style={{ fontSize: "0.65em", color: "var(--bc-muted)", marginTop: 2, whiteSpace: "nowrap" }}>{w.winner_name}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Callout({ label, hole, color }: { label: string; hole: CourseHole; color: string }) {
  return (
    <div style={{ background: `${color}11`, border: `1px solid ${color}33`, borderRadius: 8, padding: "8px 14px", minWidth: 100 }}>
      <div style={{ fontSize: "0.6em", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</div>
      <div style={{ fontWeight: 800, color, fontSize: "1.1em", marginTop: 2 }}>Hole {hole.hole_num}</div>
      <div style={{ fontSize: "0.72em", color: "var(--bc-muted)", marginTop: 2 }}>
        Par {hole.hole_par} · {fmtDiff(hole.scoring_diff)} vs par
      </div>
    </div>
  );
}

const th: React.CSSProperties = {
  color: "var(--bc-muted)", fontSize: "0.65em", fontWeight: 700,
  textTransform: "uppercase", letterSpacing: "0.05em",
  padding: "6px 8px", borderBottom: "1px solid var(--bc-line)",
  textAlign: "center", whiteSpace: "nowrap",
};

const cell: React.CSSProperties = {
  padding: "6px 8px",
  borderBottom: "1px solid #0f2236",
  fontSize: "0.83em",
  textAlign: "center",
};
