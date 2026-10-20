"use client";

/**
 * "Who's in": the organizer's view, above each game's picks while picks
 * are open. Counts come from /api/friends/pick-status (how many picks each
 * member has in, never which golfers); the words are Jack's lib/whosIn.ts.
 * Share drops the nudge into the group's own chat (the share sheet on a
 * phone, the clipboard elsewhere): no new notifications from us.
 */

import { useEffect, useState } from "react";
import { whosIn } from "@/lib/whosIn";
import type { MemberCount, WhosIn } from "@/lib/whosIn";
import { eventStatusLine } from "@/lib/eventStatus";
import { lockAt, roundLockAt } from "@/lib/lockTime";
import { useActiveGroup } from "./ActiveGroup";
import { useApi } from "./shared";

export function WhosInCard({ game, tid, eventName, startDate, tour, round, refreshKey = 0 }: {
  game: "ride" | "rounds" | "fades" | "college";
  tid: string; eventName: string; startDate: string; tour: string;
  /** Round Game only: the round still open for picks. */
  round?: number;
  /** Bump after a pick so the counts refresh. */
  refreshKey?: number;
}) {
  const api = useApi();
  const { group } = useActiveGroup();
  const [view, setView] = useState<WhosIn | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!group || !tid || (game === "rounds" && !round)) { setView(null); return; }
    let cancelled = false;
    const roundQ = game === "rounds" ? `&round=${round}` : "";
    api(`/api/friends/pick-status?game=${game}&tournament_id=${encodeURIComponent(tid)}&group_id=${group.id}${roundQ}`)
      .then(d => {
        if (cancelled) return;
        const needed = Number(d.needed ?? 0);
        const members = (d.members as MemberCount[]) ?? [];
        if (!needed || members.length < 2) { setView(null); return; }   // nobody to organize
        const t = tour === "euro" ? "euro" : "pga";
        let lockDetail = "";
        try {
          const at = game === "rounds" && round ? roundLockAt(startDate, t, round) : lockAt(startDate, t);
          if (at.getTime() > Date.now()) {
            lockDetail = eventStatusLine({ status: "open", tour: t, startDate, lockAt: at, round: null }, new Date()).detail;
          }
        } catch { /* unknown lock: leave it out */ }
        try { setView(whosIn(members, needed, eventName, lockDetail)); } catch { setView(null); }
      })
      .catch(() => { if (!cancelled) setView(null); });
    return () => { cancelled = true; };
  }, [api, group, game, tid, eventName, startDate, tour, round, refreshKey]);

  if (!view) return null;

  async function share() {
    if (!view?.shareText) return;
    if (typeof navigator.share === "function") {
      try { await navigator.share({ text: view.shareText }); return; } catch { return; }
    }
    try { await navigator.clipboard.writeText(view.shareText); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* clipboard blocked */ }
  }

  const chip = (name: string, isIn: boolean) => (
    <span key={name} style={{ padding: "4px 10px", borderRadius: 999, fontSize: "max(var(--fs-min), 0.8em)",
      fontWeight: 700, border: `1px solid ${isIn ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
      background: isIn ? "var(--bc-raised)" : "transparent", color: isIn ? "var(--bc-text)" : "var(--bc-muted)",
      display: "inline-flex", alignItems: "center", gap: 5 }}>
      {isIn && <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--bc-green)" strokeWidth="3"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7" /></svg>}
      {name}
    </span>
  );

  return (
    <div style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10,
      padding: "10px 12px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
        <div style={{ fontWeight: 800 }}>{view.headline}</div>
        {view.shareText && (
          <button onClick={share} style={{ minHeight: 36, padding: "0 12px", cursor: "pointer", fontFamily: "inherit",
            fontWeight: 800, fontSize: "max(var(--fs-min), 0.8em)", background: "transparent", color: "var(--bc-text)",
            border: "1px solid var(--bc-line-hi)", borderRadius: 6, flexShrink: 0 }}>
            {copied ? "Copied" : "Nudge the group"}
          </button>
        )}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {view.inNames.map(n => chip(n, true))}
        {view.waitingNames.map(n => chip(n, false))}
      </div>
    </div>
  );
}
