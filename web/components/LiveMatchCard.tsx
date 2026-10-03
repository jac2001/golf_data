"use client";

/**
 * LiveMatchCard — the home page's lead while a tournament is in play.
 * Same data as /match (one group, its Let It Ride slates), cut down to
 * the glance: where you stand, the story, your three golfers, and one
 * way in to the full Match Center. Group choice follows /match's saved
 * pick. Renders `fallback` whenever there's nothing live to show (no
 * group, no season, no locked slate) so the home page never goes blank.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Group, Match, isMatch, matchHeadline, money, moneyNote, totalsLine } from "@/lib/matchTypes";
import { displaySurnames } from "@/lib/names";

export default function LiveMatchCard({ fallback }: { fallback: React.ReactNode }) {
  const [data, setData] = useState<Match | null | "none">(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const g = await fetch("/api/friends/groups").then(r => r.ok ? r.json() : { groups: [] });
        const groups: Group[] = g.groups ?? [];
        let saved: number | null = null;
        try { saved = Number(localStorage.getItem("match-group")) || null; } catch { /* fine */ }
        const pick = groups.find(x => x.id === saved) ?? groups[0];
        if (!pick) { if (alive) setData("none"); return; }
        const m = await fetch(`/api/match?group_id=${pick.id}`).then(r => r.ok ? r.json() : null);
        if (alive) setData(isMatch(m) ? m : "none");
      } catch { if (alive) setData("none"); }
    };
    load();
    const t = setInterval(load, 120_000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (data === null) return <div style={{ ...shell, minHeight: 120 }} aria-busy="true" />;
  const slates = data === "none" ? [] : data.slates.filter(s => s.status === "live" && s.lines.length > 0);
  if (data === "none" || slates.length === 0) return <>{fallback}</>;

  return (
    <div style={shell}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={liveDot} aria-hidden />
        <span style={{ fontSize: "max(var(--fs-min), 0.8em)", fontWeight: 800, letterSpacing: "0.08em",
          textTransform: "uppercase", color: "var(--bc-green)" }}>
          Your matchup · live
        </span>
        {data.group?.name && <span style={{ fontSize: "max(var(--fs-min), 0.85em)", color: "var(--bc-muted)" }}>{data.group.name}</span>}
      </div>

      {slates.map(s => {
        const me = s.lines.find(l => l.user_id === s.me_id);
        return (
          <div key={s.tournament_id} style={{ padding: "10px 0", borderTop: "1px solid var(--bc-line)" }}>
            <div style={{ fontSize: "max(var(--fs-min), 0.85em)", color: "var(--bc-muted)", fontWeight: 700 }}>
              {s.tour === "euro" ? "DP World Tour" : "PGA Tour"} · {s.name}
            </div>
            <div style={{ fontWeight: 900, fontSize: "1.4em", lineHeight: 1.2, margin: "4px 0" }}>
              {matchHeadline(s)}
            </div>
            <div style={{ fontWeight: 700, fontSize: "0.95em", fontVariantNumeric: "tabular-nums" }}>{totalsLine(s)}</div>
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>{moneyNote(s)}</div>
            {me && me.golfers.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", marginTop: 8, fontSize: "0.92em" }}>
                {me.golfers.map((g, i) => (
                  <span key={g.name} style={{ whiteSpace: "nowrap" }}>
                    <span style={{ color: "var(--bc-muted)", fontWeight: 700 }}>{g.position}</span>{" "}
                    <span style={{ fontWeight: 700 }}>{displaySurnames(me.golfers.map(x => x.name))[i]}</span>{" "}
                    <span style={{ fontVariantNumeric: "tabular-nums" }}>{money(g.earnings)}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
        <Link href="/match" style={{
          background: "var(--bc-yellow)", color: "#081f14", fontWeight: 900,
          textTransform: "uppercase", fontSize: "max(var(--fs-min), 0.85em)", letterSpacing: "0.06em",
          padding: "12px 20px", borderRadius: 4, whiteSpace: "nowrap" }}>
          Open Match Center
        </Link>
        <Link href="/live" style={{ fontWeight: 700, fontSize: "0.9em", color: "var(--bc-text)" }}>
          Full leaderboard →
        </Link>
      </div>
    </div>
  );
}

const shell: React.CSSProperties = {
  marginTop: 24, padding: "18px 22px", borderRadius: 10,
  background: "var(--bc-card)", border: "1px solid var(--bc-green)",
};

const liveDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: "50%", background: "var(--bc-green)", flexShrink: 0,
  boxShadow: "0 0 0 3px color-mix(in srgb, var(--bc-green) 25%, transparent)",
};
