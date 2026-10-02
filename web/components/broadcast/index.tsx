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
                      textTransform: "uppercase", color: z.muted }}>{kicker}</div>
        <div style={{ fontWeight: 900, fontStretch: "118%", fontSize: "2.6em",
                      textTransform: "uppercase", letterSpacing: "-0.01em",
                      lineHeight: 1, color: z.text }}>{title}</div>
      </div>
      {right && <><div style={{ flexGrow: 1 }} />{right}</>}
    </div>
  );
}

/* ── Sub-tab row: quiet bar, active = text + thin accent underline ────────
   Tabs are navigation, not actions — they shouldn't compete with the
   screen's one primary button, so no filled pills. */
export function SubTabs<T extends string>({ tabs, active, onChange, zone = "public" }: {
  tabs: { id: T; label: string; count?: number }[]; active: T; onChange: (t: T) => void; zone?: Zone;
}) {
  const z = Z[zone];
  return (
    <div role="tablist" style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 18,
                                 borderBottom: `1px solid ${z.line}` }}>
      {tabs.map(t => {
        const on = t.id === active;
        return (
          <button key={t.id} role="tab" aria-selected={on} onClick={() => onChange(t.id)} style={{
            cursor: "pointer", background: "transparent", border: "none",
            borderBottom: `2px solid ${on ? z.accent : "transparent"}`, marginBottom: -1,
            color: on ? z.text : z.muted, fontWeight: on ? 800 : 600,
            fontSize: "0.8em", textTransform: "uppercase", letterSpacing: "0.05em",
            padding: "10px 12px", fontFamily: "inherit",
          }}>
            {t.label}
            {t.count != null && (
              <span style={{ marginLeft: 7, padding: "1px 7px", borderRadius: 10, fontSize: "0.9em",
                background: z.line, color: z.text }}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ── Choice: one option in a toggle group (tour switch, group picker) ─────
   Selected = raised surface + text color, never the accent fill. */
export function choice(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", fontFamily: "inherit", fontWeight: on ? 800 : 600, fontSize: "0.8em",
    textTransform: "uppercase", letterSpacing: "0.05em", padding: "8px 14px", borderRadius: 4,
    color: on ? "var(--bc-text)" : "var(--bc-muted)",
    background: on ? "var(--bc-raised)" : "transparent",
    border: `1px solid ${on ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
  };
}

/* ── Primary button: the screen's ONE yellow action ─────────────────────── */
export const primaryBtn: React.CSSProperties = {
  background: "var(--bc-yellow)", color: "#081f14", fontWeight: 900,
  textTransform: "uppercase", fontSize: "0.85em", letterSpacing: "0.06em",
  padding: "12px 20px", borderRadius: 4, whiteSpace: "nowrap", border: "none",
  cursor: "pointer", fontFamily: "inherit", display: "inline-block",
};

/* ── Secondary action link ("Betting board →"): text color, no accent ──── */
export const textLink: React.CSSProperties = {
  fontWeight: 700, fontSize: "0.9em", color: "var(--bc-text)", whiteSpace: "nowrap",
};

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

/* ── Section tag: small uppercase label, muted unless a color is passed ──────────────────── */
export function SectionTag({ children, color, zone = "public" }: {
  children: React.ReactNode; color?: string; zone?: Zone;
}) {
  return (
    <div style={{ fontSize: "0.72em", fontWeight: 900, textTransform: "uppercase",
                  letterSpacing: "0.12em", color: color ?? Z[zone].muted, marginBottom: 10 }}>
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
    <div className="tabular" style={{ background: z.panel, borderRadius: 8, overflow: "hidden" }}>
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
                    letterSpacing: "0.09em", color: z.muted }}>{title}</div>
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
  if (sgTrend < -0.5) return { word: "Cold",    color: "var(--negative)" };
  if (sgTrend < -0.1) return { word: "Cooling", color: "var(--negative)" };
  return { word: "Steady", color: "var(--bc-muted)" };
}

export function fitWord(fitSg: number | null | undefined): { word: string; color: string } {
  if (fitSg == null || isNaN(fitSg)) return { word: "—", color: "var(--bc-muted)" };
  if (fitSg > 0.5)  return { word: "Excellent", color: "var(--bc-green)" };
  if (fitSg > 0.15) return { word: "Good",      color: "var(--bc-green)" };
  if (fitSg > -0.15) return { word: "Average",  color: "var(--bc-muted)" };
  return { word: "Poor", color: "var(--negative)" };
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
