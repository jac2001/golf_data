"use client";

/**
 * The College Game: claim a school, best two alumni count.
 * Split out of app/friends/page.tsx unchanged.
 */

import { useEffect, useState } from "react";
import SchoolBadge from "@/components/SchoolBadge";
import LockCountdown from "@/components/LockCountdown";
import EventNav, { favoriteTour, fromOpenEvents, landingEvent } from "@/components/EventNav";
import PickConfirm, { buildConfirm } from "@/components/PickConfirm";
import { WhosInCard } from "./WhosInCard";
import type { ConfirmCopy } from "@/lib/pickConfirm";
import { OpenEvent } from "@/lib/api";
import { EventInfo, card, cell, hdr, lastName, money, openPlusPast, useApi } from "./shared";
import { useActiveGroup } from "./ActiveGroup";import Avatar, { useAvatars } from "@/components/Avatar";


// ── College Game ─────────────────────────────────────────────────────────────

export type CollegeSchool = { school: string; players: string[] };
export type CollegeBoardRow = { user_id: string; user_name: string; school: string;
  total: number | null; counted: { player: string; earnings: number; position: string }[] };

export function CollegeTab() {
  const av = useAvatars();   // members' photos (components/Avatar.tsx)
  const api = useApi();
  const { groupQuery } = useActiveGroup();
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState("");
  const [event, setEvent] = useState<(EventInfo & { finished?: boolean }) | null>(null);
  const [schools, setSchools] = useState<CollegeSchool[]>([]);
  const [pick, setPick] = useState<string | null>(null);
  const [board, setBoard] = useState<{ settled: boolean; projected: boolean; standings: CollegeBoardRow[]; me: string } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    openPlusPast(api, "college").then(all => {
      const evs = all.filter(e => e.tour !== "euro");
      setEvents(evs);
      const first = landingEvent(fromOpenEvents(evs), favoriteTour());
      if (first) setSelected(first.tournament_id);
      else setLoading(false);
    }).catch(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (!selected) return;
    setLoading(true); setErr(""); setBoard(null);
    api(`/api/friends/collegepicks?tournament_id=${encodeURIComponent(selected)}`)
      .then(d => {
        const ev = d.event as EventInfo & { finished?: boolean };
        setEvent(ev);
        setSchools((d.schools as CollegeSchool[]) ?? []);
        setPick((d.pick as string | null) ?? null);
        if (ev.locked) {
          api(`/api/friends/collegeboard?tournament_id=${encodeURIComponent(selected)}${groupQuery}`)
            .then(b => setBoard(b as never)).catch(() => {});
        }
      })
      .catch(e => setErr(`Could not load the college game — ${e.message}`))
      .finally(() => setLoading(false));
  }, [api, selected, groupQuery]);

  const [confirm, setConfirm] = useState<ConfirmCopy | null>(null);
  async function choose(school: string) {
    setErr("");
    try {
      const d = await api("/api/friends/collegepicks", {
        method: pick === school ? "DELETE" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pick === school ? { tournament_id: selected } : { tournament_id: selected, school }),
      });
      setPick((d.pick as string | null) ?? null);
      if (d.pick && event?.startDate) {
        setConfirm(await buildConfirm({ picked: [String(d.pick)], needed: 1, startDate: event.startDate,
          tour: event.tour === "euro" ? "euro" : "pga" }));
      }
    } catch (e) { setErr((e as Error).message); }
  }

  if (loading) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (!event) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        {err || "No event to claim a school for right now."}
      </p>
    </div>
  );

  return (
    <>
      <PickConfirm copy={confirm} onClose={() => setConfirm(null)} />
      <EventNav events={fromOpenEvents(events)} selected={selected} onPick={setSelected} />

      <div style={card}>
        <div style={{ fontWeight: 800, fontSize: "1.05em" }}>
          {event.name || events.find(e => e.tournament_id === event.tid)?.name || "Loading…"}
        </div>
        {!event.locked && event.startDate && (
          <div style={{ fontSize: "max(var(--fs-min), 0.78em)", marginTop: 3 }}>
            <LockCountdown startDate={event.startDate} tour={event.tour} />
          </div>
        )}
        <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.8em)", marginTop: 2 }}>
          {event.locked
            ? (event.finished ? "Final — graded below." : "Schools are locked — tournament underway.")
            : pick
              ? <>Your school: <SchoolBadge school={pick} /> <strong style={{ color: "var(--bc-text)" }}>{pick}</strong> · best 2 alumni checks count</>
              : "Claim one school before lock · its best 2 finishers score for you"}
        </div>
        {err && <p style={{ color: "var(--bc-red-text)", fontSize: "max(var(--fs-min), 0.84em)", marginTop: 10 }}>{err}</p>}
      </div>

      {board && board.standings.length > 0 && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            School board
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
              best 2 alumni · highest wins{board.projected && !board.settled ? " · estimated payouts if it ended now" : ""}
            </span>
          </div>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <tbody>
              {board.standings.map((r, i) => (
                <tr key={r.user_id} style={{ background: r.user_id === board.me ? "var(--bc-card-hi)" : "transparent" }}>
                  <td style={{ ...cell, fontWeight: 800, color: "var(--bc-muted)", width: 34 }}>{i + 1}</td>
                  <td style={{ ...cell, fontWeight: 700 }}>
                    <Avatar userId={r.user_id} name={r.user_name} url={av[r.user_id]} size={22} />{" "}{r.user_name}
                    {r.user_id === board.me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
                    <div style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min), 0.82em)" }}>
                      <SchoolBadge school={r.school} size={0.9} /> {r.school}{r.counted.length > 0 &&
                        ` — ${r.counted.map(c => `${lastName(c.player)} ${c.position}`).join(", ")}`}
                    </div>
                  </td>
                  <td style={{ ...cell, textAlign: "right", fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
                    {r.total != null ? money(r.total) : "…"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!event.locked && (
        <div style={{ ...card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px 6px", fontWeight: 800 }}>
            Schools in this field
            <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
              {schools.length} with alumni playing
            </span>
          </div>
          {schools.length === 0 && (
            <p style={{ padding: "0 16px 14px", color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)" }}>
              No field (or no college data) for this event yet — check back
              once the field posts.
            </p>
          )}
          <div style={{ maxHeight: 460, overflowY: "auto" }}>
            {schools.map(s => {
              const mine = pick === s.school;
              return (
                <button key={s.school} onClick={() => choose(s.school)} style={{
                  display: "block", width: "100%", textAlign: "left", cursor: "pointer",
                  fontFamily: "inherit", background: mine ? "var(--bc-card-hi)" : "none",
                  border: "none", borderBottom: "1px solid var(--bc-line)", padding: "10px 16px",
                }}>
                  <SchoolBadge school={s.school} />{" "}
                  <span style={{ fontWeight: 800, fontSize: "0.9em",
                    color: mine ? "var(--bc-green)" : "var(--bc-text)" }}>
                    {s.school}{mine && " ✓"}
                  </span>
                  <span style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
                    {s.players.map(lastName).join(" · ")}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {/* Who's in (organizer detail) after your own picks (audit #7). */}
      {event && !event.locked && schools.length > 0 && (
        <WhosInCard game="college" tid={selected} eventName={event.name} startDate={event.startDate}
          tour={event.tour} refreshKey={pick ? 1 : 0} />
      )}

    </>
  );
}

export function CollegeStandings() {
  const av = useAvatars();   // members' photos (components/Avatar.tsx)
  const api = useApi();
  const { groupQuery } = useActiveGroup();
  const [rows, setRows] = useState<{ user_id: string; user_name: string; wins: number; entered: number }[] | null>(null);
  const [me, setMe] = useState("");

  useEffect(() => {
    api(`/api/friends/collegeboard?${groupQuery.slice(1)}`)   // season table, this group
      .then(d => { setRows((d.standings as never) ?? []); setMe((d.me as string) ?? ""); })
      .catch(() => setRows([]));
  }, [api, groupQuery]);

  if (!rows) return <p style={{ color: "var(--bc-muted)" }}>Loading…</p>;
  if (rows.length === 0) return (
    <div style={card}>
      <p style={{ color: "var(--bc-muted)", margin: 0 }}>
        No schools claimed yet — grab yours on the Games tab.
      </p>
    </div>
  );
  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr>
          <th style={hdr}>#</th><th style={hdr}>Player</th>
          <th style={{ ...hdr, textAlign: "right" }}>Event wins</th>
          <th style={{ ...hdr, textAlign: "right" }}>Entered</th>
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.user_id} style={{ background: r.user_id === me ? "var(--bc-card-hi)" : "transparent" }}>
              <td style={{ ...cell, fontWeight: 800, color: "var(--bc-muted)" }}>{i + 1}</td>
              <td style={{ ...cell, fontWeight: 700 }}>
                <Avatar userId={r.user_id} name={r.user_name} url={av[r.user_id]} size={22} />{" "}{r.user_name}
                {r.user_id === me && <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}> · you</span>}
              </td>
              <td style={{ ...cell, textAlign: "right", fontWeight: 800 }}>{r.wins}</td>
              <td style={{ ...cell, textAlign: "right", color: "var(--bc-muted)" }}>{r.entered}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
