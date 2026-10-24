"use client";
/** Who decides your matchup (lib/matchupDiff.ts): the sentence, then only the
 *  golfers who move the gap, side by side. Shared golfers fold into one line. */
import type { DiffGolfer, MatchupDiff } from "@/lib/matchupDiff";
import { listNames } from "@/lib/matchupDiff";

const toPar = (v: number | null | undefined) => v == null ? "" : v === 0 ? "E" : v > 0 ? `+${v}` : String(v);

function Column({ title, golfers }: { title: string; golfers: DiffGolfer[] }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, color: "var(--bc-muted)",
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{title}</div>
      {golfers.length === 0 && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.86em)" }}>None</div>}
      {golfers.map(g => (
        <div key={g.name} style={{ display: "flex", gap: 6, alignItems: "baseline", fontSize: "max(var(--fs-min), 0.86em)", padding: "2px 0" }}>
          <span style={{ fontWeight: 800, minWidth: 34, fontVariantNumeric: "tabular-nums" }}>{g.position}</span>
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.name}</span>
          <span style={{ color: "var(--bc-muted)", fontVariantNumeric: "tabular-nums" }}>
            {toPar(g.to_par)}{g.thru ? ` · ${g.thru}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function MatchupFocus({ diff }: { diff: MatchupDiff }) {
  return (
    <div style={{ margin: "10px 0 12px", padding: "10px 12px", border: "1px solid var(--bc-line)",
      borderRadius: 10, background: "var(--bc-panel)" }}>
      <div style={{ fontSize: "max(var(--fs-min), 0.9em)", fontWeight: 700, marginBottom: 8 }}>{diff.sentence}</div>
      {(diff.mine.length > 0 || diff.theirs.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Column title="Yours" golfers={diff.mine} />
          <Column title={diff.rival.user_name} golfers={diff.theirs} />
        </div>
      )}
      {diff.shared.length > 0 && (
        <div style={{ marginTop: 8, fontSize: "max(var(--fs-min), 0.8em)", color: "var(--bc-muted)" }}>
          Both of you: {listNames(diff.shared)} (cancels out)
        </div>
      )}
    </div>
  );
}