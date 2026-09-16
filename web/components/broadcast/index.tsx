/**
 * Broadcast component kit — the shared vocabulary every redesigned screen
 * uses. Matches the approved design canvas: fairway green + yellow public
 * zone, scoreboard tables, accent-topped cards, uppercase section tags.
 * League-zone screens pass zone="league" where a variant exists.
 */

import React from "react";

type Zone = "public" | "league";

const Z = {
  public: { card: "var(--bc-card)", panel: "var(--bc-panel)", line: "var(--bc-line)",
            text: "var(--bc-text)", muted: "var(--bc-muted)", accent: "var(--bc-yellow)" },
  league: { card: "var(--lg-card)", panel: "var(--lg-panel)", line: "var(--lg-line)",
            text: "var(--lg-text)", muted: "var(--lg-muted)", accent: "var(--lg-accent)" },
};

/* ── Page header: kicker line + condensed display title ──────────────────── */
export function PageHead({ kicker, title, right, zone = "public" }: {
  kicker: string; title: string; right?: React.ReactNode; zone?: Zone;
}) {
  const z = Z[zone];
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 24, padding: "34px 0 18px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ fontSize: "0.8em", fontWeight: 700, letterSpacing: "0.16em",
                      textTransform: "uppercase", color: z.accent }}>{kicker}</div>
        <div style={{ fontWeight: 900, fontStretch: "118%", fontSize: "2.6em",
                      textTransform: "uppercase", letterSpacing: "-0.01em",
                      lineHeight: 1, color: z.text }}>{title}</div>
      </div>
      {right && <><div style={{ flexGrow: 1 }} />{right}</>}
    </div>
  );
}

/* ── Sub-tab row: yellow active pill, outlined idle ──────────────────────── */
export function SubTabs<T extends string>({ tabs, active, onChange, zone = "public" }: {
  tabs: { id: T; label: string }[]; active: T; onChange: (t: T) => void; zone?: Zone;
}) {
  const z = Z[zone];
  const activeFg = zone === "league" ? "#0a0d10" : "#081f14";
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 18 }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          cursor: "pointer",
          background: t.id === active ? z.accent : "transparent",
          color:      t.id === active ? activeFg : z.muted,
          border:     t.id === active ? `1px solid ${z.accent}` : `1px solid ${z.line}`,
          fontWeight: t.id === active ? 900 : 700,
          fontSize: "0.72em", textTransform: "uppercase", letterSpacing: "0.06em",
          padding: "9px 16px", borderRadius: 4, fontFamily: "inherit",
        }}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ── Panel: card surface, optional accent top rule ───────────────────────── */
export function Panel({ children, accent, zone = "public", style }: {
  children: React.ReactNode; accent?: string; zone?: Zone; style?: React.CSSProperties;
}) {
  const z = Z[zone];
  return (
    <div style={{
      background: zone === "league" ? z.card : z.panel,
      border: zone === "league" ? `1px solid ${z.line}` : "none",
      borderTop: accent ? `4px solid ${accent}` : undefined,
      borderRadius: 8, padding: 22, ...style,
    }}>
      {children}
    </div>
  );
}

/* ── Section tag: small uppercase label in accent color ──────────────────── */
export function SectionTag({ children, color, zone = "public" }: {
  children: React.ReactNode; color?: string; zone?: Zone;
}) {
  return (
    <div style={{ fontSize: "0.72em", fontWeight: 900, textTransform: "uppercase",
                  letterSpacing: "0.12em", color: color ?? Z[zone].accent, marginBottom: 10 }}>
      {children}
    </div>
  );
}

/* ── Scoreboard table ─────────────────────────────────────────────────────── */
export interface ScoreCol<Row> {
  key: string;
  label: string;
  width?: number | string;       // fixed columns; omit on the one flex column
  align?: "left" | "right";
  render: (row: Row) => React.ReactNode;
}

export function ScoreTable<Row>({ cols, rows, rowKey, highlight, zone = "public" }: {
  cols: ScoreCol<Row>[]; rows: Row[]; rowKey: (r: Row) => string;
  highlight?: (r: Row) => boolean; zone?: Zone;
}) {
  const z = Z[zone];
  const cellBase = (c: ScoreCol<Row>): React.CSSProperties => ({
    width: c.width, flexGrow: c.width == null ? 1 : 0, flexShrink: 0,
    textAlign: c.align ?? "left",
  });
  return (
    <div style={{ background: z.panel, borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "flex", gap: 14, padding: "12px 22px", background: z.card,
                    fontSize: "0.7em", fontWeight: 700, textTransform: "uppercase",
                    letterSpacing: "0.1em", color: z.muted }}>
        {cols.map(c => <div key={c.key} style={cellBase(c)}>{c.label}</div>)}
      </div>
      {rows.map((r, i) => (
        <div key={rowKey(r)} style={{
          display: "flex", gap: 14, alignItems: "center", padding: "13px 22px",
          borderBottom: i < rows.length - 1 ? `1px solid ${z.card}` : "none",
          background: highlight?.(r) ? "var(--bc-card-hi)" : "transparent",
          color: z.text,
        }}>
          {cols.map(c => <div key={c.key} style={cellBase(c)}>{c.render(r)}</div>)}
        </div>
      ))}
    </div>
  );
}

/* ── Stat strip: horizontal bar of big-number stats ──────────────────────── */
export function StatStrip({ title, stats, right, zone = "public" }: {
  title: string;
  stats: { value: string; label: string; color?: string }[];
  right?: React.ReactNode; zone?: Zone;
}) {
  const z = Z[zone];
  return (
    <div style={{ display: "flex", gap: 40, alignItems: "center", padding: "20px 26px",
                  background: z.panel, borderRadius: 8, flexWrap: "wrap" }}>
      <div style={{ fontWeight: 900, textTransform: "uppercase", fontSize: "0.82em",
                    letterSpacing: "0.09em", color: z.accent }}>{title}</div>
      <div style={{ display: "flex", gap: 36, flexWrap: "wrap" }}>
        {stats.map(s => (
          <div key={s.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ fontWeight: 900, fontSize: "1.35em", color: s.color ?? z.text }}>{s.value}</div>
            <div style={{ fontSize: "0.76em", color: z.muted }}>{s.label}</div>
          </div>
        ))}
      </div>
      {right && <><div style={{ flexGrow: 1 }} />{right}</>}
    </div>
  );
}

/* ── Trend + fit words: the human-label layer ────────────────────────────── */
export function trendWord(sgTrend: number | null | undefined): { word: string; color: string } {
  if (sgTrend == null || isNaN(sgTrend)) return { word: "—", color: "var(--bc-muted)" };
  if (sgTrend > 0.5)  return { word: "Hot",     color: "var(--bc-green)" };
  if (sgTrend > 0.1)  return { word: "Warming", color: "var(--bc-green)" };
  if (sgTrend < -0.5) return { word: "Cold",    color: "var(--bc-red)" };
  if (sgTrend < -0.1) return { word: "Cooling", color: "var(--bc-red)" };
  return { word: "Steady", color: "var(--bc-muted)" };
}

export function fitWord(fitSg: number | null | undefined): { word: string; color: string } {
  if (fitSg == null || isNaN(fitSg)) return { word: "—", color: "var(--bc-muted)" };
  if (fitSg > 0.5)  return { word: "Excellent", color: "var(--bc-green)" };
  if (fitSg > 0.15) return { word: "Good",      color: "var(--bc-green)" };
  if (fitSg > -0.15) return { word: "Average",  color: "var(--bc-muted)" };
  return { word: "Poor", color: "var(--bc-red)" };
}

/** Plain-language names for strokes-gained categories; jargon in the title attr. */
export const SG_LABELS: Record<string, string> = {
  sg_ott:  "Off the tee",
  sg_app:  "Approach",
  sg_arg:  "Short game",
  sg_putt: "Putting",
  sg_t2g:  "Tee to green",
  sg_total: "Overall",
};

export function pct(v: number | null | undefined, digits = 0): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
