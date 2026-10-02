"use client";

/**
 * Match Center — why you open Golf Edge on Saturday.
 *
 * One group's weekend, translated from the leaderboard into the only
 * question that matters: what needs to happen for me to beat my friends?
 * Your position, your closest rival and the gap, the golfers driving each
 * score, the move that would flip it, the group vs the model, and the
 * College Game's school race. Polls every 2 minutes during play; changes
 * since your last look ("You took the lead") come from comparing with
 * the previous snapshot kept on this device.
 */
import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { PageHead } from "@/components/broadcast";
import { displaySurnames } from "@/lib/names";

type Golfer = { name: string; position: string; earnings: number; up_one: number; thru: string };
type Line = { user_id: string; user_name: string; total: number; golfers: Golfer[]; rank: number };
type Slate = {
  tournament_id: string; name: string; tour: "pga" | "euro"; status: "open" | "live" | "settling" | "final";
  projected: boolean; lines: Line[]; me_id: string; data_updated?: string;
  rival: { user_id: string; user_name: string; total: number } | null; gap: number; story: string;
  beating_model: number | null; humans: number;
};
type CollegeLine = { user_id: string; user_name: string; school: string; total: number; rank: number;
  counting: { name: string; position: string; earnings: number }[] };
type College = { tournament_id: string; name: string; status: Slate["status"]; projected: boolean;
  lines: CollegeLine[]; me_id: string; story: string } | null;
type Match = { group?: { id: number; name: string; members: number };
  league: { id: number; name: string } | null; slates: Slate[]; college: College; checked_at?: string };
type Group = { id: number; name: string };

const money = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;
const last = (n: string) => n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);
const ordinal = (n: number) => `${n}${["th", "st", "nd", "rd"][((n % 100) - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th"}`;
const card: React.CSSProperties = {
  background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 10, padding: 18, marginBottom: 16,
};

async function call<T>(url: string): Promise<T> {
  const res = await fetch(url);
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((d as { error?: string }).error ?? `Request failed (${res.status})`);
  return d as T;
}

/** What changed since this device last looked — the "meaningful changes". */
/** A response (or saved snapshot) we can safely read. Anything else —
 *  an error body, a cached page, a snapshot from an older version of this
 *  page — is treated as absent rather than crashing the render. */
function isMatch(x: unknown): x is Match {
  const m = x as Match | null;
  return !!m && typeof m === "object" && Array.isArray(m.slates);
}

function changesBetween(prev: Match | null, next: Match): string[] {
  if (!isMatch(prev)) return [];
  const out: string[] = [];
  for (const s of next.slates) {
    const p = prev.slates.find(x => x.tournament_id === s.tournament_id);
    if (!p) continue;
    const meNow = s.lines.find(l => l.user_id === s.me_id);
    const meThen = p.lines.find(l => l.user_id === s.me_id);
    if (meNow && meThen) {
      if (meNow.rank === 1 && meThen.rank > 1) out.push(`You took the lead at ${s.name}.`);
      else if (meNow.rank > meThen.rank) {
        const passer = s.lines.find(l => l.rank < meNow.rank && (p.lines.find(o => o.user_id === l.user_id)?.rank ?? 99) > meThen.rank);
        out.push(passer ? `${passer.user_name} passed you at ${s.name}.` : `You dropped to ${ordinal(meNow.rank)} at ${s.name}.`);
      } else if (meNow.rank < meThen.rank) out.push(`You moved up to ${ordinal(meNow.rank)} at ${s.name}.`);
    }
    if (s.beating_model != null && p.beating_model != null && s.beating_model !== p.beating_model) {
      out.push(`${s.beating_model} of ${s.humans} now beating the model at ${s.name}.`);
    }
    if (s.status === "final" && p.status !== "final") out.push(`${s.name} is final.`);
  }
  const c = next.college, pc = prev.college;
  if (c && pc) {
    const now = c.lines.find(l => l.user_id === c.me_id), then = pc.lines.find(l => l.user_id === c.me_id);
    if (now && then) {
      const a = now.counting.map(x => x.name).join("|"), b = then.counting.map(x => x.name).join("|");
      if (a !== b && now.counting[1]) out.push(`Your second counting golfer changed: ${last(now.counting[1].name)} now counts for ${now.school}.`);
      if (now.rank === 1 && then.rank > 1) out.push(`${now.school} took the lead in the school race.`);
    }
  }
  return out;
}

export default function MatchCenterPage() {
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [data, setData] = useState<Match | null>(null);
  const [changes, setChanges] = useState<string[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    call<{ groups: Group[] }>("/api/friends/groups")
      .then(d => {
        setGroups(d.groups ?? []);
        let saved: number | null = null;
        try { saved = Number(localStorage.getItem("match-group")) || null; } catch { /* fine */ }
        const pick = (d.groups ?? []).find(g => g.id === saved) ?? (d.groups ?? [])[0];
        if (pick) setGroupId(pick.id);
      })
      .catch(e => { setErr(e.message); setGroups([]); });
  }, []);

  const load = useCallback(() => {
    if (!groupId) return;
    call<Match>(`/api/match?group_id=${groupId}`).then(next => {
      if (!isMatch(next)) {
        // Keep whatever was on screen; say so plainly instead of a stack-trace message.
        setErr("Couldn't refresh the match center just now — it retries every 2 minutes.");
        return;
      }
      setErr("");
      const key = `match-snap-${groupId}`;
      let prev: Match | null = null;
      try { prev = JSON.parse(localStorage.getItem(key) ?? "null"); } catch { /* fine */ }
      const ch = changesBetween(prev, next);
      if (ch.length) setChanges(ch);
      try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* fine */ }
      setData(next);
    }).catch(e => setErr(/unauthor|sign in/i.test(String(e.message))
      ? "Sign in to see your group's match center."
      : "Couldn't refresh the match center just now — it retries every 2 minutes."));
  }, [groupId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 120_000);
    return () => clearInterval(t);
  }, [load]);

  if (groups === null) return <p style={{ color: "var(--bc-muted)", padding: 24 }}>Loading…</p>;
  if (groups.length === 0) {
    return (
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <PageHead kicker="Your group's weekend" title="Match Center" />
        <div style={card}>The match center follows a group. <Link href="/friends" style={{ color: "var(--bc-yellow)" }}>Create or join one</Link> first.</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <PageHead kicker={data?.league ? `${data.group?.name ? data.group.name + " · " : ""}${data.league.name}` : "Your group's weekend"} title="Match Center" />
      {data?.checked_at && (
        <div style={{ color: "var(--bc-muted)", fontSize: "0.76em", margin: "-6px 0 12px" }}>
          Checked {new Date(data.checked_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" })}
          {data.slates.find(s => s.data_updated)?.data_updated && ` · live scores as of ${data.slates.find(s => s.data_updated)!.data_updated} (DataGolf)`}
          {" · refreshes every 2 minutes during play"}
        </div>
      )}

      {groups.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {groups.map(g => (
            <button key={g.id} onClick={() => { setGroupId(g.id); setChanges([]); setData(null);
              try { localStorage.setItem("match-group", String(g.id)); } catch { /* fine */ } }}
              style={pill(g.id === groupId)}>{g.name}</button>
          ))}
        </div>
      )}

      {err && <div style={{ ...card, color: "var(--bc-muted)", fontSize: "0.88em" }}>{err}</div>}

      {changes.length > 0 && (
        <div style={{ ...card, borderColor: "var(--bc-yellow)", background: "color-mix(in srgb, var(--bc-yellow) 8%, var(--bc-card))" }}>
          <div style={{ fontSize: "0.7em", fontWeight: 800, color: "var(--bc-yellow)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            Since you last looked
          </div>
          {changes.map((c, i) => <div key={i} style={{ fontWeight: 700, fontSize: "0.92em", padding: "2px 0" }}>{c}</div>)}
        </div>
      )}

      {!data ? <p style={{ color: "var(--bc-muted)" }}>Loading…</p>
        : !data.league ? (
          <div style={card}>No Let It Ride season in this group yet — the owner starts one from <Link href="/friends" style={{ color: "var(--bc-yellow)" }}>Friends → Let It Ride</Link>.</div>
        ) : (
          <>
            {data.slates.map(s => <SlateCard key={s.tournament_id} s={s} groupName={data.group?.name ?? ""} />)}
            {data.college && data.college.lines.length > 0 && <CollegeCard c={data.college} />}
          </>
        )}
    </div>
  );
}

function pill(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "0.74em", textTransform: "uppercase",
    letterSpacing: "0.05em", padding: "7px 13px", borderRadius: 4,
    color: on ? "#081f14" : "var(--bc-muted)", background: on ? "var(--bc-yellow)" : "transparent",
    border: `1px solid ${on ? "var(--bc-yellow)" : "var(--bc-line)"}`,
  };
}

function StatusTag({ status, projected }: { status: Slate["status"]; projected: boolean }) {
  const label = status === "final" ? "Final" : status === "settling" ? "Final · money settling"
    : status === "live" ? (projected ? "Live · projected" : "Live") : "Picks open";
  const color = status === "final" ? "var(--bc-muted)" : status === "live" ? "var(--bc-green)" : "var(--bc-yellow)";
  return <span style={{ fontSize: "0.68em", fontWeight: 800, color, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>;
}

function SlateCard({ s, groupName }: { s: Slate; groupName: string }) {
  const me = s.lines.find(l => l.user_id === s.me_id);
  const tourLabel = s.tour === "euro" ? "DP World Tour" : "PGA Tour";

  if (s.status === "open") {
    return (
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontWeight: 900 }}>{s.name}</span><StatusTag status={s.status} projected={false} />
        </div>
        <p style={{ color: "var(--bc-muted)", fontSize: "0.86em", margin: "8px 0 0" }}>
          {me ? `Your picks: ${displaySurnames(me.golfers.map(g => g.name)).join(", ")}. ` : "You haven't picked yet. "}
          Everyone&apos;s picks appear here once the event locks. <Link href="/friends" style={{ color: "var(--bc-yellow)" }}>Make picks →</Link>
        </p>
      </div>
    );
  }

  const leader = s.lines[0];
  const headline = !me ? "You didn't play this one."
    : me.rank === 1 && s.lines.filter(l => l.rank === 1).length === 1
      ? (s.status === "final" ? "You won the week." : "You're leading.")
      : s.rival && me.rank > 1
        ? `You're ${ordinal(me.rank)}. ${s.rival.user_name} leads you by ${money(s.gap)}.`
        : `You're ${ordinal(me.rank)}.`;

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.74em", color: "var(--bc-muted)", fontWeight: 700 }}>{tourLabel} · {s.name}</span>
        <StatusTag status={s.status} projected={s.projected} />
      </div>
      <div style={{ fontWeight: 900, fontSize: "1.35em", margin: "6px 0 4px", lineHeight: 1.2 }}>{headline}</div>
      {s.story && <div style={{ color: "var(--bc-yellow)", fontWeight: 700, fontSize: "0.92em" }}>{s.story}</div>}
      {s.beating_model != null && s.humans > 0 && (
        <div style={{ color: "var(--bc-muted)", fontSize: "0.84em", marginTop: 4 }}>
          {s.beating_model} of {s.humans} {s.humans === 1 ? "player is" : "players are"} beating the model{s.status === "final" ? "" : " right now"}.
        </div>
      )}

      {me && me.golfers.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: "0.68em", fontWeight: 800, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
            Your golfers
          </div>
          {me.golfers.map(g => (
            <div key={g.name} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "4px 0", borderBottom: "1px solid var(--bc-line)", fontSize: "0.88em" }}>
              <span style={{ fontWeight: 800, width: 42, color: "var(--bc-muted)" }}>{g.position}</span>
              <span style={{ fontWeight: 700 }}>{g.name}</span>
              {g.thru && s.status === "live" && <span style={{ color: "var(--bc-muted)", fontSize: "0.82em" }}>thru {g.thru}</span>}
              <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(g.earnings)}</span>
              {s.status === "live" && g.up_one > 0 && (
                <span style={{ color: "var(--bc-green)", fontSize: "0.78em", whiteSpace: "nowrap" }}>+{money(g.up_one)} one spot up</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: "0.68em", fontWeight: 800, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
          {s.humans <= 1 && s.lines.some(l => l.user_id === "model") ? "You vs. the model" : (groupName || "Your group")}
          {s.projected ? " · projected" : ""}
        </div>
        {s.lines.map(l => {
          const isMe = l.user_id === s.me_id, isModel = l.user_id === "model", isRival = l.user_id === s.rival?.user_id;
          return (
            <div key={l.user_id} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "5px 0", fontSize: "0.88em",
              borderBottom: "1px solid var(--bc-line)" }}>
              <span style={{ width: 22, fontWeight: 900, color: "var(--bc-yellow)" }}>{l.rank}</span>
              <span style={{ fontWeight: 800, color: isMe ? "var(--bc-yellow)" : "var(--bc-text)" }}>
                {isMe ? "You" : l.user_name}
              </span>
              {isModel && <span style={tag("var(--bc-yellow)")}>Model</span>}
              {isRival && !isModel && <span style={tag("var(--bc-orange)")}>Rival</span>}
              <span style={{ color: "var(--bc-muted)", fontSize: "0.82em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {displaySurnames(l.golfers.map(g => g.name)).join(", ")}
              </span>
              <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(l.total)}</span>
            </div>
          );
        })}
        {leader && s.status === "final" && (
          <div style={{ color: "var(--bc-muted)", fontSize: "0.78em", marginTop: 8 }}>
            Sunday recap card: Friends → Groups → Share recap.
          </div>
        )}
      </div>
    </div>
  );
}

function tag(color: string): React.CSSProperties {
  return { fontSize: "0.62em", fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase",
    color: "#081f14", background: color, borderRadius: 3, padding: "1px 5px" };
}

function CollegeCard({ c }: { c: NonNullable<College> }) {
  const me = c.lines.find(l => l.user_id === c.me_id);
  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: "0.74em", color: "var(--bc-muted)", fontWeight: 700 }}>College Game · {c.name}</span>
        <StatusTag status={c.status} projected={c.projected} />
      </div>
      {me ? (
        <>
          <div style={{ fontWeight: 900, fontSize: "1.6em", color: "var(--bc-yellow)", margin: "6px 0 0", letterSpacing: "-0.01em" }}>{me.school}</div>
          <div style={{ fontWeight: 800, fontSize: "0.95em" }}>{ordinal(me.rank)} in the school race · {money(me.total)}</div>
          {c.story && <div style={{ color: "var(--bc-yellow)", fontWeight: 700, fontSize: "0.88em", marginTop: 4 }}>{c.story}</div>}
          <div style={{ marginTop: 10, fontSize: "0.68em", fontWeight: 800, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Your two counting golfers
          </div>
          {me.counting.map(g => (
            <div key={g.name} style={{ display: "flex", gap: 10, padding: "4px 0", fontSize: "0.88em", borderBottom: "1px solid var(--bc-line)" }}>
              <span style={{ width: 42, fontWeight: 800, color: "var(--bc-muted)" }}>{g.position}</span>
              <span style={{ fontWeight: 700 }}>{g.name}</span>
              <span style={{ marginLeft: "auto", fontWeight: 800 }}>{money(g.earnings)}</span>
            </div>
          ))}
        </>
      ) : (
        <p style={{ color: "var(--bc-muted)", fontSize: "0.86em" }}>You didn&apos;t claim a school this week.</p>
      )}
      {c.lines.length > 1 && (
        <div style={{ marginTop: 12 }}>
          {c.lines.map(l => (
            <div key={l.user_id} style={{ display: "flex", gap: 10, fontSize: "0.86em", padding: "3px 0" }}>
              <span style={{ width: 22, fontWeight: 900, color: "var(--bc-yellow)" }}>{l.rank}</span>
              <span style={{ fontWeight: 800 }}>{l.school}</span>
              <span style={{ color: "var(--bc-muted)" }}>{l.user_id === c.me_id ? "you" : l.user_name}</span>
              <span style={{ marginLeft: "auto", fontWeight: 800 }}>{money(l.total)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
