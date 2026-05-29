/**
 * BookTable.tsx
 * ==============
 * Multi-book odds comparison table. Shows every player in the selected market
 * with their odds at each sportsbook side-by-side, sorted by model edge.
 *
 * Props:
 *   data  — the OddsComparison object from the API
 */

"use client";

import { OddsComparison, BOOK_ABBR } from "@/lib/api";

type Props = {
  data: OddsComparison;
};

export default function BookTable({ data }: Props) {
  if (!data.players.length) {
    return <p style={{ color: "#7f8c8d", fontSize: "0.9em" }}>No odds data available.</p>;
  }

  // Column header style
  const th: React.CSSProperties = {
    background: "#0a1628",
    color: "#8ba0b8",
    fontSize: "0.70em",
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    padding: "8px 12px",
    borderBottom: "1px solid #1e3a5f",
    whiteSpace: "nowrap",
  };

  // Cell style
  const td: React.CSSProperties = {
    padding: "7px 12px",
    borderBottom: "1px solid #0f2236",
    fontSize: "0.85em",
  };

  return (
    <div style={{ overflowX: "auto", border: "1px solid #1e3a5f", borderRadius: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
        <thead>
          <tr>
            {/* Fixed columns */}
            <th style={{ ...th, textAlign: "left" }}>Player</th>
            <th style={{ ...th, textAlign: "center" }}>Model%</th>

            {/* One column per book */}
            {data.books.map((book) => (
              <th key={book} style={{ ...th, textAlign: "center" }}>
                {BOOK_ABBR[book] ?? book.slice(0, 3)}
              </th>
            ))}

            {/* Edge column */}
            <th style={{ ...th, textAlign: "center" }}>
              Edge vs {BOOK_ABBR[data.ref_book] ?? data.ref_book}
            </th>
          </tr>
        </thead>

        <tbody>
          {data.players.map((p, i) => {
            const bg = i % 2 === 0 ? "#0d1a30" : "#0a1525";
            const edge = p.edge_vs_dk;
            const edgeColor =
              edge == null ? "#7f8c8d"
              : edge > 1   ? "#00c44f"
              : edge > 0   ? "#f39c12"
              :               "#7f8c8d";

            return (
              <tr key={p.player} style={{ background: bg }}>
                {/* Player name */}
                <td style={{ ...td, color: "#dde6f5", fontWeight: 600, textAlign: "left" }}>
                  {p.player}
                </td>

                {/* Model probability */}
                <td style={{ ...td, color: "#00c44f", fontWeight: 700, textAlign: "center" }}>
                  {p.model_prob != null ? `${p.model_prob.toFixed(1)}%` : "—"}
                </td>

                {/* Odds per book */}
                {data.books.map((book) => (
                  <td key={book} style={{ ...td, color: "#dde6f5", textAlign: "center" }}>
                    {p.book_odds[book] ?? "—"}
                  </td>
                ))}

                {/* Edge */}
                <td style={{ ...td, color: edgeColor, fontWeight: 700, textAlign: "center" }}>
                  {edge != null ? `${edge > 0 ? "+" : ""}${edge.toFixed(1)}pp` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <p style={{ color: "#7f8c8d", fontSize: "0.72em", padding: "8px 12px", margin: 0 }}>
        Sorted by model edge vs {BOOK_ABBR[data.ref_book] ?? data.ref_book}. No-vig normalized.
        Sharp books (PIN) are shown for reference only — not available in the US.
      </p>
    </div>
  );
}
