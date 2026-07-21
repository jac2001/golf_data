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

import { useState, useMemo, useEffect } from "react";
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
type ColKey = "win" | "top10" | "cut" | "owgr" | "sg" | "form" | "edge" | "odds" | "move" | "ev" | "uses" | "pick";

// Maps each sortable column to a label, sort direction, and the ColKey that
// controls its visibility in the picker.
const COLS: { key: SortCol; label: string; higherBetter: boolean; toggleKey: ColKey }[] = [
  { key: "win_prob_sim",       label: "Win%",     higherBetter: true,  toggleKey: "win"   },
  { key: "top10_prob_sim",     label: "Top 10%",  higherBetter: true,  toggleKey: "top10" },
  { key: "cut_prob",           label: "Cut%",     higherBetter: true,  toggleKey: "cut"   },
  { key: "world_rank",         label: "OWGR",     higherBetter: false, toggleKey: "owgr"  },
  { key: "season_sg_total",    label: "SG Total", higherBetter: true,  toggleKey: "sg"    },
  { key: "form_trend",         label: "Form",     higherBetter: true,  toggleKey: "form"  },
  { key: "model_vs_vegas_edge",label: "Edge",     higherBetter: true,  toggleKey: "edge"  },
];
const TOGGLE_COLS: { key: ColKey; label: string; default: boolean }[] = [
  { key: "win",   label: "Win%",     default: true  },
  { key: "top10", label: "Top 10%",  default: true  },
  { key: "odds",  label: "Odds",     default: true  },
  { key: "uses",  label: "Uses",     default: true  },
  { key: "pick",  label: "Pick",     default: true  },
  { key: "cut",   label: "Cut%",     default: false },
  { key: "owgr",  label: "OWGR",     default: false },
  { key: "sg",    label: "SG Total", default: false },
  { key: "form",  label: "Form",     default: false },
  { key: "edge",  label: "Edge",     default: false },
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
  positive: "#00c44f",
  neutral:  "#4a6080",
  negative: "#e74c3c",
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
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    fontSize: "0.68em", fontWeight: 700, color: "#5a7090",
    textTransform: "uppercase", letterSpacing: "0.05em",
    background: "#0a1628", whiteSpace: "nowrap", cursor: "pointer",
    userSelect: "none",
  };

  const thActive: React.CSSProperties = { ...th, color: "#00c44f" };

  return (
    <div>
      {/* Search + column picker */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12, position: "relative" }}>
        <input
          placeholder="Search player…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            background: "#0a1525", border: "1px solid #1e3a5f", borderRadius: 6,
            color: "#dde6f5", padding: "7px 12px", fontSize: "0.85em",
            outline: "none", width: 200,
          }}
        />
        <button
          onClick={() => setPickerOpen(o => !o)}
          style={{
            background: pickerOpen ? "#0d2e18" : "#0a1525",
            border: `1px solid ${pickerOpen ? "#00c44f44" : "#1e3a5f"}`,
            borderRadius: 6, color: pickerOpen ? "#00c44f" : "#7a9ab8",
            padding: "6px 12px", fontSize: "0.8em", fontWeight: 600, cursor: "pointer",
          }}
        >
          + Columns
        </button>
        <span style={{ color: "#4a6080", fontSize: "0.75em" }}>
          {sorted.length} players · click column to sort
        </span>

        {pickerOpen && (
          <div style={{
            position: "absolute", top: "calc(100% + 6px)", left: 212, zIndex: 20,
            background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
            padding: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px",
          }}>
            {TOGGLE_COLS.map(c => (
              <label key={c.key} style={{
                display: "flex", alignItems: "center", gap: 6,
                fontSize: "0.8em", color: "#c8d8e8", cursor: "pointer",
                padding: "3px 4px", whiteSpace: "nowrap",
              }}>
                <input
                  type="checkbox"
                  checked={visibleCols.has(c.key)}
                  onChange={() => toggleCol(c.key)}
                  style={{ accentColor: "#00c44f", cursor: "pointer" }}
                />
                {c.label}
              </label>
            ))}
          </div>
        )}
      </div>

      <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
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
              {visibleCols.has("ev")   && <th style={{ ...th, textAlign: "center", color: "#f1c40f" }}>EV</th>}
              {visibleCols.has("uses") && <th style={{ ...th, textAlign: "center" }}>Uses</th>}
              {visibleCols.has("pick") && <th style={{ ...th, textAlign: "center" }}>Pick</th>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => { // eslint-disable-line
              const isUse = p.badge === "USE";
              const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
              const td: React.CSSProperties = {
                padding: "6px 10px", borderBottom: "1px solid #0f2236", background: bg,
              };

              const formVal  = p.form_trend ?? 0;
              const formColor = formVal > 0.3 ? "#00c44f" : formVal > 0 ? "#8ba0b8" : "#e74c3c";
              const formStr   = formVal > 0 ? `+${formVal.toFixed(2)}` : formVal.toFixed(2);

              const edgeVal   = p.model_vs_vegas_edge;
              const edgeColor = edgeVal == null ? "#4a6080" : edgeVal > 3 ? "#00c44f" : edgeVal > 0 ? "#f39c12" : "#4a6080";

              const drift    = String(p.dk_odds_direction ?? "");
              const driftColor = drift === "UP" ? "#e74c3c" : drift === "DOWN" ? "#00c44f" : "#4a6080";

              // Format odds: large numbers stay as-is with + prefix
              const odds = p.odds_to_win;
              const oddsStr = odds == null ? "—" : odds >= 0 ? `+${Math.round(odds)}` : String(Math.round(odds));

              const playerIntel = intelMap.get(p.player_name.toLowerCase());
              const isPick = myPicksNorm.has(normName(p.player_name));
              return (
                <tr key={p.player_name ?? `row-${i}`} style={isPick ? {
                  background: "#0a1e12",
                  borderLeft: "2px solid #00c44f",
                } : undefined}>
                  <td style={{ ...td, color: "#3a5060", textAlign: "center", fontSize: "0.78em" }}>{i + 1}</td>

                  {/* Player name + intel */}
                  <td style={{ ...td, fontSize: "0.85em", maxWidth: 280 }}>
                    {/* Row 1: name + badges */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      <Link
                        href={`/players?player=${encodeURIComponent(p.player_name)}`}
                        style={{ color: isPick ? "#00c44f" : "#dde6f5", fontWeight: isPick ? 700 : 600, whiteSpace: "nowrap", textDecoration: "none" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "#4cb8ff")}
                        onMouseLeave={e => (e.currentTarget.style.color = isPick ? "#00c44f" : "#dde6f5")}
                      >
                        {p.player_name}
                      </Link>
                      {isPick && (
                        <span style={{
                          fontSize: "0.6em", fontWeight: 800, color: "#00c44f",
                          background: "#0d2e18", border: "1px solid #00c44f44",
                          borderRadius: 3, padding: "1px 5px", whiteSpace: "nowrap",
                        }}>MY PICK</span>
                      )}
                      {playerIntel?.injury_flag && (
                        <span style={{
                          fontSize: "0.68em", fontWeight: 700, color: "#e74c3c",
                          background: "#1a0808", border: "1px solid #5f1e1e44",
                          borderRadius: 4, padding: "1px 6px", whiteSpace: "nowrap",
                        }}>
                          {playerIntel.injury_detail
                            ? playerIntel.injury_detail.length > 30
                              ? playerIntel.injury_detail.slice(0, 30) + "…"
                              : playerIntel.injury_detail
                            : "injury risk"}
                        </span>
                      )}
                      {playerIntel?.trend === "trending_up" && (
                        <span style={{
                          fontSize: "0.68em", fontWeight: 700, color: "#00c44f",
                          background: "#0d2e18", border: "1px solid #00c44f44",
                          borderRadius: 4, padding: "1px 6px",
                        }}>↑ hot</span>
                      )}
                      {playerIntel?.trend === "trending_down" && (
                        <span style={{
                          fontSize: "0.68em", fontWeight: 700, color: "#f39c12",
                          background: "#1a1200", border: "1px solid #5f4a0044",
                          borderRadius: 4, padding: "1px 6px",
                        }}>↓ cold</span>
                      )}
                    </div>

                    {/* Row 2: model explanation */}
                    {p.explanation && (
                      <div style={{ color: "#3a5a70", fontSize: "0.75em", marginTop: 3 }}>
                        {p.explanation}
                      </div>
                    )}

                    {/* Row 3: intel form summary */}
                    {playerIntel?.recent_form_summary && (
                      <div style={{ color: "#4a6a80", fontSize: "0.72em", marginTop: 3, lineHeight: 1.4 }}>
                        {playerIntel.recent_form_summary}
                      </div>
                    )}

                    {/* Row 4: last 3 results chips */}
                    {playerIntel?.last_3_results?.length && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                        {playerIntel.last_3_results.slice(0, 3).map((r, ri) => (
                          <span key={ri} style={{
                            fontSize: "0.65em", color: "#4a6080",
                            background: "#0a1520", border: "1px solid #1e3a5f",
                            borderRadius: 3, padding: "1px 5px", whiteSpace: "nowrap",
                          }}>{r}</span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Win% — sim primary, xgb subscript */}
                  {visibleCols.has("win") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.win_prob_sim != null ? (
                      <div>
                        <span style={{ color: "#00c44f", fontWeight: 700, fontSize: "0.88em" }}>
                          {(p.win_prob_sim * 100).toFixed(1)}%
                        </span>
                        {p.win_prob != null && (
                          <div style={{ color: "#2a5040", fontSize: "0.68em", marginTop: 1 }}>
                            xgb {(p.win_prob * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: "#00c44f", fontWeight: 700, fontSize: "0.88em" }}>
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
                        <span style={{ color: "#4cb8ff", fontWeight: 600, fontSize: "0.85em" }}>
                          {(p.top10_prob_sim * 100).toFixed(1)}%
                        </span>
                        {p.top10_prob != null && (
                          <div style={{ color: "#1a3050", fontSize: "0.68em", marginTop: 1 }}>
                            xgb {(p.top10_prob * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: "#4cb8ff", fontSize: "0.85em", fontWeight: 600 }}>
                        {p.top10_prob != null ? `${(p.top10_prob * 100).toFixed(1)}%` : "—"}
                      </span>
                    )}
                  </td>
                  )}

                  {/* Cut% */}
                  {visibleCols.has("cut") && (
                  <td style={{ ...td, textAlign: "center", color: "#8ba0b8", fontSize: "0.85em" }}>
                    {p.cut_prob != null ? `${(p.cut_prob * 100).toFixed(0)}%` : "—"}
                  </td>
                  )}

                  {/* OWGR */}
                  {visibleCols.has("owgr") && (
                  <td style={{ ...td, textAlign: "center", color: "#7f8c8d", fontSize: "0.82em" }}>
                    {p.world_rank ?? "—"}
                  </td>
                  )}

                  {/* SG Total */}
                  {visibleCols.has("sg") && (
                  <td style={{ ...td, textAlign: "center", color: "#8ba0b8", fontSize: "0.82em" }}>
                    {p.season_sg_total != null ? (p.season_sg_total > 0 ? `+${p.season_sg_total.toFixed(2)}` : p.season_sg_total.toFixed(2)) : "—"}
                  </td>
                  )}

                  {/* Form */}
                  {visibleCols.has("form") && (
                  <td style={{ ...td, textAlign: "center", color: formColor, fontWeight: 600, fontSize: "0.82em" }}>
                    {formStr}
                  </td>
                  )}

                  {/* Edge vs Vegas */}
                  {visibleCols.has("edge") && (
                  <td style={{ ...td, textAlign: "center", color: edgeColor, fontWeight: edgeVal && edgeVal > 3 ? 700 : 400, fontSize: "0.82em" }}>
                    {edgeVal != null ? `${edgeVal > 0 ? "+" : ""}${edgeVal.toFixed(1)}pp` : "—"}
                  </td>
                  )}

                  {/* Odds */}
                  {visibleCols.has("odds") && (
                  <td style={{ ...td, textAlign: "center", color: "#7f8c8d", fontSize: "0.82em" }}>
                    {oddsStr}
                  </td>
                  )}

                  {/* Drift */}
                  {visibleCols.has("move") && (
                  <td style={{ ...td, textAlign: "center", color: driftColor, fontWeight: 700, fontSize: "0.88em" }}>
                    {DRIFT_ARROW[drift] ?? "—"}
                  </td>
                  )}

                  {/* Season EV */}
                  {visibleCols.has("ev") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.this_week_ev != null ? (
                      <span style={{ fontSize: "0.72em", color: "#f1c40f", fontWeight: 600 }}>
                        {p.this_week_ev >= 1000
                          ? `${(p.this_week_ev / 1000).toFixed(0)}k`
                          : String(p.this_week_ev)}
                      </span>
                    ) : <span style={{ color: "#3a5060", fontSize: "0.72em" }}>—</span>}
                  </td>
                  )}

                  {/* Uses remaining — pip dots */}
                  {visibleCols.has("uses") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    <div style={{ display: "flex", gap: 3, justifyContent: "center" }}>
                      {[0,1,2].map(idx => (
                        <div key={idx} style={{
                          width: 7, height: 7, borderRadius: "50%",
                          background: idx < (p.uses_remaining ?? 3) ? "#00c44f" : "#1a3050",
                        }} />
                      ))}
                    </div>
                  </td>
                  )}

                  {/* Badge: USE / SAVE / MAXED */}
                  {visibleCols.has("pick") && (
                  <td style={{ ...td, textAlign: "center" }}>
                    {p.badge === "USE" && (
                      <span style={{ fontSize: "0.62em", fontWeight: 800, color: "#00c44f", background: "#0d2e18", padding: "2px 6px", borderRadius: 3, border: "1px solid #00c44f44" }}>USE</span>
                    )}
                    {p.badge === "SAVE" && (
                      <span style={{ fontSize: "0.62em", fontWeight: 800, color: "#f39c12", background: "#2a1f0a", padding: "2px 6px", borderRadius: 3, border: "1px solid #f39c1244" }}>SAVE</span>
                    )}
                    {p.badge === "MAXED" && (
                      <span style={{ fontSize: "0.62em", fontWeight: 800, color: "#4a6080", background: "#0a1220", padding: "2px 6px", borderRadius: 3, border: "1px solid #1e3a5f" }}>MAXED</span>
                    )}
                  </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
