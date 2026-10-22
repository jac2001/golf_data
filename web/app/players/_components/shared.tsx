"use client";

/** Shared by the Players tabs: colors, formatters, card styles, Chip, AdjBar, small parsers.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React from "react";


export const BG       = "var(--bc-bg)";

export const CARD_BG  = "var(--bc-panel)";

export const BORDER   = "var(--bc-line)";

export const TEXT      = "var(--bc-text)";

export const MUTED     = "var(--bc-muted)";


export const GREEN     = "var(--bc-green)";


export const GOLD      = "var(--bc-yellow)";  // also H2H player B (it had a second name, "BLUE", though it is yellow)

export const RED       = "var(--negative)";


export function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}


export function fmtPct(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(decimals)}%`;
}


/** Real prize money from results: "$1,440,000"; "—" when missing. */
export function fmtMoney(v: number | string | null | undefined): string {
  const n = typeof v === "string" ? Number(v.replace(/[$,]/g, "")) : v;
  return n != null && Number.isFinite(n) ? `$${Math.round(n).toLocaleString()}` : "—";
}


export function fmtOdds(n: number | null | undefined): string {
  if (n == null) return "—";
  return n >= 0 ? `+${Math.round(n)}` : String(Math.round(n));
}


export function sgColor(v: number | null): string {
  if (v == null) return MUTED;
  return v >= 0 ? GREEN : RED;
}


export const sectionLabel: React.CSSProperties = {
  fontSize: "max(var(--fs-min-xs), 0.68em)",
  fontWeight: 700,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: MUTED,
  marginBottom: 10,
};


export const card: React.CSSProperties = {
  background: CARD_BG,
  border: `1px solid ${BORDER}`,
  borderRadius: 10,
  padding: "16px 20px",
  marginBottom: 16,
};


// ── Stat chip ────────────────────────────────────────────────────────────────

export function Chip({ label, value, color = TEXT }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      background: "var(--bc-panel)", border: `1px solid ${BORDER}`, borderRadius: 8,
      padding: "10px 16px", minWidth: 80,
    }}>
      <span style={{ fontSize: "1.15em", fontWeight: 700, color }}>{value}</span>
      <span style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: MUTED, marginTop: 2 }}>{label}</span>
    </div>
  );
}


// ── Adjustment bar ────────────────────────────────────────────────────────────

export function AdjBar({ label, value, maxAbs }: { label: string; value: number | null; maxAbs: number }) {
  const pct = value == null || maxAbs === 0 ? 0 : Math.abs(value) / maxAbs * 100;
  const positive = (value ?? 0) >= 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
      <span style={{ width: 160, fontSize: "max(var(--fs-min), 0.78em)", color: MUTED, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
        {/* left half */}
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
          {!positive && value != null && (
            <div style={{
              width: `${pct}%`, height: 8, borderRadius: 2,
              background: RED, maxWidth: "100%",
            }} />
          )}
        </div>
        {/* center line */}
        <div style={{ width: 1, height: 14, background: BORDER, flexShrink: 0 }} />
        {/* right half */}
        <div style={{ flex: 1 }}>
          {positive && value != null && (
            <div style={{
              width: `${pct}%`, height: 8, borderRadius: 2,
              background: GREEN, maxWidth: "100%",
            }} />
          )}
        </div>
      </div>
      <span style={{
        width: 44, fontSize: "max(var(--fs-min), 0.78em)", textAlign: "right", flexShrink: 0,
        color: value == null ? MUTED : (positive ? GREEN : RED),
        fontVariantNumeric: "tabular-nums",
      }}>
        {value == null ? "—" : `${positive ? "+" : ""}${value.toFixed(2)}`}
      </span>
    </div>
  );
}



// ── Course history parser ─────────────────────────────────────────────────────

type CourseResult = { tournament: string; year: number; position: string; to_par: string };

type CourseHistory = { course_name: string; tournaments: CourseResult[] };


export function parseCourseHistory(raw: string | null): CourseHistory[] {
  if (!raw || raw === "nan" || raw === "None") return [];
  try {
    return JSON.parse(raw) as CourseHistory[];
  } catch {
    return [];
  }
}


export function posColor(pos: string): string {
  const n = parseInt(pos, 10);
  if (isNaN(n)) return MUTED;
  if (n === 1) return GOLD;
  if (n <= 5) return GREEN;
  if (n <= 10) return GOLD;
  return MUTED;
}


export function normName(n: string): string {
  return n.toLowerCase().split(/[\s,]+/).filter(Boolean).sort().join(" ");
}


export function rankColor(rank: number | null): string {
  if (rank == null) return MUTED;
  if (rank <= 5)  return GREEN;
  if (rank <= 15) return GOLD;
  if (rank <= 30) return TEXT;
  return MUTED;
}


// ── Career card ───────────────────────────────────────────────────────────────

export function posColor2(pos: string): string {
  const n = parseInt(pos, 10);
  if (isNaN(n)) return MUTED;
  if (n === 1) return GOLD;
  if (n <= 5)  return GREEN;
  if (n <= 10) return GOLD;
  return TEXT;
}


export function sgColor2(v: number | null): string {
  if (v == null) return MUTED;
  return v >= 0 ? GREEN : RED;
}


export function fmtSg(v: number | null): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}


export function toParColor2(v: string | null): string {
  if (!v) return MUTED;
  if (v.startsWith("-")) return GREEN;
  if (v === "0" || v === "E") return MUTED;
  return RED;
}


const MAJOR_KEYWORDS = ["masters", "u.s. open", "us open", "open championship", "pga championship"];

export function isMajor(name: string): boolean {
  const n = name.toLowerCase();
  return MAJOR_KEYWORDS.some(k => n.includes(k));
}


// ── Betting profile card ──────────────────────────────────────────────────────

type RecentResult = { tournament: string; course?: string; finish: string; year: number; to_par: string; winnings?: string };


export function parseRecentResults(raw: string | null): RecentResult[] {
  if (!raw || raw === "nan" || raw === "None") return [];
  try { return JSON.parse(raw) as RecentResult[]; } catch { return []; }
}
