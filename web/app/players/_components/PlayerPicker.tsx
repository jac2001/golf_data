"use client";

/** Player search box and This Week's field browser, used by Profiles and Head-to-Head.
 *  Split out of app/players/page.tsx (Players audit #24, Oct 22). */

import React, { useState, useEffect } from "react";
import { OpenEvent, getEventField, getOpenEvents } from "@/lib/api";
import { BORDER, CARD_BG, GOLD, MUTED, TEXT } from "./shared";


// ── Player select helper (reused by both tabs) ────────────────────────────────

export function PlayerSelect({
  players, value, onChange, id, placeholder,
}: {
  players: string[]; value: string; onChange: (v: string) => void;
  id: string; placeholder?: string;
}) {
  const [inputVal, setInputVal] = useState(value);

  useEffect(() => { setInputVal(value); }, [value]);

  return (
    <div style={{ position: "relative" }}>
      <input
        list={id + "-list"}
        value={inputVal}
        onChange={e => setInputVal(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter") {
            const q = inputVal.trim().toLowerCase();
            if (!q) return;
            const match = players.find(p => p.toLowerCase() === q)
              ?? players.find(p => p.toLowerCase().includes(q));
            if (match) { onChange(match); setInputVal(match); }
          }
        }}
        onBlur={() => {
          const match = players.find(p => p.toLowerCase() === inputVal.toLowerCase());
          if (match) onChange(match);
          else setInputVal(value);
        }}
        placeholder={placeholder ?? "Search player…"}
        style={{
          width: "100%", padding: "10px 14px", borderRadius: 8, fontSize: "0.9em",
          background: CARD_BG, border: `1px solid ${BORDER}`, color: TEXT,
          outline: "none", boxSizing: "border-box",
        }}
      />
      <datalist id={id + "-list"}>
        {players.map(p => <option key={p} value={p} />)}
      </datalist>
    </div>
  );
}


// ── Field browser ─────────────────────────────────────────────────────────────

/** Browse this week's fields instead of guessing names into the search:
 *  one chip per open event, tap a player to open their profile. */
export function FieldBrowser({ onPick }: { onPick: (name: string) => void }) {
  const [events, setEvents] = useState<OpenEvent[]>([]);
  const [selected, setSelected] = useState("");
  const [field, setField] = useState<string[] | null>(null);

  useEffect(() => {
    getOpenEvents().then(d => {
      const evs = (d.events ?? []).filter(e => !e.finished);
      setEvents(evs);
      if (evs[0]) setSelected(evs[0].tournament_id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    setField(null);
    getEventField(selected).then(d => setField(d.players ?? [])).catch(() => setField([]));
  }, [selected]);

  if (events.length === 0) return null;

  return (
    <div style={{ background: CARD_BG, border: `1px solid ${BORDER}`,
      borderRadius: 10, padding: 20, marginTop: 4 }}>
      <div style={{ fontWeight: 800, marginBottom: 10 }}>
        This week&apos;s fields
        <span style={{ color: MUTED, fontWeight: 400, fontSize: "max(var(--fs-min), 0.78em)", marginLeft: 8 }}>
          or search any player above
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {events.map(ev => (
          <button key={ev.tournament_id} onClick={() => setSelected(ev.tournament_id)} style={{
            cursor: "pointer", fontFamily: "inherit", fontWeight: 700, fontSize: "max(var(--fs-min), 0.78em)",
            padding: "6px 13px", borderRadius: 5,
            color: selected === ev.tournament_id ? "#081f14" : MUTED,
            background: selected === ev.tournament_id ? GOLD : "transparent",
            border: `1px solid ${selected === ev.tournament_id ? GOLD : BORDER}`,
          }}>
            {ev.name}
            <span style={{ marginLeft: 6, opacity: 0.75 }}>{ev.tour === "euro" ? "DPWT" : "PGA"}</span>
          </button>
        ))}
      </div>
      {field === null && <p style={{ color: MUTED, fontSize: "max(var(--fs-min), 0.85em)", margin: 0 }}>Loading field…</p>}
      {field !== null && field.length === 0 && (
        <p style={{ color: MUTED, fontSize: "max(var(--fs-min), 0.85em)", margin: 0 }}>
          The field for this event hasn&apos;t been published yet — check back
          closer to tournament week.
        </p>
      )}
      {field !== null && field.length > 0 && (
        <div style={{ display: "grid", gap: "4px 14px",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
          {field.map(name => (
            <button key={name} onClick={() => onPick(name)} style={{
              cursor: "pointer", fontFamily: "inherit", textAlign: "left",
              background: "none", border: "none", padding: "3px 0",
              color: TEXT, fontSize: "max(var(--fs-min), 0.86em)",
              borderBottom: "1px dotted transparent",
            }}
            onMouseEnter={e => { (e.target as HTMLElement).style.color = GOLD; }}
            onMouseLeave={e => { (e.target as HTMLElement).style.color = TEXT; }}>
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
