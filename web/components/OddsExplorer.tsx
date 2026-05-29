"use client";

import { useState, useEffect } from "react";
import { getOddsExplorer, refreshDgOdds, OddsExplorerResponse } from "@/lib/api";

const MARKET_OPTS = [
  { value: "top_10", label: "Top 10" },
  { value: "top_20", label: "Top 20" },
  { value: "top_5",  label: "Top 5" },
  { value: "win",    label: "Win" },
  { value: "make_cut", label: "Make Cut" },
];

const BOOK_ABBR: Record<string, string> = {
  Draftkings: "DK", Fanduel: "FD", Bet365: "B365", Betmgm: "MGM",
  Caesars: "CZR", Pinnacle: "PIN", Unibet: "UNI", Bovada: "BOV",
  Betonline: "BOL", Betcris: "BCR", Pointsbet: "PB",
};

export default function OddsExplorer() {
  const [market, setMarket]         = useState("top_10");
  const [data, setData]             = useState<OddsExplorerResponse | null>(null);
  const [loading, setLoading]       = useState(false);
  const [posEvOnly, setPosEvOnly]   = useState(false);
  const [search, setSearch]         = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);

  function load() {
    setLoading(true);
    getOddsExplorer(market).then(setData).finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, [market]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshErr(null);
    try {
      await refreshDgOdds();
      load();
    } catch {
      setRefreshErr("Refresh failed — check FastAPI logs.");
    } finally {
      setRefreshing(false);
    }
  }

  const players = (data?.players ?? []).filter(p => {
    if (posEvOnly && !p.has_pos_ev) return false;
    if (search.trim()) {
      return p.player.toLowerCase().includes(search.trim().toLowerCase());
    }
    return true;
  });

  const books = data?.books ?? [];
  // Cap at 8 books to keep the table readable
  const booksShown = books.slice(0, 8);

  const th: React.CSSProperties = {
    background: "#0a1628", color: "#5a7090",
    fontSize: "0.68em", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.05em",
    padding: "7px 10px", borderBottom: "1px solid #1e3a5f",
    whiteSpace: "nowrap", position: "sticky", top: 0,
  };

  return (
    <div>
      {/* Controls */}
      <div style={{
        display: "flex", gap: 12, alignItems: "center", marginBottom: 16,
        padding: "12px 14px", background: "#0d1a30",
        border: "1px solid #1e3a5f", borderRadius: 8, flexWrap: "wrap",
      }}>
        {/* Market select */}
        <div>
          <div style={{ fontSize: "0.65em", color: "#7f8c8d", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Market
          </div>
          <select
            value={market}
            onChange={e => setMarket(e.target.value)}
            style={selectStyle}
          >
            {MARKET_OPTS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Search */}
        <div>
          <div style={{ fontSize: "0.65em", color: "#7f8c8d", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Search
          </div>
          <input
            placeholder="Player name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ ...selectStyle, width: 160 }}
          />
        </div>

        {/* Pos EV filter */}
        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", color: "#8ba0b8", fontSize: "0.85em", marginTop: 18 }}>
          <input
            type="checkbox"
            checked={posEvOnly}
            onChange={e => setPosEvOnly(e.target.checked)}
            style={{ accentColor: "#00c44f" }}
          />
          Positive EV only
        </label>

        {/* Refresh + meta */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "flex-end", gap: 12 }}>
          {data?.updated && (
            <span style={{ color: "#4a6080", fontSize: "0.72em" }}>
              DG updated: {data.updated}
            </span>
          )}
          <button onClick={handleRefresh} disabled={refreshing} style={btnStyle}>
            {refreshing ? "Refreshing…" : "Refresh Odds"}
          </button>
        </div>
        {refreshErr && (
          <span style={{ color: "#e74c3c", fontSize: "0.75em", width: "100%", marginTop: 4 }}>
            {refreshErr}
          </span>
        )}
      </div>

      {/* Summary strip */}
      {data && !loading && (
        <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
          <span style={{ color: "#7f8c8d", fontSize: "0.78em" }}>
            {players.length} players
          </span>
          <span style={{ color: "#7f8c8d", fontSize: "0.78em" }}>
            {players.filter(p => p.has_pos_ev).length} with positive-EV cells
          </span>
          <span style={{ color: "#7f8c8d", fontSize: "0.78em" }}>
            {booksShown.length} books
          </span>
        </div>
      )}

      {loading && (
        <div style={{ color: "#7f8c8d", padding: 24, textAlign: "center" }}>Loading…</div>
      )}

      {!loading && data && players.length === 0 && (
        <div style={{
          padding: 24, textAlign: "center", color: "#7f8c8d",
          background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10,
        }}>
          No players match current filters.
        </div>
      )}

      {/* Table */}
      {!loading && players.length > 0 && (
        <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10, maxHeight: 600, overflowY: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
            <thead>
              <tr>
                <th style={{ ...th, textAlign: "left", minWidth: 140 }}>Player</th>
                <th style={{ ...th, textAlign: "center", background: "#0a1e38", color: "#4cb8ff", minWidth: 70 }}>
                  DG Model
                </th>
                {booksShown.map(b => (
                  <th key={b} style={{ ...th, textAlign: "center", minWidth: 70 }}>
                    {BOOK_ABBR[b] ?? b.slice(0, 3)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {players.map((p, i) => {
                const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
                const tdBase: React.CSSProperties = { padding: "5px 10px", borderBottom: "1px solid #0f2236", background: bg };
                return (
                  <tr key={p.player}>
                    <td style={{ ...tdBase, color: "#dde6f5", fontWeight: 500, fontSize: "0.85em", whiteSpace: "nowrap" }}>
                      {p.player}
                    </td>
                    <td style={{ ...tdBase, textAlign: "center", background: i % 2 === 0 ? "#0a1e38" : "#091929", color: "#4cb8ff", fontWeight: 700, fontSize: "0.85em" }}>
                      {p.dg_prob != null ? `${p.dg_prob.toFixed(1)}%` : "—"}
                    </td>
                    {booksShown.map(b => {
                      const cell = p.books[b];
                      const isPos = cell?.ev != null && cell.ev > 0;
                      return (
                        <td key={b} style={{ ...tdBase, textAlign: "center" }}>
                          {cell?.odds ? (
                            <div>
                              <div style={{
                                color: isPos ? "#00c44f" : "#4a6080",
                                fontWeight: isPos ? 700 : 400,
                                fontSize: "0.85em",
                                background: isPos ? "rgba(0,196,79,0.12)" : "transparent",
                                padding: isPos ? "1px 5px" : undefined,
                                borderRadius: isPos ? 3 : undefined,
                                display: "inline-block",
                              }}>
                                {cell.odds}
                              </div>
                              {cell.ev != null && (
                                <div style={{
                                  fontSize: "0.68em",
                                  color: isPos ? "#00c44f" : "#2a4060",
                                  marginTop: 1,
                                }}>
                                  {isPos ? `+${cell.ev.toFixed(1)}%` : `${cell.ev.toFixed(1)}%`}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: "#1a3050" }}>—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p style={{ color: "#4a6080", fontSize: "0.70em", padding: "6px 12px", margin: 0 }}>
            EV = DG model probability × decimal odds − 1. Pinnacle shown for reference — not available in US.
          </p>
        </div>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  background: "#1e3a5f", border: "1px solid #2a4f7f", borderRadius: 6,
  color: "#dde6f5", padding: "6px 14px", fontSize: "0.85em",
  fontWeight: 600, cursor: "pointer",
};

const selectStyle: React.CSSProperties = {
  background: "#0a1525",
  border: "1px solid #1e3a5f",
  borderRadius: 6,
  color: "#dde6f5",
  padding: "6px 10px",
  fontSize: "0.85em",
  outline: "none",
};
