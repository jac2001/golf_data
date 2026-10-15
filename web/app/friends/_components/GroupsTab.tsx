"use client";

/**
 * Groups: create, join, invite, members, and the group feed.
 * Split out of app/friends/page.tsx unchanged.
 */

import React, { useCallback, useEffect, useState } from "react";
import { LetItRideStandings } from "@/components/LetItRideTab";
import RecapPreview from "@/components/RecapPreview";
import { ModelBadge, PlayerLink, btn, btnQuiet, card, inputStyle, useApi } from "./shared";

// ── Groups ───────────────────────────────────────────────────────────────────

export type Group = { id: number; name: string; invite_code: string; is_owner: boolean;
  members: { user_id: string; user_name: string }[] };
export type FeedBet = { user_name: string; description: string; odds_american: number | null;
  stake_units: number; outcome: string; tournament_id: string };
export type FeedPick = { event: string; user_name: string; player_name: string };

export function GroupsTab({ focusJoin = false }: { focusJoin?: boolean }) {
  const [recapFor, setRecapFor] = useState<Group | null>(null);
  // Per group: is a recap available yet? (undefined = still checking)
  const [recapOk, setRecapOk] = useState<Record<number, boolean>>({});
  const api = useApi();
  const joinRef = React.useRef<HTMLInputElement>(null);
  useEffect(() => { if (focusJoin) joinRef.current?.focus(); }, [focusJoin]);
  const [groups, setGroups]   = useState<Group[] | null>(null);
  const [open, setOpen]       = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [code, setCode]       = useState("");
  const [err, setErr]         = useState("");
  const [copied, setCopied]   = useState<number | null>(null);
  // One-tap invite link per group (/api/friends/invites): fetched on the
  // first tap, shared on the second. iOS Safari only opens the share sheet
  // as a DIRECT response to a tap; awaiting a fetch first can lose that.
  const [inviteLink, setInviteLink] = useState<Record<number, string>>({});
  const [inviteErr, setInviteErr] = useState<Record<number, string>>({});

  const load = useCallback(() => {
    api("/api/friends/groups")
      .then(d => setGroups((d.groups as Group[]) ?? []))
      .catch(e => { setErr(String(e.message)); setGroups([]); });
  }, [api]);
  useEffect(load, [load]);

  async function create() {
    if (!newName.trim()) return;
    setErr("");
    try {
      await api("/api/friends/groups", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      setNewName(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function join() {
    if (!code.trim()) return;
    setErr("");
    try {
      await api("/api/friends/groups", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite_code: code.trim() }),
      });
      setCode(""); load();
    } catch (e) { setErr((e as Error).message); }
  }

  async function leave(g: Group) {
    if (!confirm(g.is_owner
      ? `Delete "${g.name}" for everyone? This can't be undone.`
      : `Leave "${g.name}"?`)) return;
    try {
      await api("/api/friends/groups", {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: g.id }),
      });
    } catch { /* list reload below shows truth either way */ }
    setOpen(null); load();
  }

  function copyCode(g: Group) {
    try { navigator.clipboard.writeText(g.invite_code); setCopied(g.id);
      setTimeout(() => setCopied(null), 1500); } catch { /* clipboard blocked */ }
  }

  function inviteMessage(g: Group) {
    return `Join my group "${g.name}" on Golf Edge: ${window.location.origin}/friends?invite=1 — invite code: ${g.invite_code}`;
  }

  // Copies a ready-to-text message: the link gets them signed in and onto
  // the join form; the code in the same message is what they type there.
  function copyLink(g: Group) {
    try {
      navigator.clipboard.writeText(inviteMessage(g));
      setCopied(g.id); setTimeout(() => setCopied(null), 1500);
    } catch { /* clipboard blocked */ }
  }

  // Reuse a still-working link this member made; otherwise make one.
  async function getInviteLink(g: Group) {
    setInviteErr(e => ({ ...e, [g.id]: "" }));
    try {
      const listed = await fetch(`/api/friends/invites?group_id=${g.id}`, { cache: "no-store" }).then(r => r.json());
      const live = (listed.links ?? []).find((l: { mine: boolean; revoked: boolean; expires_at: string; uses: number; max_uses: number }) =>
        l.mine && !l.revoked && new Date(l.expires_at).getTime() > Date.now() && l.uses < l.max_uses);
      if (live) { setInviteLink(m => ({ ...m, [g.id]: live.url })); return; }
      const r = await fetch("/api/friends/invites", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id: g.id }),
      });
      const d = await r.json();
      if (!r.ok || !d.url) throw new Error(d.error || "Couldn't make a link");
      setInviteLink(m => ({ ...m, [g.id]: d.url }));
    } catch {
      setInviteErr(e => ({ ...e, [g.id]: "Couldn't make a link — share the invite code instead." }));
    }
  }

  function inviteText(g: Group) {
    return `Join my group "${g.name}" on Golf Edge — one tap: ${inviteLink[g.id]}`;
  }

  async function shareLink(g: Group) {
    const text = inviteText(g);
    if (typeof navigator.share === "function") {
      try { await navigator.share({ text }); return; } catch { return; }
    }
    copyInvite(g);
  }

  function copyInvite(g: Group) {
    try { navigator.clipboard.writeText(inviteText(g)); setCopied(g.id);
      setTimeout(() => setCopied(null), 1500); } catch { /* clipboard blocked */ }
  }

  /** The Sunday recap PNG for this group's latest settled event —
   *  built to be dropped straight into the group chat. */
  useEffect(() => {
    for (const g of groups ?? []) {
      fetch(`/api/recap?group_id=${g.id}&check=1`).then(r => r.json())
        .then(d => setRecapOk(o => ({ ...o, [g.id]: !!d.available })))
        .catch(() => setRecapOk(o => ({ ...o, [g.id]: true })));   // unknown: let the preview explain
    }
  }, [groups]);

  if (!groups) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;

  return (
    <>
      {recapFor && <RecapPreview groupId={recapFor.id} groupName={recapFor.name} onClose={() => setRecapFor(null)} />}
      <div style={{ ...card, display: "flex", gap: 20, flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="New group name…" style={inputStyle}
            onKeyDown={e => e.key === "Enter" && create()} />
          <button onClick={create} style={btn}>Create</button>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input ref={joinRef} value={code} onChange={e => setCode(e.target.value.toUpperCase())}
            placeholder="Invite code…" style={{ ...inputStyle, width: 130,
              textTransform: "uppercase", letterSpacing: "0.1em" }}
            onKeyDown={e => e.key === "Enter" && join()} />
          <button onClick={join} style={btnQuiet}>Join</button>
        </div>
        {err && <span style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", alignSelf: "center" }}>{err}</span>}
      </div>

      {groups.length === 0 && (
        <div style={card}>
          <p style={{ color: "var(--bc-muted)", margin: 0, fontSize: "max(var(--fs-min), 0.88em)" }}>
            No groups yet. Create one and text the invite code to your friends —
            group standings, shared bets, and everyone&apos;s picks (revealed at
            lock) live here.
          </p>
        </div>
      )}

      {groups.map(g => (
        <div key={g.id} style={card}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, fontSize: "1.05em" }}>{g.name}</span>
            <button onClick={() => copyCode(g)} title="Copy invite code" style={{
              ...btnQuiet, padding: "4px 10px", letterSpacing: "0.1em",
              color: copied === g.id ? "var(--bc-green)" : "var(--bc-muted)",
            }}>
              {copied === g.id ? "Copied!" : g.invite_code}
            </button>
            <button onClick={() => getInviteLink(g)} title="Make a one-tap invite link" style={{
              ...btnQuiet, padding: "4px 10px", color: "var(--bc-text)", borderColor: "var(--bc-line-hi)",
            }}>
              Invite friends
            </button>
            {recapOk[g.id] === false ? (
              <span title="The recap is built once an event your group played is final"
                style={{ ...btnQuiet, padding: "4px 10px", opacity: 0.6, cursor: "default" }}>
                Recap after your first completed event
              </span>
            ) : (
              <button onClick={() => setRecapFor(g)}
                title="Share this group's Sunday recap card" style={{
                ...btnQuiet, padding: "4px 10px", color: "var(--bc-text)",
                borderColor: "var(--bc-line-hi)",
              }}>
                Sunday recap
              </button>
            )}
            <button onClick={() => copyLink(g)} title="Copy the invite message" style={{
              ...btnQuiet, padding: "4px 10px",
              color: copied === g.id ? "var(--bc-green)" : "var(--bc-text)",
              borderColor: "var(--bc-line-hi)",
            }}>
              {copied === g.id ? "Copied!" : "Copy invite"}
            </button>
            <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)" }}>
              {g.members.map(m => m.user_name).join(" · ")}
            </span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button onClick={() => setOpen(open === g.id ? null : g.id)} style={btnQuiet}>
                {open === g.id ? "Hide" : "Open"}
              </button>
              <button onClick={() => leave(g)} style={{ ...btnQuiet, color: "var(--bc-red-text)" }}>
                {g.is_owner ? "Delete" : "Leave"}
              </button>
            </span>
          </div>
          {(inviteLink[g.id] || inviteErr[g.id]) && (
            <div style={{ marginTop: 10, padding: "10px 12px", borderRadius: 10,
                          background: "var(--bc-panel)", border: "1px solid var(--bc-line)" }}>
              {inviteErr[g.id] ? (
                <span style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)" }}>{inviteErr[g.id]}</span>
              ) : (
                <>
                  <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginBottom: 8 }}>
                    One tap to join for up to 20 friends · works for 7 days
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    <button onClick={() => shareLink(g)} style={{ ...btn, minHeight: 44, padding: "0 18px" }}>Share link</button>
                    <button onClick={() => copyInvite(g)} style={{ ...btnQuiet, minHeight: 44, padding: "0 14px",
                      color: copied === g.id ? "var(--bc-green)" : "var(--bc-text)" }}>
                      {copied === g.id ? "Copied!" : "Copy"}
                    </button>
                    <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min-xs), 0.74em)", wordBreak: "break-all" }}>
                      {inviteLink[g.id]}
                    </span>
                  </div>
                </>
              )}
            </div>
          )}
          {open === g.id && <GroupFeed groupId={g.id} />}
        </div>
      ))}
    </>
  );
}

export function GroupFeed({ groupId }: { groupId: number }) {
  const api = useApi();
  const [feed, setFeed] = useState<{ openNames?: string[];
    bets: FeedBet[]; picks: FeedPick[];
    modelMoves?: { event: string; game: string; text: string }[] } | null>(null);
  useEffect(() => {
    api(`/api/friends/feed?group_id=${groupId}`)
      .then(d => setFeed(d as never))
      .catch(() => setFeed({ openNames: [], bets: [], picks: [] }));
  }, [groupId, api]);

  if (!feed) return <p style={{ color: "var(--bc-muted)", marginTop: 12 }}>Loading…</p>;

  // Group picks by event, then by user, for the reveal.
  const byEvent = new Map<string, Map<string, string[]>>();
  for (const p of feed.picks) {
    const ev = byEvent.get(p.event) ?? new Map<string, string[]>();
    ev.set(p.user_name, [...(ev.get(p.user_name) ?? []), p.player_name]);
    byEvent.set(p.event, ev);
  }

  return (
    <div style={{ marginTop: 16, display: "grid", gap: 14 }}>
      {/* The Model's week — its locked-in moves, in its own voice. */}
      {(feed.modelMoves ?? []).length > 0 && (
        <div style={{ ...card, marginBottom: 0,
          border: "1px solid var(--bc-line-hi)" }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>
            The Model&apos;s week <ModelBadge />
          </div>
          <div style={{ display: "grid", gap: 6 }}>
            {(feed.modelMoves ?? []).map((m, i) => (
              <div key={i} style={{ fontSize: "max(var(--fs-min), 0.84em)", lineHeight: 1.5 }}>
                <span style={{ color: "var(--bc-text)", fontWeight: 700 }}>{m.game}</span>
                <span style={{ color: "var(--bc-muted)" }}> · {m.event} — </span>
                {m.text}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Season standings — the group's Let It Ride season */}
      <LetItRideStandings groupId={groupId} compact />
      {/* Picks — revealed per event once it locks */}
      <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.7em)", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Picks
        </div>
        {byEvent.size === 0 ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)" }}>
            {feed.openNames?.length
              ? `Hidden until lock — picks open for ${feed.openNames.join(", ")}.`
              : "No locked events with picks yet."}
          </span>
        ) : (
          [...byEvent.entries()].map(([evName, byUser]) => (
            <div key={evName} style={{ marginBottom: 8 }}>
              <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", fontWeight: 700 }}>{evName}</div>
              {[...byUser.entries()].map(([user, ps]) => (
                <div key={user} style={{ fontSize: "max(var(--fs-min), 0.86em)", padding: "2px 0" }}>
                  <span style={{ fontWeight: 600 }}>{user}</span>
                  <span style={{ color: "var(--bc-muted)" }}> — </span>
                  {ps.map((pl, pi) => (
                    <React.Fragment key={pl}>
                      {pi > 0 && <span style={{ color: "var(--bc-muted)" }}>, </span>}
                      <PlayerLink name={pl} style={{ color: "var(--bc-muted)" }} />
                    </React.Fragment>
                  ))}
                </div>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Shared bets */}
      <div style={{ background: "var(--bc-panel)", borderRadius: 8, padding: "10px 14px" }}>
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.7em)", fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Shared bets</div>
        {feed.bets.length === 0 ? (
          <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)" }}>
            Nothing shared yet — log a bet on the My Bets tab and flip it to shared.
          </span>
        ) : feed.bets.map((b, i) => (
          <div key={i} style={{ display: "flex", gap: 8, fontSize: "max(var(--fs-min), 0.86em)", padding: "3px 0", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600 }}>{b.user_name}</span>
            <span>{b.description}</span>
            {b.odds_american != null && (
              <span style={{ color: "var(--bc-muted)" }}>
                {b.odds_american > 0 ? `+${b.odds_american}` : b.odds_american}
              </span>
            )}
            <span style={{ marginLeft: "auto", fontWeight: 700,
              color: b.outcome === "won" ? "var(--bc-green)"
                   : b.outcome === "lost" ? "var(--bc-red-text)" : "var(--bc-muted)" }}>
              {b.outcome}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
