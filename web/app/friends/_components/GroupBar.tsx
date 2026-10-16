"use client";

/**
 * The top of the Friends page: which group you're playing with, plus
 * Invite. Tapping the name (or Invite) opens a bottom sheet: your groups,
 * the members, invite / join / new group, and "Group feed and settings"
 * (the full Groups screen). The phone mockup's frames 1 and 4.
 */

import React, { useEffect, useState } from "react";
import { useActiveGroup } from "./ActiveGroup";
import { btn, btnQuiet, inputStyle, useApi } from "./shared";

type InviteRow = { mine: boolean; revoked: boolean; expires_at: string; uses: number; max_uses: number; url: string };

const label: React.CSSProperties = {
  fontSize: "max(var(--fs-min-xs), 0.72em)", color: "var(--bc-muted)", fontWeight: 700,
  textTransform: "uppercase", letterSpacing: "0.06em",
};

export function GroupBar({ onManage, startJoin = false }: { onManage: () => void; startJoin?: boolean }) {
  const { groups, group } = useActiveGroup();
  const [sheet, setSheet] = useState<null | "menu" | "invite">(startJoin ? "menu" : null);

  if (groups === null) return <div style={{ minHeight: 44, marginBottom: 12 }} />;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 12 }}>
        <button onClick={() => setSheet("menu")} aria-haspopup="dialog" aria-expanded={sheet !== null} style={{
          display: "flex", alignItems: "center", gap: 8, minHeight: 44, minWidth: 0, padding: "4px 0",
          background: "transparent", border: "none", color: "var(--bc-text)", cursor: "pointer", fontFamily: "inherit",
        }}>
          <span style={label}>Group</span>
          <span style={{ fontWeight: 900, fontSize: "1.05em", textTransform: "uppercase", fontStretch: "110%",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {group ? group.name : "Join or start a group"}
          </span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}><path d="M6 9l6 6 6-6" /></svg>
        </button>
        {group && (
          <button onClick={() => setSheet("invite")} style={{ ...btnQuiet, color: "var(--bc-text)",
            borderColor: "var(--bc-line-hi)", minHeight: 40, display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M19 8v6M22 11h-6" />
            </svg>
            Invite
          </button>
        )}
      </div>
      {sheet && <GroupSheet inviteFirst={sheet === "invite"} focusJoin={startJoin && !group}
        onClose={() => setSheet(null)} onManage={() => { setSheet(null); onManage(); }} />}
    </>
  );
}

function GroupSheet({ inviteFirst, focusJoin, onClose, onManage }: {
  inviteFirst: boolean; focusJoin: boolean; onClose: () => void; onManage: () => void;
}) {
  const api = useApi();
  const { groups, group, choose, reload } = useActiveGroup();
  const [link, setLink] = useState("");
  const [linkErr, setLinkErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState("");
  const [newName, setNewName] = useState("");
  const [err, setErr] = useState("");

  // Reuse a still-working link this member made; otherwise make one. Fetched
  // when the sheet opens so "Share link" is a DIRECT tap: iOS Safari only
  // opens the share sheet straight from a gesture.
  useEffect(() => {
    if (!group) return;
    let cancelled = false;
    setLink(""); setLinkErr("");
    (async () => {
      try {
        const listed = await api(`/api/friends/invites?group_id=${group.id}`);
        const live = ((listed.links as InviteRow[]) ?? []).find(l =>
          l.mine && !l.revoked && new Date(l.expires_at).getTime() > Date.now() && l.uses < l.max_uses);
        const url = live?.url ?? String((await api("/api/friends/invites", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ group_id: group.id }),
        })).url ?? "");
        if (!cancelled) url ? setLink(url) : setLinkErr("Couldn't make a link. Share the invite code instead.");
      } catch {
        if (!cancelled) setLinkErr("Couldn't make a link. Share the invite code instead.");
      }
    })();
    return () => { cancelled = true; };
  }, [group, api]);

  const inviteText = () => `Join my group "${group?.name}" on Golf Edge, one tap: ${link}`;
  async function share() {
    if (typeof navigator.share === "function") {
      try { await navigator.share({ text: inviteText() }); return; } catch { return; }
    }
    copy();
  }
  function copy() {
    try { navigator.clipboard.writeText(inviteText()); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* clipboard blocked */ }
  }

  async function join() {
    if (!code.trim()) return;
    setErr("");
    try {
      const d = await api("/api/friends/groups", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invite_code: code.trim() }),
      });
      setCode(""); reload();
      const id = Number((d.joined as { id?: number } | undefined)?.id ?? 0);
      if (id) choose(id);
    } catch (e) { setErr((e as Error).message); }
  }

  async function create() {
    if (!newName.trim()) return;
    setErr("");
    try {
      const d = await api("/api/friends/groups", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim() }),
      });
      setNewName(""); reload();
      const id = Number(d.id ?? 0);
      if (id) choose(id);
    } catch (e) { setErr((e as Error).message); }
  }

  const chip: React.CSSProperties = {
    padding: "6px 10px", borderRadius: 999, background: "var(--bc-card)", border: "1px solid var(--bc-line)",
    fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 700,
  };

  const inviteBlock = group && (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={label}>Invite to {group.name}</div>
      {link ? (
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={share} style={{ ...btn, flex: 1, minHeight: 48 }}>Share link</button>
          <button onClick={copy} style={{ ...btnQuiet, minHeight: 48, color: "var(--bc-text)" }}>{copied ? "Copied" : "Copy"}</button>
        </div>
      ) : (
        <div style={{ color: "var(--bc-muted)", fontSize: "0.88em" }}>{linkErr || "Making a link…"}</div>
      )}
      {linkErr && <div style={{ color: "var(--bc-muted)", fontSize: "0.88em" }}>Code: <b style={{ color: "var(--bc-text)" }}>{group.invite_code}</b></div>}
      {link && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)" }}>Works for up to 20 friends for 7 days.</div>}
    </div>
  );

  return (
    <>
      <div onClick={onClose} aria-hidden="true" style={{ position: "fixed", inset: 0, zIndex: 400, background: "rgba(0,0,0,0.55)" }} />
      <div role="dialog" aria-label="Your groups" style={{
        position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 401, maxWidth: 560, margin: "0 auto",
        maxHeight: "85vh", overflowY: "auto", background: "var(--bc-panel)", borderTop: "1px solid var(--bc-line-hi)",
        borderRadius: "16px 16px 0 0", padding: "10px 16px calc(24px + env(safe-area-inset-bottom))",
        display: "flex", flexDirection: "column", gap: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={label}>Your groups</div>
          <button onClick={onClose} aria-label="Close" style={{ background: "transparent", border: "none", color: "var(--bc-muted)",
            fontSize: "1.4em", lineHeight: 1, cursor: "pointer", minWidth: 44, minHeight: 44 }}>×</button>
        </div>

        {inviteFirst && inviteBlock}

        {(groups ?? []).length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(groups ?? []).map(g => {
              const on = g.id === group?.id;
              return (
                <button key={g.id} onClick={() => choose(g.id)} aria-pressed={on} style={{
                  display: "flex", alignItems: "center", gap: 12, minHeight: 56, padding: "0 14px", textAlign: "left",
                  background: on ? "var(--bc-raised)" : "var(--bc-card)", cursor: "pointer", fontFamily: "inherit",
                  border: `1px solid ${on ? "var(--bc-line-hi)" : "var(--bc-line)"}`, borderRadius: 10, color: "var(--bc-text)",
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 900, textTransform: "uppercase" }}>{g.name}</div>
                    <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 2 }}>
                      {g.members.length} member{g.members.length === 1 ? "" : "s"}{g.is_owner ? " · you own it" : ""}
                    </div>
                  </div>
                  {on && <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--bc-yellow)" strokeWidth="2.6"
                    strokeLinecap="round" strokeLinejoin="round" role="img" aria-label="Current group"><path d="M5 12l5 5L20 7" /></svg>}
                </button>
              );
            })}
          </div>
        )}

        {group && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={label}>In {group.name}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {group.members.map(m => <span key={m.user_id} style={chip}>{m.user_name}</span>)}
            </div>
          </div>
        )}

        {!inviteFirst && inviteBlock}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <label htmlFor="join-code" style={label}>Join with a code</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input id="join-code" value={code} onChange={e => setCode(e.target.value)} autoFocus={focusJoin}
              placeholder="Invite code" autoCapitalize="characters" style={{ ...inputStyle, flex: 1, minWidth: 0, minHeight: 44 }} />
            <button onClick={join} style={{ ...btnQuiet, color: "var(--bc-text)", minHeight: 44 }}>Join</button>
          </div>
          <label htmlFor="new-group" style={label}>New group</label>
          <div style={{ display: "flex", gap: 8 }}>
            <input id="new-group" value={newName} onChange={e => setNewName(e.target.value)}
              placeholder="Group name" style={{ ...inputStyle, flex: 1, minWidth: 0, minHeight: 44 }} />
            <button onClick={create} style={{ ...btnQuiet, color: "var(--bc-text)", minHeight: 44 }}>Create</button>
          </div>
          {err && <div style={{ color: "var(--bc-red-text)", fontSize: "0.88em" }}>{err}</div>}
        </div>

        <button onClick={onManage} style={{ background: "transparent", border: "none", color: "var(--bc-yellow)",
          fontWeight: 700, fontFamily: "inherit", cursor: "pointer", minHeight: 44 }}>
          Group feed and settings
        </button>
      </div>
    </>
  );
}
