"use client";

/**
 * Home — the Broadcast landing. Answers one question in five seconds:
 * who's likely to win this week, and why should you trust the answer.
 * Offseason: hero counts down to the next season's opener and the model
 * board is honestly labeled with its own event ("Last time out").
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getHome, HomeData } from "@/lib/api";
import { Panel, SectionTag, StatStrip, pct } from "@/components/broadcast";

const STORY_COLORS: Record<string, string> = {
  yellow: "var(--bc-yellow)", green: "var(--bc-green)", orange: "var(--bc-orange)",
};

function fmtDates(start: string, end: string): string {
  // Parse date-only strings as LOCAL dates: new Date("2027-01-21") is UTC
  // midnight, which renders as the previous day west of Greenwich.
  const local = (s: string) => {
    const [y, m, d] = s.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d);
  };
  try {
    const s = local(start), e = local(end);
    const fmt = (d: Date) => d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${fmt(s)}–${e.getDate()}`;
  } catch { return start; }
}

export default function Home() {
  const [data, setData] = useState<HomeData | null>(null);
  const [tour, setTour] = useState<"pga" | "euro">(() => {
    try { return localStorage.getItem("favorite-tour") === "euro" ? "euro" : "pga"; }
    catch { return "pga"; }
  });
  const [err, setErr]   = useState("");

  useEffect(() => { getHome(tour).then(setData).catch(e => setErr(String(e))); }, [tour]);

  if (err)   return <div style={{ color: "var(--bc-red)", padding: 24 }}>Failed to load: {err}</div>;
  if (!data) return <div style={{ color: "var(--bc-muted)", padding: 24 }}>Loading…</div>;

  const h = data.hero;

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto" }}>

      {/* ── Tour switch: PGA is home, the DPWT one tap away ─────────────── */}
      <div style={{ display: "flex", gap: 8, paddingTop: 20 }}>
        {([["pga", "PGA Tour"], ["euro", "DP World Tour"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTour(id)} style={{
            cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "0.72em",
            textTransform: "uppercase", letterSpacing: "0.06em",
            padding: "7px 15px", borderRadius: 4,
            color: tour === id ? "#081f14" : "var(--bc-muted)",
            background: tour === id ? "var(--bc-yellow)" : "transparent",
            border: `1px solid ${tour === id ? "var(--bc-yellow)" : "var(--bc-line)"}`,
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 48, padding: "24px 0 30px", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 480px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ fontSize: "0.82em", fontWeight: 700, letterSpacing: "0.16em",
                        textTransform: "uppercase", color: "var(--bc-yellow)" }}>
            {h ? (h.is_live ? "Live this week" : "Next on tour") : "Offseason"}
            {h && ` · ${fmtDates(h.start_date, h.end_date)}`}
            {h?.course && ` · ${h.course}`}
          </div>
          <h1 style={{ margin: 0, fontWeight: 900, fontStretch: "120%",
                       fontSize: "4em", lineHeight: 0.98, textTransform: "uppercase",
                       letterSpacing: "-0.01em" }}>
            {h ? h.name : "See you in January"}
          </h1>
          <div style={{ fontSize: "1em", lineHeight: 1.55, color: "var(--bc-muted)",
                        maxWidth: 560, textWrap: "pretty" as never }}>
            {h?.is_live
              ? "Rounds in progress — live board, model vs reality, and your lineup tracker are running."
              : h
                ? `The ${h.type.toLowerCase() === "signature" ? "season's first signature event" : "season opener"} at ${h.course || h.location}. Predictions go live the Tuesday of tournament week.`
                : "The model is in the offseason lab."}
          </div>
          <div style={{ display: "flex", gap: 14, alignItems: "center", marginTop: 8 }}>
            <Link href="/predictions" style={{
              background: "var(--bc-yellow)", color: "#081f14", fontWeight: 900,
              textTransform: "uppercase", fontSize: "0.82em", letterSpacing: "0.06em",
              padding: "13px 24px", borderRadius: 4 }}>
              This week's forecast
            </Link>
            <Link href="/betting" style={{ fontWeight: 700, fontSize: "0.82em",
              textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--bc-yellow)" }}>
              Betting board →
            </Link>
          </div>
        </div>

        {/* Model board */}
        <Panel style={{ flex: "0 1 460px", minWidth: 380 }}>
          <SectionTag>
            {data.board_is_hero ? "Who the model likes" : `Last time out · ${data.board_event ?? ""}`}
          </SectionTag>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {data.board.map((b, i) => (
              <div key={b.player} style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <div style={{ fontWeight: 900, fontSize: "1.4em", color: "var(--bc-yellow)", width: 24 }}>{i + 1}</div>
                <div style={{ flexGrow: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: "1em" }}>{b.player}</div>
                  <div style={{ fontSize: "0.78em", color: "var(--bc-muted)" }}>{b.why}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontWeight: 900, fontSize: "1.15em" }}>{pct(b.win_prob)}</div>
                  <div style={{ fontSize: "0.72em", color: "var(--bc-muted)" }}>win chance</div>
                </div>
              </div>
            ))}
            {data.board.length === 0 && (
              <div style={{ color: "var(--bc-muted)", fontSize: "0.85em" }}>
                Predictions publish the Tuesday of tournament week.
              </div>
            )}
          </div>
          <div style={{ borderTop: "1px solid var(--bc-card)", marginTop: 16, paddingTop: 12,
                        fontSize: "0.76em", color: "var(--bc-muted)" }}>
            Probabilities calibrated on 3,171 graded predictions ·{" "}
            <Link href="/predictions" style={{ color: "var(--bc-green)" }}>full field →</Link>
          </div>
        </Panel>
      </div>

      {/* ── Storylines ───────────────────────────────────────────────────── */}
      {data.storylines.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                      gap: 20, paddingBottom: 30 }}>
          {data.storylines.map(s => (
            <Panel key={s.tag} accent={STORY_COLORS[s.color] ?? "var(--bc-yellow)"}
                   style={{ background: "var(--bc-card)" }}>
              <SectionTag color={STORY_COLORS[s.color]}>{s.tag}</SectionTag>
              <div style={{ fontWeight: 700, fontSize: "1.1em", lineHeight: 1.25, marginBottom: 8 }}>
                {s.headline}
              </div>
              <div style={{ fontSize: "0.82em", color: "var(--bc-muted)", lineHeight: 1.5 }}>{s.sub}</div>
            </Panel>
          ))}
        </div>
      )}

      {/* ── Trust strip ──────────────────────────────────────────────────── */}
      <div style={{ paddingBottom: 44 }}>
        <StatStrip
          title="Track record"
          stats={Object.values(data.trust).map(t => ({ value: t.value, label: t.label }))}
          right={<Link href="/methodology" style={{ fontWeight: 700, fontSize: "0.8em",
            textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--bc-yellow)" }}>
            How it works →</Link>}
        />
      </div>
    </div>
  );
}
