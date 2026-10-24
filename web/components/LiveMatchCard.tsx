"use client";

/**
 * LiveMatchCard — the home page's lead card, which follows the week.
 * Same data as /match (one group, its Let It Ride slates), cut down to one
 * glance and one action: picks open -> Make / Change picks; live -> where
 * you stand and View matchup; finished -> the result and See results.
 * Group choice follows /match's saved pick. Renders `fallback` when there's
 * nothing to show (no group, no season, nothing open, live or just ended)
 * so the home page never goes blank.
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Group, Match, isMatch, matchHeadline, moneyNote, totalsLine } from "@/lib/matchTypes";

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
  if (data === "none") return <>{fallback}</>;

  // The card follows the week (one main action, never a guess):
  //   live and you're in  -> where you stand, "View matchup"
  //   picks open          -> "Make picks", or "Change picks" once yours are in
  //   just finished       -> the result, "See results"
  //   anything else       -> the plain banner
  const mine = (s: Match["slates"][number]) => s.lines.some(l => l.user_id === s.me_id);
  const liveIn = data.slates.filter(s => s.status === "live" && mine(s));
  const open = data.slates.find(s => s.status === "open");
  const done = data.slates.find(s => (s.status === "final" || s.status === "settling") && mine(s));

  const button = (href: string, label: string) => (
    <Link href={href} style={{
      display: "inline-block", marginTop: 12,
      background: "var(--bc-yellow-fill)", color: "#081f14", fontWeight: 900,
      textTransform: "uppercase", fontSize: "max(var(--fs-min), 0.85em)", letterSpacing: "0.06em",
      padding: "12px 20px", borderRadius: 4, whiteSpace: "nowrap" }}>
      {label}
    </Link>
  );
  const kicker = (text: string, isLive = false) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      {isLive && <span style={liveDot} aria-hidden />}
      <span style={{ fontSize: "max(var(--fs-min), 0.8em)", fontWeight: 800, letterSpacing: "0.08em",
        textTransform: "uppercase", color: isLive ? "var(--bc-green)" : "var(--bc-muted)" }}>{text}</span>
      {data.group?.name && <span style={{ fontSize: "max(var(--fs-min), 0.85em)", color: "var(--bc-muted)" }}>{data.group.name}</span>}
    </div>
  );

  if (liveIn.length > 0) {
    // Compact: rank and gap, your total, one button. The golfers live in Match Center.
    return (
      <div style={shell}>
        {kicker("Your matchup · live", true)}
        {liveIn.map(s => (
          <div key={s.tournament_id} style={{ padding: "6px 0" }}>
            {liveIn.length > 1 && (
              <div style={{ fontSize: "max(var(--fs-min), 0.8em)", color: "var(--bc-muted)", fontWeight: 700 }}>{s.name}</div>
            )}
            <div style={{ fontWeight: 900, fontSize: "1.2em", lineHeight: 1.25 }}>{matchHeadline(s)}</div>
            <div style={{ fontSize: "max(var(--fs-min), 0.86em)", color: "var(--bc-muted)", fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
              {totalsLine(s)} · {moneyNote(s).replace(/\.$/, "").toLowerCase()}
            </div>
          </div>
        ))}
        {button("/match", "View matchup")}
      </div>
    );
  }
  if (open) {
    const picked = mine(open);
    return (
      <div style={{ ...shell, borderColor: "var(--bc-line)" }}>
        {kicker("Picks open")}
        <div style={{ fontWeight: 900, fontSize: "1.2em", lineHeight: 1.25 }}>
          {picked ? `Your ${open.name} picks are in.` : `${open.name}: make your picks.`}
        </div>
        <div style={{ fontSize: "max(var(--fs-min), 0.86em)", color: "var(--bc-muted)", marginTop: 2 }}>
          {picked ? "Everyone's picks are revealed when the event locks." : "Pick your golfers before the first tee time."}
        </div>
        {button("/friends?game=ride", picked ? "Change picks" : "Make picks")}
      </div>
    );
  }
  if (done) {
    return (
      <div style={{ ...shell, borderColor: "var(--bc-line)" }}>
        {kicker(done.status === "final" ? "Final" : "Settling")}
        <div style={{ fontWeight: 900, fontSize: "1.2em", lineHeight: 1.25 }}>{matchHeadline(done)}</div>
        <div style={{ fontSize: "max(var(--fs-min), 0.86em)", color: "var(--bc-muted)", marginTop: 2 }}>{done.name} · {moneyNote(done)}</div>
        {button("/match", "See results")}
      </div>
    );
  }
  return <>{fallback}</>;
}

const shell: React.CSSProperties = {
  marginTop: 24, padding: "18px 22px", borderRadius: 10,
  background: "var(--bc-card)", border: "1px solid var(--bc-green)",
};

const liveDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: "50%", background: "var(--bc-green)", flexShrink: 0,
  boxShadow: "0 0 0 3px color-mix(in srgb, var(--bc-green) 25%, transparent)",
};
