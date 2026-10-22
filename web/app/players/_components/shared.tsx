"use client";

/** Shared by the Players tabs: colors, formatters, card styles, Chip, AdjBar, small parsers.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React from "react";
import { MISSING, finishNumber, fmtSigned } from "@/lib/format";


export const BG       = "var(--bc-bg)";

export const CARD_BG  = "var(--bc-panel)";

export const BORDER   = "var(--bc-line)";

export const TEXT      = "var(--bc-text)";

export const MUTED     = "var(--bc-muted)";


export const GREEN     = "var(--bc-green)";


export const GOLD      = "var(--bc-yellow)";  // also H2H player B (it had a second name, "BLUE", though it is yellow)

export const RED       = "var(--negative)";


// Formatters are Jack's lib/format.ts (audit #23): one set, NaN-safe, no "-0.00".
export { MISSING, fmtMoney, fmtOdds, fmtPct } from "@/lib/format";

/** An unsigned number to `decimals` places; MISSING when not a number. */
export function fmt(n: number | null | undefined, decimals = 1): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toFixed(decimals) : MISSING;
}

/** Strokes gained: "+0.34", "-1.20", "0.00". */
export function fmtSg(v: number | null | undefined): string {
  return fmtSigned(v, 2);
}


export function sgColor(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return MUTED;
  return v >= 0 ? GREEN : RED;
}


/** A see-through tint of a theme color. `tint(GOLD, 13)` made "var(--bc-yellow)22",
 *  which isn't a color, so those backgrounds and borders never drew (audit #22). */
export function tint(color: string, pct: number): string {
  return `color-mix(in srgb, ${color} ${pct}%, transparent)`;
}

/** One look for loading, empty and error states across Players (audit #25).
 *  Errors say what didn't load and offer a retry when one is possible. */
export function Notice({ kind, children, onRetry }: {
  kind: "loading" | "empty" | "error"; children: React.ReactNode; onRetry?: () => void;
}) {
  return (
    <div role={kind === "error" ? "alert" : "status"} style={{
      padding: "14px 16px", margin: "8px 0", borderRadius: 10, fontSize: 14, lineHeight: 1.5,
      background: CARD_BG, border: `1px solid ${kind === "error" ? tint(RED, 40) : BORDER}`,
      color: kind === "error" ? TEXT : MUTED,
    }}>
      {children}
      {onRetry && (
        <button type="button" onClick={onRetry} style={{ marginLeft: 8, background: "none", border: "none",
          color: GOLD, fontWeight: 800, cursor: "pointer", font: "inherit", padding: 0, minHeight: 32 }}>
          Try again
        </button>
      )}
    </div>
  );
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


/** Color for a finish: gold for a win, green top 5, gold top 10, `rest` after.
 *  Ties count ("T5" colors like 5th); parseInt("T5") was NaN, so they never did. */
export function posColor(pos: string | null | undefined, rest: string = MUTED): string {
  const n = finishNumber(pos);
  if (n == null) return MUTED;
  if (n === 1) return GOLD;
  if (n <= 5) return GREEN;
  if (n <= 10) return GOLD;
  return rest;
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







export function toParColor(v: string | null): string {
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
