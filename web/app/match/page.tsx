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
import SchoolBadge from "@/components/SchoolBadge";
import { displaySurnames } from "@/lib/names";
import { College, CollegeGolfer, Group, Match, Slate, collegeHeadline, collegeTotals, golferProgress, isMatch, isSoloVsModel, matchHeadline, money, moneyNote, ordinal, totalsLine } from "@/lib/matchTypes";

const last = (n: string) => n.includes(",") ? n.split(",")[0].trim() : (n.trim().split(/\s+/).pop() ?? n);
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
        <div style={card}>The match center follows a group. <Link href="/friends" style={{ color: "var(--bc-text)", textDecoration: "underline" }}>Create or join one</Link> first.</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <PageHead kicker={data?.league ? `${data.group?.name ? data.group.name + " · " : ""}${data.league.name}` : "Your group's weekend"} title="Match Center" />
      {/* One plain timestamp up top, in the viewer's own timezone. The
          source and refresh cadence live in each card's details. */}
      {(() => {
        const at = data?.slates.map(s => s.data_updated_utc).filter(Boolean).sort().pop();
        return at ? (
          <div style={{ color: "var(--bc-text)", fontWeight: 700, fontSize: "max(var(--fs-min), 0.85em)", margin: "-6px 0 12px" }}>
            Scores updated {clock(at)}
          </div>
        ) : null;
      })()}

      {groups.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
          {groups.map(g => (
            <button key={g.id} onClick={() => { setGroupId(g.id); setChanges([]); setData(null);
              try { localStorage.setItem("match-group", String(g.id)); } catch { /* fine */ } }}
              style={pill(g.id === groupId)}>{g.name}</button>
          ))}
        </div>
      )}

      {err && <div style={{ ...card, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)" }}>{err}</div>}

      {changes.length > 0 && (
        <div style={{ ...card, borderColor: "var(--bc-green)" }}>
          <div style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 800, color: "var(--bc-green)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
            Since you last looked
          </div>
          {changes.map((c, i) => <div key={i} style={{ fontWeight: 700, fontSize: "0.92em", padding: "2px 0" }}>{c}</div>)}
        </div>
      )}

      {!data ? <p style={{ color: "var(--bc-muted)" }}>Loading…</p>
        : !data.league ? (
          <div style={card}>No Let It Ride season in this group yet — the owner starts one from <Link href="/friends" style={{ color: "var(--bc-text)", textDecoration: "underline" }}>Friends → Let It Ride</Link>.</div>
        ) : (
          <>
            {data.slates.map(s => <SlateCard key={s.tournament_id} s={s} groupName={data.group?.name ?? ""} checkedAt={data.checked_at} />)}
            {data.college && data.college.lines.length > 0 && <CollegeCard c={data.college} />}
          </>
        )}
    </div>
  );
}

function pill(on: boolean): React.CSSProperties {
  return {
    cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "max(var(--fs-min), 0.74em)", textTransform: "uppercase",
    letterSpacing: "0.05em", padding: "7px 13px", borderRadius: 4,
    color: on ? "var(--bc-text)" : "var(--bc-muted)", background: on ? "var(--bc-raised)" : "transparent",
    border: `1px solid ${on ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
  };
}

function StatusTag({ status, projected }: { status: Slate["status"]; projected: boolean }) {
  const label = status === "final" ? "Final" : status === "settling" ? "Final · money settling"
    : status === "live" ? "Live" : "Picks open";  // what the money means lives in moneyNote, not here
  const color = status === "final" ? "var(--bc-muted)" : status === "live" ? "var(--bc-green)" : "var(--bc-text)";
  return <span style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, color, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</span>;
}

/** "9:40 AM EDT" in the viewer's own timezone. */
function clock(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

function SlateCard({ s, groupName, checkedAt }: { s: Slate; groupName: string; checkedAt?: string }) {
  const me = s.lines.find(l => l.user_id === s.me_id);
  const tourLabel = s.tour === "euro" ? "DP World Tour" : "PGA Tour";

  if (s.status === "open") {
    return (
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <span style={{ fontWeight: 900 }}>{s.name}</span><StatusTag status={s.status} projected={false} />
        </div>
        <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.86em)", margin: "8px 0 0" }}>
          {me ? `Your picks: ${displaySurnames(me.golfers.map(g => g.name)).join(", ")}. ` : "You haven't picked yet. "}
          Everyone&apos;s picks appear here once the event locks. <Link href="/friends" style={{ color: "var(--bc-text)", textDecoration: "underline" }}>Make picks →</Link>
        </p>
      </div>
    );
  }

  const solo = isSoloVsModel(s);
  const live = s.status === "live";
  const others = s.lines.filter(l => l.user_id !== s.me_id);
  const label: React.CSSProperties = { fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, color: "var(--bc-muted)",
    textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 };

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: "max(var(--fs-min), 0.74em)", color: "var(--bc-muted)", fontWeight: 700 }}>{tourLabel} · {s.name}</span>
        <StatusTag status={s.status} projected={false} />
      </div>

      {/* Layer 1 — am I winning? */}
      <div style={{ fontWeight: 900, fontSize: "1.35em", margin: "6px 0 4px", lineHeight: 1.2 }}>{matchHeadline(s)}</div>
      {me && <div style={{ fontWeight: 700, fontSize: "max(var(--fs-min), 0.95em)", fontVariantNumeric: "tabular-nums" }}>{totalsLine(s)}</div>}
      <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", marginTop: 2 }}>{moneyNote(s)}</div>

      {/* Layer 2 — who am I watching? */}
      {me && me.golfers.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={label}>Your golfers</div>
          {me.golfers.map(g => (
            <div key={g.name} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "6px 0",
              borderBottom: "1px solid var(--bc-line)", fontSize: "max(var(--fs-min), 0.9em)" }}>
              <span style={{ fontWeight: 800, width: 40, flexShrink: 0, color: "var(--bc-muted)" }}>{g.position}</span>
              <span style={{ minWidth: 0 }}>
                <span style={{ fontWeight: 700 }}>{g.name}</span>
                {golferProgress(g, s.status) && (
                  <span style={{ display: "block", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
                    {golferProgress(g, s.status)}
                  </span>
                )}
              </span>
              <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(g.earnings)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Group standings stay up top for groups — "am I winning" needs them.
          Solo, the totals line already says it all, so the table moves down. */}
      {!solo && others.length > 0 && <Standings s={s} title={groupName || "Your group"} />}
      {!solo && s.beating_model != null && s.humans > 1 && (
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 8 }}>
          {s.beating_model} of {s.humans} players {s.status === "final" ? "beat" : "are beating"} the model.
        </div>
      )}

      {/* Layer 3 — the math, on request */}
      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)", color: "var(--bc-text)" }}>
          View scoring details
        </summary>
        <div style={{ marginTop: 8, display: "grid", gap: 10 }}>
          {s.story && live && <div style={{ fontSize: "max(var(--fs-min), 0.88em)" }}>{s.story}</div>}
          {live && me && me.golfers.some(g => g.up_one > 0) && (
            <div>
              <div style={label}>If each golfer moved up one spot</div>
              {me.golfers.filter(g => g.up_one > 0).map(g => (
                <div key={g.name} style={{ display: "flex", fontSize: "max(var(--fs-min), 0.86em)", padding: "2px 0" }}>
                  <span>{g.name}</span>
                  <span style={{ marginLeft: "auto", color: "var(--bc-green)", fontVariantNumeric: "tabular-nums" }}>+{money(g.up_one)}</span>
                </div>
              ))}
            </div>
          )}
          {solo && <Standings s={s} title="You vs. the model" />}
          <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.5 }}>
            {s.status === "final"
              ? "Totals are each golfer's official prize money."
              : "Totals use each golfer's current position on the live leaderboard and the purse's payout table, with tied positions sharing the money. They show where things stand now, not a forecast of where they'll finish."}
            {live && ` Live scores come from DataGolf${s.data_updated_utc ? ` (last update ${clock(s.data_updated_utc)})` : ""}; this page re-checks every 2 minutes during play${checkedAt ? `, last at ${clock(checkedAt)}` : ""}.`}
          </div>
          {s.status === "final" && (
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)" }}>
              Sunday recap card: Friends → Groups → Share recap.
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

function Standings({ s, title }: { s: Slate; title: string }) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, color: "var(--bc-muted)",
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{title}</div>
      {s.lines.map(l => {
        const isMe = l.user_id === s.me_id, isModel = l.user_id === "model", isRival = l.user_id === s.rival?.user_id;
        return (
          <div key={l.user_id} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "5px 0", fontSize: "max(var(--fs-min), 0.88em)",
            borderBottom: "1px solid var(--bc-line)" }}>
            <span style={{ width: 22, fontWeight: 900, color: "var(--bc-muted)" }}>{l.rank}</span>
            <span style={{ fontWeight: 800, color: isMe ? "var(--bc-green)" : "var(--bc-text)" }}>{isMe ? "You" : l.user_name}</span>
            {isModel && <span style={tag("var(--bc-line-hi)", "var(--bc-text)")}>Model</span>}
            {isRival && !isModel && <span style={tag("var(--bc-orange)", "#081f14")}>Rival</span>}
            <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {displaySurnames(l.golfers.map(g => g.name)).join(", ")}
            </span>
            <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(l.total)}</span>
          </div>
        );
      })}
    </div>
  );
}

function tag(bg: string, fg: string): React.CSSProperties {
  return { fontSize: "max(var(--fs-min), 0.7em)", fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase",
    color: fg, background: bg, borderRadius: 3, padding: "1px 5px" };
}

function CollegeCard({ c }: { c: NonNullable<College> }) {
  const me = c.lines.find(l => l.user_id === c.me_id);
  const solo = c.lines.length <= 2 && c.lines.some(l => l.user_id === "model");
  const label: React.CSSProperties = { fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 800, color: "var(--bc-muted)",
    textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 };
  const golferRow = (g: CollegeGolfer, dim = false) => (
    <div key={g.name} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "6px 0",
      borderBottom: "1px solid var(--bc-line)", fontSize: "max(var(--fs-min), 0.9em)", opacity: dim ? 0.75 : 1 }}>
      <span style={{ width: 40, flexShrink: 0, fontWeight: 800, color: "var(--bc-muted)" }}>{g.position}</span>
      <span style={{ minWidth: 0 }}>
        <span style={{ fontWeight: 700 }}>{g.name}</span>
        {golferProgress(g, c.status) && (
          <span style={{ display: "block", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>{golferProgress(g, c.status)}</span>
        )}
      </span>
      <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(g.earnings)}</span>
    </div>
  );
  const race = (
    <div style={{ marginTop: 14 }}>
      <div style={label}>School race</div>
      {c.lines.map(l => (
        <div key={l.user_id} style={{ display: "flex", gap: 10, fontSize: "max(var(--fs-min), 0.88em)", padding: "5px 0",
          borderBottom: "1px solid var(--bc-line)" }}>
          <span style={{ width: 22, fontWeight: 900, color: "var(--bc-muted)" }}>{l.rank}</span>
          <SchoolBadge school={l.school} size={0.9} />
          <span style={{ fontWeight: 800, color: l.user_id === c.me_id ? "var(--bc-green)" : "var(--bc-text)" }}>{l.school}</span>
          <span style={{ color: "var(--bc-muted)" }}>{l.user_id === c.me_id ? "you" : l.user_id === "model" ? "the model" : l.user_name}</span>
          <span style={{ marginLeft: "auto", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{money(l.total)}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: "max(var(--fs-min), 0.74em)", color: "var(--bc-muted)", fontWeight: 700 }}>College Game · {c.name}</span>
        <StatusTag status={c.status} projected={false} />
      </div>

      {/* Layer 1 — is my school winning? */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "6px 0 4px" }}>
        {me && <SchoolBadge school={me.school} size={1.3} />}
        <div style={{ fontWeight: 900, fontSize: "1.35em", lineHeight: 1.2 }}>{collegeHeadline(c)}</div>
      </div>
      {me && c.lines.length > 1 && <div style={{ fontWeight: 700, fontSize: "max(var(--fs-min), 0.95em)", fontVariantNumeric: "tabular-nums" }}>{collegeTotals(c)}</div>}
      {me && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", marginTop: 2 }}>{moneyNote({ status: c.status } as Slate)}</div>}

      {/* Layer 2 — the two alumni who count */}
      {me && me.counting.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={label}>Your two counting golfers</div>
          {me.counting.map(g => golferRow(g))}
        </div>
      )}

      {!solo && c.lines.length > 1 && race}

      {/* Layer 3 — the math, on request */}
      {me && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "max(var(--fs-min), 0.88em)", color: "var(--bc-text)" }}>
            View scoring details
          </summary>
          <div style={{ marginTop: 8, display: "grid", gap: 10 }}>
            {c.story && c.status === "live" && <div style={{ fontSize: "max(var(--fs-min), 0.88em)" }}>{c.story}</div>}
            {(me.bench ?? []).length > 0 && (
              <div>
                <div style={label}>Next in line (don&apos;t count yet)</div>
                {(me.bench ?? []).map(g => golferRow(g, true))}
              </div>
            )}
            {solo && c.lines.length > 1 && race}
            <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.5 }}>
              A school scores its two best-paid alumni in the field. {c.status === "final"
                ? "Totals are official prize money."
                : "Totals use current leaderboard positions and the purse's payout table — where things stand now, not a forecast."}
            </div>
          </div>
        </details>
      )}
    </div>
  );
}
