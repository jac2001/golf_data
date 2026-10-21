"use client";

/**
 * PredictionsTable.tsx
 * =====================
 * Sortable table of all players for the current tournament.
 *
 * Two React concepts used here:
 *
 * 1. useMemo — like a cached property. The sorted list only recomputes
 *    when `players`, `sortCol`, or `sortDir` actually changes.
 *    Without it, React would re-sort on every keystroke in the search box.
 *
 * 2. Controlled sort state — clicking a column header calls setSortCol().
 *    If you click the same column twice, sortDir flips between "asc"/"desc".
 */

import React, { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { PlayerPrediction, PlayerIntel, GolferForm } from "@/lib/api";
import { nameKey } from "@/lib/names";
import { whyLine } from "@/lib/whyLine";
import { considerHref } from "@/lib/consider";
import Term from "@/components/Term";
import { COLUMN_HELP } from "@/lib/columnHelp";
import styles from "./PredictionsTable.module.css";

type Props = {
  players: PlayerPrediction[];
  intel?: PlayerIntel[];
  myPicks?: string[];  // confirmed pick names in "First Last" format
  /** Real recent results per golfer (/api/golfer-form): feeds the plain
   *  "why" line shown above the model's reasons. Omit for none. */
  form?: GolferForm[];
  /** Signed in, this event open for picks: each row's detail carries a
   *  "Consider for my picks" link to the pick screen (lib/consider.ts). */
  considerTid?: string | null;
};

type SortCol = "world_rank" | "win_prob_sim" | "win_prob" | "top10_prob_sim" | "top10_prob" | "cut_prob" | "season_sg_total" | "form_trend" | "model_vs_vegas_edge";

// Every column that can be shown/hidden, sortable or not (DataGolf-style
// "add columns" picker). `default: true` = visible out of the box; the rest
// are opt-in, since the unfiltered table was too dense to scan at a glance.
type ColKey = "win" | "top10" | "cut" | "owgr" | "sg" | "form" | "edge" | "odds" | "move";

// Maps each sortable column to a label, sort direction, and the ColKey that
// controls its visibility in the picker.
const COLS: { key: SortCol; label: string; higherBetter: boolean; toggleKey: ColKey }[] = [
  { key: "win_prob_sim",       label: "Win chance",     higherBetter: true,  toggleKey: "win"   },
  { key: "top10_prob_sim",     label: "Top-10 chance",  higherBetter: true,  toggleKey: "top10" },
  { key: "cut_prob",           label: "Makes cut",     higherBetter: true,  toggleKey: "cut"   },
  { key: "world_rank",         label: "World rank",     higherBetter: false, toggleKey: "owgr"  },
  { key: "season_sg_total",    label: "Strokes gained", higherBetter: true,  toggleKey: "sg"    },
  { key: "form_trend",         label: "Form",     higherBetter: true,  toggleKey: "form"  },
  { key: "model_vs_vegas_edge",label: "Our edge",     higherBetter: true,  toggleKey: "edge"  },
];
// Does this week's data have anything for a column? Columns with nothing
// (Move until an event has an opening line) leave the picker instead of
// showing a column of dashes, and come back on their own when it does.
// Odds and Move are DataGolf's (api _dg_odds_for); EV was dropped Oct 21.
const VALUE_OF: Record<ColKey, (p: PlayerPrediction) => unknown> = {
  win: p => p.win_prob_sim ?? p.win_prob, top10: p => p.top10_prob_sim ?? p.top10_prob,
  cut: p => p.cut_prob, owgr: p => p.world_rank, sg: p => p.season_sg_total, form: p => p.form_trend,
  edge: p => p.model_vs_vegas_edge, odds: p => p.odds_to_win, move: p => p.dk_odds_direction || null,
};

const TOGGLE_COLS: { key: ColKey; label: string; default: boolean }[] = [
  { key: "win",   label: "Win chance",     default: true  },
  { key: "top10", label: "Top-10 chance",  default: true  },
  { key: "odds",  label: "Odds",     default: true  },
  { key: "cut",   label: "Makes cut",     default: true  },
  { key: "owgr",  label: "World rank",     default: false },
  { key: "sg",    label: "Strokes gained", default: false },
  { key: "form",  label: "Form",     default: false },
  { key: "edge",  label: "Our edge",     default: false },
  { key: "move",  label: "Move",     default: false },
];
const DEFAULT_VISIBLE_COLS: ColKey[] = TOGGLE_COLS.filter(c => c.default).map(c => c.key);
const ALL_COL_KEYS = new Set<string>(TOGGLE_COLS.map(c => c.key));
const COLS_STORAGE_KEY = "fieldTableVisibleCols";

function loadVisibleCols(): Set<ColKey> {
  if (typeof window === "undefined") return new Set(DEFAULT_VISIBLE_COLS);
  try {
    const raw = window.localStorage.getItem(COLS_STORAGE_KEY);
    if (!raw) return new Set(DEFAULT_VISIBLE_COLS);
    const parsed = JSON.parse(raw);
    // Validate shape before trusting it — a corrupt/outdated value should
    // fall back to defaults quietly, not render a table with zero columns.
    if (!Array.isArray(parsed) || parsed.length === 0) return new Set(DEFAULT_VISIBLE_COLS);
    const valid = parsed.filter((k): k is ColKey => typeof k === "string" && ALL_COL_KEYS.has(k));
    return valid.length ? new Set(valid) : new Set(DEFAULT_VISIBLE_COLS);
  } catch {
    return new Set(DEFAULT_VISIBLE_COLS);
  }
}

const DRIFT_ARROW: Record<string, string> = {
  UP: "▲", DOWN: "▼", CONSTANT: "→",
};

const SENTIMENT_DOT: Record<string, string> = {
  positive: "var(--bc-green)",
  neutral:  "var(--bc-muted)",
  negative: "var(--bc-red)",
};

function normName(n: string) {
  // Normalize "Last, First" or "First Last" → sorted lowercase tokens for matching
  return n.toLowerCase().replace(",", "").split(/\s+/).sort().join(" ");
}

export default function PredictionsTable({ players, intel = [], myPicks = [], form = [], considerTid = null }: Props) {
  // One true sentence per golfer from his results + the model's chances
  // (Jack's whyLine). The model's own reasons (p.explanation) stay below it:
  // the fact is for anyone, the reasons are for golf fans.
  const whyByName = useMemo(() => {
    const facts = new Map(form.map(f => [nameKey(f.player_name), f]));
    const out = new Map<string, string>();
    if (!facts.size) return out;
    for (const p of players) {
      const f = facts.get(nameKey(p.player_name));
      try {
        out.set(p.player_name, whyLine({
          recent: f?.recent ?? [], courseStarts: f?.event_starts ?? 0, courseCuts: f?.event_cuts ?? 0,
          // The chance the Win column shows (simulation first), so the line and the column agree.
          winProb: p.win_prob_sim ?? p.win_prob ?? null, top10Prob: p.top10_prob_sim ?? p.top10_prob ?? null,
          worldRank: p.world_rank ?? null,
        }));
      } catch { /* no line beats a wrong one */ }
    }
    return out;
  }, [form, players]);
  const myPicksNorm = useMemo(() => new Set(myPicks.map(normName)), [myPicks]);
  // Build a lowercase name → intel lookup so we can match "First Last" from either source
  const intelMap = useMemo(() => {
    const m = new Map<string, PlayerIntel>();
    for (const p of intel) m.set(p.player_name.toLowerCase(), p);
    return m;
  }, [intel]);
  const [sortCol, setSortCol]   = useState<SortCol>("win_prob_sim");
  const [sortDir, setSortDir]   = useState<"asc" | "desc">("desc");
  const [search, setSearch]     = useState("");
  const [openRow, setOpenRow]   = useState<string | null>(null);

  // Column visibility — defaults are read once on first render; localStorage
  // is only touched client-side (loadVisibleCols guards on `typeof window`),
  // so this is safe under SSR/hydration.
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(() => loadVisibleCols());
  const [pickerOpen, setPickerOpen]   = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLS_STORAGE_KEY, JSON.stringify([...visibleCols]));
    } catch {
      // localStorage unavailable (private browsing, quota, etc.) — the
      // picker still works for this session, it just won't persist.
    }
  }, [visibleCols]);

  function toggleCol(key: ColKey) {
    setVisibleCols(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      // Never allow zero columns — that would render a table with just
      // the # and Player columns and no obvious way back without knowing
      // to reopen the picker on an apparently-empty table.
      return next.size === 0 ? prev : next;
    });
  }

  // Handle column header click — flip direction if same col, reset to desc if new col
  function handleSort(col: SortCol) {
    if (col === sortCol) {
      setSortDir(d => d === "desc" ? "asc" : "desc");
    } else {
      setSortCol(col);
      setSortDir(col === "world_rank" ? "asc" : "desc");
    }
  }

  // useMemo: only re-sort when these three values change
  const sorted = useMemo(() => {
    let list = [...players];

    // Filter by search
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(p => p.player_name.toLowerCase().includes(q));
    }

    // Sort
    list.sort((a, b) => {
      const av = a[sortCol] ?? (sortDir === "desc" ? -Infinity : Infinity);
      const bv = b[sortCol] ?? (sortDir === "desc" ? -Infinity : Infinity);
      return sortDir === "desc" ? (bv as number) - (av as number) : (av as number) - (bv as number);
    });

    return list;
  }, [players, sortCol, sortDir, search]);

  /** The tap-to-open detail for one golfer: same in the table row and the phone card. */
  const detailOf = (p: PlayerPrediction, playerIntel: PlayerIntel | undefined) => (
    <>
        {considerTid && (
          <Link href={considerHref(p.player_name, considerTid)} onClick={e => e.stopPropagation()}
            style={{ display: "inline-flex", alignItems: "center", minHeight: 44, marginBottom: 4,
              color: "var(--bc-yellow)", fontWeight: 800, textDecoration: "none",
              fontSize: "max(var(--fs-min), 0.85em)" }}>
            Consider {p.player_name} for my picks →
          </Link>
        )}
        {playerIntel?.injury_flag && playerIntel?.injury_detail && (
          <div style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.82em)", marginBottom: 6 }}>
            <strong>Injury:</strong> {playerIntel.injury_detail}
          </div>
        )}
        {playerIntel?.recent_form_summary && (
          <div style={{ color: "var(--bc-text)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.5, maxWidth: 760 }}>
            {playerIntel.recent_form_summary}
          </div>
        )}
        {!!playerIntel?.last_3_results?.length && (
          <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 6 }}>
            Last 3: {playerIntel.last_3_results.slice(0, 3).join(" · ")}
          </div>
        )}
    </>
  );

  const available = useMemo(() => new Set(TOGGLE_COLS.map(c => c.key)
    .filter(k => players.some(p => { const v = VALUE_OF[k](p); return v != null && v !== ""; }))), [players]);
  const shownCols = useMemo(() => new Set([...visibleCols].filter(k => available.has(k))), [visibleCols, available]);

  const th: React.CSSProperties = {
    padding: "7px 10px", borderBottom: "1px solid var(--bc-line)",
    fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700, color: "var(--bc-muted)",
    textTransform: "uppercase", letterSpacing: "0.05em",
    background: "var(--bc-panel)", whiteSpace: "nowrap", cursor: "pointer",
    userSelect: "none",
  };

  const thActive: React.CSSProperties = { ...th, color: "var(--bc-green)" };

  return (
    <div>
      {/* Search + column picker */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: "8px 12px", flexWrap: "wrap", position: "relative" }}>
        <input
          placeholder="Search player…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6,
            color: "var(--bc-text)", padding: "7px 12px", fontSize: "max(var(--fs-min), 0.85em)",
            outline: "none", width: 200,
          }}
        />
        <button
          onClick={() => setPickerOpen(o => !o)}
          style={{
            background: pickerOpen ? "var(--bc-card)" : "var(--bc-panel)",
            border: `1px solid ${pickerOpen ? "color-mix(in srgb, var(--bc-green) 27%, transparent)" : "var(--bc-line)"}`,
            borderRadius: 6, color: pickerOpen ? "var(--bc-green)" : "var(--bc-muted)",
            padding: "6px 12px", fontSize: "max(var(--fs-min), 0.8em)", fontWeight: 600, cursor: "pointer",
          }}
        >
          + Columns
        </button>
        <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)", flex: "1 1 260px" }}>
          {sorted.length} players<span className={styles.desktopOnly}> · click column to sort</span>
          {players.some(p => p.win_prob_sim != null && p.win_prob != null) &&
            " · chances come from 10,000 simulated tournaments; “base model” is the machine-learning model's direct estimate — both pre-tournament"}
        </span>

        {pickerOpen && (
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 20,
            background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 8,
            padding: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px",
          }}>
            {TOGGLE_COLS.filter(c => available.has(c.key)).map(c => (
              <label key={c.key} style={{
                display: "flex", alignItems: "center", gap: 6,
                fontSize: "max(var(--fs-min), 0.8em)", color: "var(--bc-text)", cursor: "pointer",
                padding: "3px 4px", whiteSpace: "nowrap",
              }}>
                <input
                  type="checkbox"
                  checked={visibleCols.has(c.key)}
                  onChange={() => toggleCol(c.key)}
                  style={{ accentColor: "var(--bc-green)", cursor: "pointer" }}
                />
                <Term help={COLUMN_HELP[c.key]}>{c.label}</Term>
              </label>
            ))}
          </div>
        )}
      </div>

      {sorted.length === 0 && search.trim() ? (
        <div style={{ padding: "20px 16px", background: "var(--bc-panel)", border: "1px solid var(--bc-line)",
          borderRadius: 10, color: "var(--bc-text)" }}>
          No golfers match &ldquo;{search.trim()}&rdquo;.{" "}
          <button type="button" onClick={() => setSearch("")} style={{ background: "none", border: "none",
            color: "var(--bc-yellow)", fontWeight: 800, cursor: "pointer", font: "inherit", minHeight: 44, padding: 0 }}>
            Clear search
          </button>
        </div>
      ) : <>
      <div className={styles.cards}>
        {sorted.map((p, i) => {
          const playerIntel = intelMap.get(p.player_name.toLowerCase());
          const isPick = myPicksNorm.has(normName(p.player_name));
          const isOpen = openRow === p.player_name;
          return (
            <div key={p.player_name} className={`${styles.card} ${isPick ? styles.pick : ""}`}
              onClick={() => setOpenRow(isOpen ? null : p.player_name)}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                <span style={{ color: "var(--bc-muted)", fontSize: 12, width: 22 }}>{i + 1}</span>
                <Link href={`/players?player=${encodeURIComponent(p.player_name)}`} onClick={e => e.stopPropagation()}
                  style={{ color: isPick ? "var(--bc-green)" : "var(--bc-text)", fontWeight: 700, textDecoration: "none",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.player_name}
                </Link>
                {isPick && <span style={badge("var(--bc-green)")}>My pick</span>}
                {playerIntel?.injury_flag && <span style={badge("var(--bc-red-text)")}>Injury</span>}
                <span style={{ marginLeft: "auto", color: "var(--bc-muted)", fontSize: 12 }}>{isOpen ? "Less ▾" : "More ▸"}</span>
              </div>
              <div className={styles.chips}>
                {CARD_ORDER.filter(k => shownCols.has(k)).map(k => {
                  const c = chipOf(k, p);
                  return (
                    <span key={k} className={styles.chip}>
                      <span className={styles.chipLabel}>{CHIP_LABEL[k]}</span>
                      <span className={styles.chipValue} style={{ color: c.color }}>{c.text}</span>
                    </span>
                  );
                })}
              </div>
              {whyByName.get(p.player_name) && (
                <div style={{ color: "var(--bc-text)", fontSize: 13, marginTop: 6 }}>{whyByName.get(p.player_name)}</div>
              )}
              {isOpen && <div style={{ marginTop: 8 }}>{detailOf(p, playerIntel)}</div>}
            </div>
          );
        })}
      </div>
      <div className={styles.table} style={{ overflowX: "auto", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "center", width: 36 }}>#</th>
              <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
              {COLS.filter(c => shownCols.has(c.toggleKey)).map(c => (
                <th
                  key={c.key}
                  style={sortCol === c.key ? { ...thActive, textAlign: "center" } : { ...th, textAlign: "center" }}
                  onClick={() => handleSort(c.key)}
                >
                  <Term help={COLUMN_HELP[c.toggleKey]}>{c.label}</Term>
                  {sortCol === c.key && (
                    <span style={{ marginLeft: 4 }}>{sortDir === "desc" ? "↓" : "↑"}</span>
                  )}
                </th>
              ))}
              {shownCols.has("odds") && <th style={{ ...th, textAlign: "center" }}><Term help={COLUMN_HELP.odds}>Odds</Term></th>}
              {shownCols.has("move") && <th style={{ ...th, textAlign: "center" }}><Term help={COLUMN_HELP.move}>Move</Term></th>}
              
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => { // eslint-disable-line
              const bg = i % 2 === 0 ? "var(--bc-panel)" : "var(--bc-panel)";
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid var(--bc-card)", background: bg,
              };

              const formVal  = p.form_trend ?? 0;
              const formColor = formVal > 0.3 ? "var(--bc-green)" : formVal > 0 ? "var(--bc-muted)" : "var(--bc-red)";
              const formStr   = formVal > 0 ? `+${formVal.toFixed(2)}` : formVal.toFixed(2);

              // The API sends a fraction (0.037); shown in percentage points (+3.7pp).
              const edgeVal   = p.model_vs_vegas_edge == null ? null : p.model_vs_vegas_edge * 100;
              const edgeColor = edgeVal == null ? "var(--bc-muted)" : edgeVal > 3 ? "var(--bc-green)" : edgeVal > 0 ? "var(--bc-orange)" : "var(--bc-muted)";

              const drift    = String(p.dk_odds_direction ?? "");
              const driftColor = drift === "UP" ? "var(--bc-red)" : drift === "DOWN" ? "var(--bc-green)" : "var(--bc-muted)";

              // Format odds: large numbers stay as-is with + prefix
              const odds = p.odds_to_win;
              const oddsStr = odds == null ? "—" : odds >= 0 ? `+${Math.round(odds)}` : String(Math.round(odds));

              const playerIntel = intelMap.get(p.player_name.toLowerCase());
              const isPick = myPicksNorm.has(normName(p.player_name));
              const hasMore = !!(considerTid || playerIntel?.recent_form_summary || playerIntel?.last_3_results?.length
                || (playerIntel?.injury_flag && playerIntel?.injury_detail));
              const isOpen = openRow === p.player_name;
              return (
                <React.Fragment key={p.player_name ?? `row-${i}`}>
                <tr onClick={hasMore ? () => setOpenRow(isOpen ? null : p.player_name) : undefined}
                  style={{ cursor: hasMore ? "pointer" : undefined,
                    ...(isPick ? { background: "#0a1e12", borderLeft: "2px solid var(--bc-green)" } : {}) }}>
                  <td style={{ ...td, color: "var(--bc-muted)", textAlign: "center", fontSize: "max(var(--fs-min), 0.78em)" }}>{i + 1}</td>

                  {/* Player name + intel */}
                  <td style={{ ...td, fontSize: "max(var(--fs-min), 0.85em)", maxWidth: 280 }}>
                    {/* One compact line + one line of reason; the write-up, injury
                        note and recent finishes open in a detail row on tap, so
                        every row stays the same height (2026-10-07). */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                      <Link
                        href={`/players?player=${encodeURIComponent(p.player_name)}`}
                        onClick={e => e.stopPropagation()}
                        style={{ color: isPick ? "var(--bc-green)" : "var(--bc-text)", fontWeight: isPick ? 700 : 600, whiteSpace: "nowrap", textDecoration: "none" }}
                      >
                        {p.player_name}
                      </Link>
                      {isPick && <span style={badge("var(--bc-green)")}>My pick</span>}
                      {playerIntel?.injury_flag && <span title={playerIntel.injury_detail || "injury risk"} style={badge("var(--bc-red-text)")}>Injury</span>}
                      {playerIntel?.trend === "trending_up" && <span style={badge("var(--bc-green)")}>↑ hot</span>}
                      {playerIntel?.trend === "trending_down" && <span style={badge("var(--bc-orange)")}>↓ cold</span>}
                      {hasMore && (
                        <span style={{ marginLeft: "auto", color: "var(--bc-muted)", fontSize: "max(var(--fs-min-xs), 0.72em)", whiteSpace: "nowrap" }}>
                          {isOpen ? "Less ▾" : "More ▸"}
                        </span>
                      )}
                    </div>
                    {whyByName.get(p.player_name) && (
                      <div style={{ color: "var(--bc-text)", fontSize: "max(var(--fs-min), 0.75em)", marginTop: 2,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {whyByName.get(p.player_name)}
                      </div>
                    )}
                    {p.explanation && (
                      <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)", marginTop: 2,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {p.explanation}
                      </div>
                    )}
                  </td>

                  {/* Win% — sim primary, xgb subscript */}
                  {shownCols.has("win") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.win_prob_sim != null ? (
                      <div>
                        <span style={{ color: "var(--bc-green)", fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                          {(p.win_prob_sim * 100).toFixed(1)}%
                        </span>
                        {p.win_prob != null && (
                          <div style={{ color: "#2a5040", fontSize: "max(var(--fs-min-xs), 0.68em)", marginTop: 1 }}>
                            base model {(p.win_prob * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: "var(--bc-green)", fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                        {p.win_prob != null ? `${(p.win_prob * 100).toFixed(1)}%` : "—"}
                      </span>
                    )}
                  </td>
                  )}

                  {/* Top 10% — sim primary, xgb subscript */}
                  {shownCols.has("top10") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.top10_prob_sim != null ? (
                      <div>
                        <span style={{ color: "var(--bc-yellow)", fontWeight: 600, fontSize: "max(var(--fs-min), 0.85em)" }}>
                          {(p.top10_prob_sim * 100).toFixed(1)}%
                        </span>
                        {p.top10_prob != null && (
                          <div style={{ color: "var(--bc-card)", fontSize: "max(var(--fs-min-xs), 0.68em)", marginTop: 1 }}>
                            base model {(p.top10_prob * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: "var(--bc-yellow)", fontSize: "max(var(--fs-min), 0.85em)", fontWeight: 600 }}>
                        {p.top10_prob != null ? `${(p.top10_prob * 100).toFixed(1)}%` : "—"}
                      </span>
                    )}
                  </td>
                  )}

                  {/* Cut% */}
                  {shownCols.has("cut") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.cut_prob != null ? `${(p.cut_prob * 100).toFixed(0)}%` : "—"}
                  </td>
                  )}

                  {/* OWGR */}
                  {shownCols.has("owgr") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {p.world_rank ?? "—"}
                  </td>
                  )}

                  {/* SG Total */}
                  {shownCols.has("sg") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {p.season_sg_total != null ? (p.season_sg_total > 0 ? `+${p.season_sg_total.toFixed(2)}` : p.season_sg_total.toFixed(2)) : "—"}
                  </td>
                  )}

                  {/* Form */}
                  {shownCols.has("form") && (
                  <td style={{ ...td, textAlign: "center", color: formColor, fontWeight: 600, fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {formStr}
                  </td>
                  )}

                  {/* Edge vs Vegas */}
                  {shownCols.has("edge") && (
                  <td style={{ ...td, textAlign: "center", color: edgeColor, fontWeight: edgeVal && edgeVal > 3 ? 700 : 400, fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {edgeVal != null ? `${edgeVal > 0 ? "+" : ""}${edgeVal.toFixed(1)}pp` : "—"}
                  </td>
                  )}

                  {/* Odds */}
                  {shownCols.has("odds") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {oddsStr}
                  </td>
                  )}

                  {/* Drift */}
                  {shownCols.has("move") && (
                  <td style={{ ...td, textAlign: "center", color: driftColor, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {DRIFT_ARROW[drift] ?? "—"}
                  </td>
                  )}


                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={2 + shownCols.size} style={{ ...td, background: "var(--bc-panel)", padding: "10px 14px 12px 46px" }}>
                      {detailOf(p, playerIntel)}
                    </td>
                  </tr>
                )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      </>}
    </div>
  );
}

// Phone cards: one chip per column the member has chosen, in table order.
const CARD_ORDER: ColKey[] = ["win", "top10", "cut", "owgr", "sg", "form", "edge", "odds", "move"];
const CHIP_LABEL: Record<ColKey, string> = { win: "Win", top10: "Top 10", cut: "Makes cut", owgr: "World rank",
  sg: "SG", form: "Form", edge: "Our edge", odds: "Odds", move: "Move" };

function chipOf(k: ColKey, p: PlayerPrediction): { text: string; color?: string } {
  const pct = (v: number | null | undefined, dp = 1) => v == null ? "—" : `${(v * 100).toFixed(dp)}%`;
  const signed = (v: number | null | undefined, dp = 2, unit = "") => v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(dp)}${unit}`;
  switch (k) {
    case "win":   return { text: pct(p.win_prob_sim ?? p.win_prob), color: "var(--bc-green)" };
    case "top10": return { text: pct(p.top10_prob_sim ?? p.top10_prob), color: "var(--bc-yellow)" };
    case "cut":   return { text: pct(p.cut_prob, 0) };
    case "owgr":  return { text: p.world_rank != null ? `#${Math.round(p.world_rank)}` : "—" };
    case "sg":    return { text: signed(p.season_sg_total) };
    case "form":  return { text: signed(p.form_trend),
                           color: (p.form_trend ?? 0) > 0.3 ? "var(--bc-green)" : (p.form_trend ?? 0) < 0 ? "var(--bc-red)" : undefined };
    case "edge":  return { text: signed(p.model_vs_vegas_edge == null ? null : p.model_vs_vegas_edge * 100, 1, "pp"),
                           color: (p.model_vs_vegas_edge ?? 0) * 100 > 3 ? "var(--bc-green)" : undefined };
    case "odds":  return { text: p.odds_to_win == null ? "—" : p.odds_to_win >= 0 ? `+${Math.round(p.odds_to_win)}` : String(Math.round(p.odds_to_win)) };
    case "move":  return { text: String(p.dk_odds_direction ?? "") === "UP" ? "↑" : String(p.dk_odds_direction ?? "") === "DOWN" ? "↓" : "—" };
  }
}

/** Small outlined badge next to a player name (My pick / Injury / hot / cold). */
function badge(color: string): React.CSSProperties {
  return {
    fontSize: "max(var(--fs-min-xs), 0.66em)", fontWeight: 800, color, whiteSpace: "nowrap", flexShrink: 0,
    border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`, borderRadius: 3, padding: "0 5px",
    textTransform: "uppercase", letterSpacing: "0.03em",
  };
}
