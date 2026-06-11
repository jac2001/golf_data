"use client";

import Link from "next/link";
import { ModelCompPlayer } from "@/lib/api";

type Props = { players: ModelCompPlayer[] };

const GREEN  = "#00c44f";
const BLUE   = "#4cb8ff";
const BORDER = "#1e3a5f";
const MUTED  = "#4a6080";
const TEXT   = "#dde6f5";

const playerLink = (name: string, style?: React.CSSProperties) => (
  <Link
    href={`/players?player=${encodeURIComponent(name)}`}
    style={{ textDecoration: "none", color: "inherit", ...style }}
    onMouseEnter={e => (e.currentTarget.style.color = "#00c44f")}
    onMouseLeave={e => (e.currentTarget.style.color = style?.color ?? TEXT)}
  >
    {name}
  </Link>
);

// Returns [fillA, fillB] as percentages that always sum to ~100
function splitBar(a: number | null, b: number | null): [number, number] {
  if (a == null || b == null) return [50, 50];
  const total = a + b;
  if (total === 0) return [50, 50];
  return [Math.max(2, a / total * 100), Math.max(2, b / total * 100)];
}

export default function ModelComparison({ players }: Props) {
  if (!players.length) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "#7f8c8d", background: "#0d1a30", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        No comparison data available.
      </div>
    );
  }

  // Top disagreements sorted by |delta|
  const wePrefer = [...players].filter(p => (p.delta ?? 0) > 3).sort((a, b) => (b.delta ?? 0) - (a.delta ?? 0)).slice(0, 3);
  const dgPrefers = [...players].filter(p => (p.delta ?? 0) < -3).sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0)).slice(0, 3);

  const th = (label: string, color = MUTED): React.CSSProperties => ({});

  return (
    <div>
      {/* Disagreement callouts */}
      {(wePrefer.length > 0 || dgPrefers.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
          {/* We prefer */}
          <div style={{ background: "#0a1a10", border: `1px solid ${GREEN}33`, borderRadius: 8, padding: "12px 14px" }}>
            <div style={{ fontSize: "0.65em", fontWeight: 700, color: GREEN, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
              We rank higher than DG
            </div>
            {wePrefer.map(p => (
              <div key={p.player} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: "0.82em", fontWeight: 600 }}>{playerLink(p.player)}</span>
                <span style={{ fontSize: "0.75em" }}>
                  <span style={{ color: GREEN }}>Us #{p.our_rank}</span>
                  <span style={{ color: MUTED, margin: "0 5px" }}>vs</span>
                  <span style={{ color: BLUE }}>DG #{p.dg_rank}</span>
                  <span style={{ color: GREEN, marginLeft: 8, fontWeight: 700 }}>+{p.delta} spots</span>
                </span>
              </div>
            ))}
          </div>
          {/* DG prefers */}
          <div style={{ background: "#0a1220", border: `1px solid ${BLUE}33`, borderRadius: 8, padding: "12px 14px" }}>
            <div style={{ fontSize: "0.65em", fontWeight: 700, color: BLUE, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 8 }}>
              DG ranks higher than us
            </div>
            {dgPrefers.map(p => (
              <div key={p.player} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: "0.82em", fontWeight: 600 }}>{playerLink(p.player)}</span>
                <span style={{ fontSize: "0.75em" }}>
                  <span style={{ color: GREEN }}>Us #{p.our_rank}</span>
                  <span style={{ color: MUTED, margin: "0 5px" }}>vs</span>
                  <span style={{ color: BLUE }}>DG #{p.dg_rank}</span>
                  <span style={{ color: BLUE, marginLeft: 8, fontWeight: 700 }}>{p.delta} spots</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main table */}
      <div style={{ overflowX: "auto", border: `1px solid ${BORDER}`, borderRadius: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", background: "#0d1a30" }}>
          <thead>
            <tr>
              {[
                { label: "#",        color: MUTED,  align: "center" as const, width: 36 },
                { label: "Player",   color: MUTED,  align: "left"   as const },
                { label: "Our #",    color: GREEN,  align: "center" as const },
                { label: "DG #",     color: BLUE,   align: "center" as const },
                { label: "Δ",        color: MUTED,  align: "center" as const },
                { label: "Win % (Us vs DG)", color: MUTED, align: "center" as const, minWidth: 160 },
                { label: "Top 10 % (Us vs DG)", color: MUTED, align: "center" as const, minWidth: 160 },
              ].map(({ label, color, align, width, minWidth }) => (
                <th key={label} style={{
                  padding: "7px 10px", background: "#0a1628",
                  fontSize: "0.68em", fontWeight: 700, color,
                  textTransform: "uppercase", letterSpacing: "0.05em",
                  borderBottom: `1px solid ${BORDER}`,
                  textAlign: align, whiteSpace: "nowrap",
                  width, minWidth,
                }}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {players.map((p, i) => {
              const bg      = i % 2 === 0 ? "#0d1a30" : "#0a1525";
              const delta   = p.delta ?? 0;
              const weUp    = delta > 3;
              const dgUp    = delta < -3;
              const dColor  = weUp ? GREEN : dgUp ? BLUE : MUTED;
              const dStr    = delta === 0 ? "=" : delta > 0 ? `+${delta}` : String(delta);
              const [wA, wB] = splitBar(p.our_win, p.dg_win);
              const [tA, tB] = splitBar(p.our_top10, p.dg_top10);

              const td: React.CSSProperties = {
                padding: "6px 10px", background: bg,
                borderBottom: "1px solid #0f2236", fontSize: "0.85em",
              };

              return (
                <tr key={`${p.player}-${i}`}>
                  <td style={{ ...td, textAlign: "center", color: MUTED, fontSize: "0.75em" }}>{i + 1}</td>

                  <td style={{ ...td, textAlign: "left", fontWeight: 600, whiteSpace: "nowrap" }}>
                    {playerLink(p.player)}
                  </td>

                  <td style={{ ...td, textAlign: "center", color: GREEN, fontWeight: 700 }}>
                    #{p.our_rank}
                  </td>
                  <td style={{ ...td, textAlign: "center", color: BLUE, fontWeight: 700 }}>
                    {p.dg_rank != null ? `#${p.dg_rank}` : "—"}
                  </td>

                  <td style={{ ...td, textAlign: "center", color: dColor, fontWeight: Math.abs(delta) > 3 ? 700 : 400 }}>
                    {dStr}
                  </td>

                  {/* Win % dual bar */}
                  <td style={{ ...td, padding: "6px 14px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "52px 1fr 52px", alignItems: "center", gap: 8 }}>
                      <span style={{ color: GREEN, fontWeight: weUp ? 700 : 400, textAlign: "right", fontSize: "0.88em" }}>
                        {p.our_win != null ? `${p.our_win.toFixed(1)}%` : "—"}
                      </span>
                      <div style={{ display: "grid", gridTemplateColumns: `${wA.toFixed(1)}fr ${wB.toFixed(1)}fr`, height: 7, borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ background: weUp ? GREEN : "#0d2e18" }} />
                        <div style={{ background: dgUp ? BLUE : "#0d1e30" }} />
                      </div>
                      <span style={{ color: BLUE, fontWeight: dgUp ? 700 : 400, fontSize: "0.88em" }}>
                        {p.dg_win != null ? `${p.dg_win.toFixed(1)}%` : "—"}
                      </span>
                    </div>
                  </td>

                  {/* Top 10 % dual bar */}
                  <td style={{ ...td, padding: "6px 14px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "52px 1fr 52px", alignItems: "center", gap: 8 }}>
                      <span style={{ color: GREEN, fontWeight: weUp ? 700 : 400, textAlign: "right", fontSize: "0.88em" }}>
                        {p.our_top10 != null ? `${p.our_top10.toFixed(1)}%` : "—"}
                      </span>
                      <div style={{ display: "grid", gridTemplateColumns: `${tA.toFixed(1)}fr ${tB.toFixed(1)}fr`, height: 7, borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ background: weUp ? GREEN : "#0d2e18" }} />
                        <div style={{ background: dgUp ? BLUE : "#0d1e30" }} />
                      </div>
                      <span style={{ color: BLUE, fontWeight: dgUp ? 700 : 400, fontSize: "0.88em" }}>
                        {p.dg_top10 != null ? `${p.dg_top10.toFixed(1)}%` : "—"}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p style={{ color: "#3a5060", fontSize: "0.70em", marginTop: 6 }}>
        Δ = DG rank − our rank · <span style={{ color: GREEN }}>green = we rank higher</span> · <span style={{ color: BLUE }}>blue = DG ranks higher</span>
      </p>
    </div>
  );
}
