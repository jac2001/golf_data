import type { ScoreBreakdown } from "@/lib/scoreBreakdown";

/** Plain HTML details supports keyboard/touch without additional state. */
export default function ScoreBreakdownPanel({ score }: { score: ScoreBreakdown }) {
  const amount = (value: number | null) => value === null ? "Pending" :
    `$${Math.round(value).toLocaleString("en-US")}`;
  return (
    <details style={{ marginTop: 12 }}>
      <summary style={{ cursor: "pointer", fontWeight: 700, padding: "10px 0" }}>
        How your score adds up
      </summary>
      <div style={{ padding: "12px 0", fontSize: "max(var(--fs-min), 0.9em)" }}>
        <div style={{ fontWeight: 800 }}>{score.title}</div>
        <div style={{ fontSize: "1.6em", fontWeight: 900, fontVariantNumeric: "tabular-nums" }}>{amount(score.total)}</div>
        <p style={{ color: "var(--bc-muted)", margin: "4px 0 12px" }}>{score.note}</p>
        <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
          <caption style={{ textAlign: "left", marginBottom: 8 }}>{score.rule}</caption>
          <thead><tr>
            <th scope="col" style={{ textAlign: "left", width: "55%" }}>Golfer</th>
            <th scope="col" style={{ textAlign: "right" }}>Earnings</th>
          </tr></thead>
          <tbody>{score.rows.map((row, index) => (
            <tr key={`${index}:${row.name}`}>
              <th scope="row" style={{ textAlign: "left", fontWeight: 600, padding: "10px 8px 10px 0", borderBottom: "1px solid var(--bc-line)", overflowWrap: "anywhere" }}>
                {row.name}
                <span style={{ display: "block", color: "var(--bc-muted)", fontWeight: 400 }}>Position: {row.position.trim() || "Pending"}</span>
              </th>
              <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--bc-line)" }}>{amount(row.amount)}</td>
            </tr>
          ))}</tbody>
          <tfoot><tr>
            <th scope="row" style={{ textAlign: "left", paddingTop: 12 }}>Your total</th>
            <td style={{ textAlign: "right", fontWeight: 800, paddingTop: 12, fontVariantNumeric: "tabular-nums" }}>{amount(score.total)}</td>
          </tr></tfoot>
        </table>
        {score.total === null && <p style={{ color: "var(--bc-muted)", marginBottom: 0 }}>Waiting for complete scoring data.</p>}
      </div>
    </details>
  );
}
