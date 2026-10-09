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
import { PlayerPrediction, PlayerIntel } from "@/lib/api";

type Props = {
  players: PlayerPrediction[];
  intel?: PlayerIntel[];
  myPicks?: string[];  // confirmed pick names in "First Last" format
};

type SortCol = "world_rank" | "win_prob_sim" | "win_prob" | "top10_prob_sim" | "top10_prob" | "cut_prob" | "season_sg_total" | "form_trend" | "model_vs_vegas_edge";

// Every column that can be shown/hidden, sortable or not (DataGolf-style
// "add columns" picker). `default: true` = visible out of the box; the rest
// are opt-in, since the unfiltered table was too dense to scan at a glance.
type ColKey = "win" | "top10" | "cut" | "owgr" | "sg" | "form" | "edge" | "odds" | "move" | "ev";

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
const TOGGLE_COLS: { key: ColKey; label: string; default: boolean }[] = [
  { key: "win",   label: "Win chance",     default: true  },
  { key: "top10", label: "Top-10 chance",  default: true  },
  { key: "odds",  label: "Odds",     default: true  },
  { key: "cut",   label: "Makes cut",     default: false },
  { key: "owgr",  label: "World rank",     default: false },
  { key: "sg",    label: "Strokes gained", default: false },
  { key: "form",  label: "Form",     default: false },
  { key: "edge",  label: "Our edge",     default: false },
  { key: "move",  label: "Move",     default: false },
  { key: "ev",    label: "EV",       default: false },
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

export default function PredictionsTable({ players, intel = [], myPicks = [] }: Props) {
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
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12, position: "relative" }}>
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
        <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)" }}>
          {sorted.length} players · click column to sort
          {players.some(p => p.win_prob_sim != null && p.win_prob != null) &&
            " · chances come from 10,000 simulated tournaments; “base model” is the machine-learning model's direct estimate — both pre-tournament"}
        </span>

        {pickerOpen && (
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", left: 212, zIndex: 20,
            background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 8,
            padding: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px",
          }}>
            {TOGGLE_COLS.map(c => (
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
                {c.label}
              </label>
            ))}
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto", border: "1px solid var(--bc-line)", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "var(--bc-panel)" }}>
          <thead>
            <tr>
              <th style={{ ...th, textAlign: "center", width: 36 }}>#</th>
              <th style={{ ...th, textAlign: "left", minWidth: 160 }}>Player</th>
              {COLS.filter(c => visibleCols.has(c.toggleKey)).map(c => (
                <th
                  key={c.key}
                  style={sortCol === c.key ? { ...thActive, textAlign: "center" } : { ...th, textAlign: "center" }}
                  onClick={() => handleSort(c.key)}
                >
                  {c.label}
                  {sortCol === c.key && (
                    <span style={{ marginLeft: 4 }}>{sortDir === "desc" ? "↓" : "↑"}</span>
                  )}
                </th>
              ))}
              {visibleCols.has("odds") && <th style={{ ...th, textAlign: "center" }}>Odds</th>}
              {visibleCols.has("move") && <th style={{ ...th, textAlign: "center" }}>Move</th>}
              {visibleCols.has("ev")   && <th style={{ ...th, textAlign: "center", color: "var(--bc-yellow)" }}>EV</th>}
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

              const edgeVal   = p.model_vs_vegas_edge;
              const edgeColor = edgeVal == null ? "var(--bc-muted)" : edgeVal > 3 ? "var(--bc-green)" : edgeVal > 0 ? "var(--bc-orange)" : "var(--bc-muted)";

              const drift    = String(p.dk_odds_direction ?? "");
              const driftColor = drift === "UP" ? "var(--bc-red)" : drift === "DOWN" ? "var(--bc-green)" : "var(--bc-muted)";

              // Format odds: large numbers stay as-is with + prefix
              const odds = p.odds_to_win;
              const oddsStr = odds == null ? "—" : odds >= 0 ? `+${Math.round(odds)}` : String(Math.round(odds));

              const playerIntel = intelMap.get(p.player_name.toLowerCase());
              const isPick = myPicksNorm.has(normName(p.player_name));
              const hasMore = !!(playerIntel?.recent_form_summary || playerIntel?.last_3_results?.length
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
                    {p.explanation && (
                      <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.75em)", marginTop: 2,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {p.explanation}
                      </div>
                    )}
                  </td>

                  {/* Win% — sim primary, xgb subscript */}
                  {visibleCols.has("win") && (
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
                  {visibleCols.has("top10") && (
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
                  {visibleCols.has("cut") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {p.cut_prob != null ? `${(p.cut_prob * 100).toFixed(0)}%` : "—"}
                  </td>
                  )}

                  {/* OWGR */}
                  {visibleCols.has("owgr") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {p.world_rank ?? "—"}
                  </td>
                  )}

                  {/* SG Total */}
                  {visibleCols.has("sg") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {p.season_sg_total != null ? (p.season_sg_total > 0 ? `+${p.season_sg_total.toFixed(2)}` : p.season_sg_total.toFixed(2)) : "—"}
                  </td>
                  )}

                  {/* Form */}
                  {visibleCols.has("form") && (
                  <td style={{ ...td, textAlign: "center", color: formColor, fontWeight: 600, fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {formStr}
                  </td>
                  )}

                  {/* Edge vs Vegas */}
                  {visibleCols.has("edge") && (
                  <td style={{ ...td, textAlign: "center", color: edgeColor, fontWeight: edgeVal && edgeVal > 3 ? 700 : 400, fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {edgeVal != null ? `${edgeVal > 0 ? "+" : ""}${edgeVal.toFixed(1)}pp` : "—"}
                  </td>
                  )}

                  {/* Odds */}
                  {visibleCols.has("odds") && (
                  <td style={{ ...td, textAlign: "center", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
                    {oddsStr}
                  </td>
                  )}

                  {/* Drift */}
                  {visibleCols.has("move") && (
                  <td style={{ ...td, textAlign: "center", color: driftColor, fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)" }}>
                    {DRIFT_ARROW[drift] ?? "—"}
                  </td>
                  )}

                  {/* Season EV */}
                  {visibleCols.has("ev") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.this_week_ev != null ? (
                      <span style={{ fontSize: "max(var(--fs-min), 0.72em)", color: "var(--bc-yellow)", fontWeight: 600 }}>
                        {p.this_week_ev >= 1000
                          ? `${(p.this_week_ev / 1000).toFixed(0)}k`
                          : String(p.this_week_ev)}
                      </span>
                    ) : <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.72em)" }}>—</span>}
                  </td>
                  )}

                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={2 + visibleCols.size} style={{ ...td, background: "var(--bc-panel)", padding: "10px 14px 12px 46px" }}>
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
                    </td>
                  </tr>
                )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Small outlined badge next to a player name (My pick / Injury / hot / cold). */
function badge(color: string): React.CSSProperties {
  return {
    fontSize: "max(var(--fs-min-xs), 0.66em)", fontWeight: 800, color, whiteSpace: "nowrap", flexShrink: 0,
    border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`, borderRadius: 3, padding: "0 5px",
    textTransform: "uppercase", letterSpacing: "0.03em",
  };
}
