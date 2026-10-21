"use client";

/**
 * HoleStrip — 18 tiles, front nine over back nine (Course Guide).
 * ================================================================
 * Each tile: hole number and par. Color only when the hole has real
 * scoring this week, and always with a word (Jack's lib/holeVerdict.ts),
 * so color is never the only signal. Not played = neutral, no label.
 * Tap a tile for yardage, scoring in plain words, and birdie / bogey rates.
 */
import { useState } from "react";
import { CourseHole } from "@/lib/api";
import { holeSentence, holeVerdict, type HoleLabel } from "@/lib/holeVerdict";

const LOOK: Record<HoleLabel, { word: string; color: string; bg: string }> = {
  chance: { word: "Birdie chance", color: "var(--bc-green)", bg: "color-mix(in srgb, var(--bc-green) 16%, var(--bc-panel))" },
  par:    { word: "Around par",    color: "var(--bc-text)",  bg: "var(--bc-panel)" },
  tough:  { word: "Tough",         color: "var(--bc-red-text)", bg: "color-mix(in srgb, var(--bc-red) 16%, var(--bc-panel))" },
};

function verdictOf(diff: number | null): HoleLabel | null {
  try { return holeVerdict(diff); } catch { return null; }   // until Jack's rule lands: neutral
}
function sentenceOf(diff: number | null): string {
  try { return holeSentence(diff); } catch {
    return diff == null ? "Not played yet this week." : `Scoring ${diff > 0 ? "+" : ""}${diff.toFixed(2)} vs par.`;
  }
}

export default function HoleStrip({ holes, played }: { holes: CourseHole[]; played: boolean }) {
  const [sel, setSel] = useState<number | null>(null);
  const nines = [holes.filter(h => h.hole_num <= 9), holes.filter(h => h.hole_num > 9)].filter(n => n.length);
  const hole = holes.find(h => h.hole_num === sel) ?? null;

  return (
    <section style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10, padding: "14px 16px", marginBottom: 14 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 16, color: "var(--bc-text)" }}>The 18 holes</h3>
      <p style={{ margin: "0 0 10px", color: "var(--bc-muted)", fontSize: 13 }}>
        {played ? "Shaded by how each hole is playing this week. Tap a hole for details."
          : "Hole scoring appears once round 1 is underway. Tap a hole for its yardage."}
      </p>
      {nines.map((nine, i) => (
        <div key={i} style={{ display: "grid", gridTemplateColumns: "repeat(9, minmax(0, 1fr))", gap: 4, marginBottom: 4 }}>
          {nine.map(h => {
            const v = verdictOf(h.scoring_diff);
            const look = v ? LOOK[v] : null;
            const on = sel === h.hole_num;
            return (
              <button key={h.hole_num} type="button" aria-pressed={on}
                aria-label={`Hole ${h.hole_num}, par ${h.hole_par}${look ? `, ${look.word}` : ""}`}
                onClick={() => setSel(on ? null : h.hole_num)}
                style={{
                  minHeight: 52, padding: "4px 0", borderRadius: 6, cursor: "pointer", fontFamily: "inherit",
                  background: look?.bg ?? "var(--bc-card)",
                  border: `1px solid ${on ? "var(--bc-yellow)" : "var(--bc-line)"}`,
                  color: "var(--bc-text)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1,
                }}>
                <span style={{ fontSize: 15, fontWeight: 800 }}>{h.hole_num}</span>
                <span style={{ fontSize: 11, color: "var(--bc-muted)" }}>Par {h.hole_par}</span>
                {/* The word, so color is never the only signal (short form on the tile). */}
                {look && <span style={{ fontSize: 10, fontWeight: 700, color: look.color }}>
                  {v === "chance" ? "Easy" : v === "tough" ? "Hard" : "Par"}
                </span>}
              </button>
            );
          })}
        </div>
      ))}
      {hole && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--bc-line)", fontSize: 14, color: "var(--bc-text)", lineHeight: 1.6 }}>
          <strong>Hole {hole.hole_num}</strong> · Par {hole.hole_par}
          {hole.hole_yards != null && <> · {hole.hole_yards.toLocaleString()} yards</>}
          {(() => { const v = verdictOf(hole.scoring_diff); return v && <> · <span style={{ color: LOOK[v].color, fontWeight: 700 }}>{LOOK[v].word}</span></>; })()}
          <div style={{ color: "var(--bc-muted)" }}>{sentenceOf(hole.scoring_diff)}</div>
          {hole.birdies != null && hole.bogeys != null && (
            <div style={{ color: "var(--bc-muted)" }}>
              Birdies {hole.birdies.toFixed(0)}% of the time · bogeys {hole.bogeys.toFixed(0)}%.
            </div>
          )}
        </div>
      )}
    </section>
  );
}
