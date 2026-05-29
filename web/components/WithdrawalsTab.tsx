"use client";

import { Withdrawal } from "@/lib/api";

type Props = { withdrawals: Withdrawal[] };

const SOURCE_LABEL: Record<string, string> = {
  pga_field_api:         "PGA Tour API",
  pga_field_api_missing: "PGA Tour API (missing from field)",
  leaderboard:           "Live leaderboard",
  manual:                "Manual",
};

function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function WdRow({ w }: { w: Withdrawal }) {
  return (
    <div style={{
      background: "#1a0d0d", border: "1px solid #5f1e1e",
      borderLeft: "3px solid #e74c3c",
      borderRadius: 7, padding: "10px 14px",
      display: "flex", justifyContent: "space-between", alignItems: "center",
      flexWrap: "wrap", gap: 8,
    }}>
      <div>
        <div style={{ fontWeight: 700, color: "#dde6f5", fontSize: "0.92em" }}>
          {w.player_name}
        </div>
        <div style={{ fontSize: "0.68em", color: "#4a6080", marginTop: 3 }}>
          {SOURCE_LABEL[w.source] ?? w.source}
          {w.detected_at && <span style={{ marginLeft: 8 }}>· {fmtDate(w.detected_at)}</span>}
        </div>
      </div>
      <span style={{
        fontSize: "0.65em", fontWeight: 800, color: "#e74c3c",
        background: "#e74c3c18", padding: "3px 9px",
        borderRadius: 4, border: "1px solid #e74c3c33",
        textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0,
      }}>
        Withdrawn
      </span>
    </div>
  );
}

export default function WithdrawalsTab({ withdrawals }: Props) {
  if (!withdrawals.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 10 }}>
        No confirmed withdrawals for this tournament.
      </div>
    );
  }

  return (
    <div>
      <div style={{ fontSize: "0.65em", fontWeight: 700, color: "#e74c3c", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
        Withdrawals ({withdrawals.length})
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {withdrawals.map(w => <WdRow key={w.player_name} w={w} />)}
      </div>
    </div>
  );
}
