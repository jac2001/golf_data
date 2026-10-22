"use client";

/**
 * EventNav — the one event navigator every game uses (Let It Ride,
 * Round, Fade, College): PGA / DP World Tour pills when the list spans
 * both tours, prev/next through one tour's events in date order, and a
 * scroll-snap strip grouped Completed | This week | Upcoming that keeps
 * the selection centered. Selecting is the caller's job (onPick).
 *
 * Closed (the default) it is one bar: the event's name and ONE status line
 * (lib/eventStatus.ts, Jack's eventStatusLine) between prev/next arrows.
 * Tapping the name opens the tour pills and the full strip.
 */
import React, { useEffect, useRef, useState } from "react";
import { eventStatusLine } from "@/lib/eventStatus";
import type { StatusLine } from "@/lib/eventStatus";
import { lockAt } from "@/lib/lockTime";
import { landingEvent, favoriteTour } from "@/lib/landing";

export type NavEvent = {
  tournament_id: string; name: string; tour: "pga" | "euro"; start_date: string;
  status: "open" | "awaiting" | "live" | "completed" | "upcoming";
  /** Round in play while live (from events/open), else null/absent. */
  round?: number | null;
};

const STATUS_LABEL: Record<NavEvent["status"], string> = {
  open: "Picks open", awaiting: "Awaiting field", live: "Live", completed: "Final", upcoming: "Opens soon",
};
const STATUS_COLOR: Record<NavEvent["status"], string> = {
  open: "var(--bc-green)", awaiting: "var(--bc-muted)", live: "var(--bc-green)",
  completed: "var(--bc-muted)", upcoming: "var(--bc-muted)",
};
const shortDate = (d: string) =>
  new Date(`${d.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** events/open rows → NavEvents (the per-event games' source). */
export function fromOpenEvents(evs: { tournament_id: string; name: string; tour: string; start_date: string;
  locked: boolean; finished: boolean; field_available?: boolean; current_round?: number | null }[]): NavEvent[] {
  return evs.map(e => ({
    tournament_id: e.tournament_id, name: e.name, tour: e.tour === "euro" ? "euro" : "pga",
    start_date: e.start_date,
    // "Picks open" only when there's a field to pick from.
    status: e.finished ? "completed" : e.locked ? "live" : e.field_available === false ? "awaiting" : "open",
    round: e.current_round ?? null,
  }));
}

/** Where to land (favorite tour first, PGA by default): see lib/landing.ts. */
export { landingEvent, favoriteTour };

/** A weekly win. Drawn, not an emoji glyph, so it renders identically everywhere. */
export function Star() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" aria-label="weekly win" style={{ verticalAlign: "-1px", marginRight: 2 }}>
      <path fill="currentColor" d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z" />
    </svg>
  );
}

const btn = (on: boolean): React.CSSProperties => ({
  cursor: "pointer", fontFamily: "inherit", fontWeight: 800, fontSize: "max(var(--fs-min), 0.76em)",
  textTransform: "uppercase", letterSpacing: "0.05em", borderRadius: 5, padding: "7px 12px",
  background: on ? "var(--bc-sel-bg)" : "transparent", color: on ? "var(--bc-sel-fg)" : "var(--bc-muted)",
  border: `1px solid ${on ? "var(--bc-sel-line)" : "var(--bc-line)"}`,
});

export default function EventNav({ events, selected, onPick, starred = {} }: {
  events: NavEvent[]; selected: string; onPick: (tid: string) => void;
  starred?: Record<string, unknown>;   // tids that get a star (weekly winners)
}) {
  const sel = events.find(e => e.tournament_id === selected);
  const tours = [...new Set(events.map(e => e.tour))];
  const tour = sel?.tour ?? tours[0] ?? "pga";
  const list = events.filter(e => e.tour === tour).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const idx = list.findIndex(e => e.tournament_id === selected);
  const cur = list[idx];

  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => new Date());
  // The countdown is minutes-precise: re-render once a minute.
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(t);
  }, []);

  const selRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (open) selRef.current?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [selected, open]);

  if (!events.length) return null;

  const weekOut = new Date(Date.now() + 6 * 86_400_000).toISOString().slice(0, 10);
  const group = (e: NavEvent) => e.status === "completed" ? "Completed"
    : e.status === "live" ? "This week"
    : e.start_date <= weekOut ? "This week" : "Upcoming";

  const switchTour = (t: string) => {
    const land = landingEvent(events.filter(e => e.tour === t));
    if (land) onPick(land.tournament_id);
  };
  const arrow = (dir: -1 | 1) => {
    const target = list[idx + dir];
    return (
      <button onClick={() => target && onPick(target.tournament_id)} disabled={!target}
        aria-label={dir < 0 ? "Previous event" : "Next event"}
        style={{ ...btn(false), border: "none", width: 40, height: 44, padding: 0, fontSize: "1.2em", opacity: target ? 1 : 0.35 }}>
        {dir < 0 ? "‹" : "›"}
      </button>
    );
  };

  // Jack's line; if it ever throws, fall back to the plain status label.
  let line: StatusLine | null = null;
  if (cur) {
    try {
      line = eventStatusLine({ status: cur.status, tour: cur.tour, startDate: cur.start_date,
        lockAt: lockAt(cur.start_date, cur.tour), round: cur.round ?? null }, now);
    } catch {
      line = { state: STATUS_LABEL[cur.status], detail: shortDate(cur.start_date), tone: "quiet" };
    }
  }
  const toneColor = (t: StatusLine["tone"]) => t === "quiet" ? "var(--bc-muted)" : "var(--bc-green)";

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, background: "var(--bc-card)",
        border: "1px solid var(--bc-line)", borderRadius: 10, padding: 6 }}>
        {arrow(-1)}
        <button onClick={() => setOpen(o => !o)} aria-expanded={open} aria-label={`${cur?.name ?? "Event"}: show all events`}
          style={{ flex: 1, minWidth: 0, minHeight: 44, background: "transparent", border: "none", cursor: "pointer",
            fontFamily: "inherit", color: "var(--bc-text)", textAlign: "center", padding: "2px 0" }}>
          <div style={{ fontWeight: 900, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {cur?.name ?? "—"}
          </div>
          {line && (
            <div style={{ fontSize: "max(var(--fs-min), 0.8em)", marginTop: 2 }}>
              <span style={{ color: toneColor(line.tone), fontWeight: 800 }}>{line.state}</span>
              {line.detail && <span style={{ color: "var(--bc-muted)" }}> · {line.detail}</span>}
            </div>
          )}
        </button>
        {arrow(1)}
      </div>
      {open && <div style={{ marginTop: 10 }}>
      {tours.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {(["pga", "euro"] as const).filter(t => tours.includes(t)).map(t => (
            <button key={t} onClick={() => switchTour(t)} style={btn(tour === t)}>
              {t === "euro" ? "DP World Tour" : "PGA Tour"}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, overflowX: "auto", scrollSnapType: "x mandatory",
        paddingBottom: 4, WebkitOverflowScrolling: "touch" as never }}>
        {list.map((e, i) => {
          const first = i === 0 || group(list[i - 1]) !== group(e);
          const on = i === idx;
          return (
            <React.Fragment key={e.tournament_id}>
              {first && (
                <span style={{ alignSelf: "center", fontSize: "max(var(--fs-min-xs), 0.62em)", fontWeight: 800, color: "var(--bc-muted)",
                  textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap",
                  marginLeft: i === 0 ? 0 : 8 }}>{group(e)}</span>
              )}
              <button ref={on ? selRef : undefined} onClick={() => onPick(e.tournament_id)} style={{
                scrollSnapAlign: "center", flexShrink: 0, cursor: "pointer", fontFamily: "inherit",
                textAlign: "left", borderRadius: 6, padding: "6px 10px", minWidth: 118,
                background: on ? "var(--bc-sel-bg)" : "var(--bc-card)",
                border: `1px solid ${on ? "var(--bc-sel-line)" : "var(--bc-line)"}`,
              }}>
                <div style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", fontWeight: 700, color: STATUS_COLOR[e.status] }}>
                  {shortDate(e.start_date)} · {STATUS_LABEL[e.status]}
                  {starred[e.tournament_id] ? <span style={{ color: "var(--bc-yellow)", marginLeft: 4 }}><Star /></span> : null}
                </div>
                <div style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700, color: on ? "var(--bc-sel-fg)" : "var(--bc-muted)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 150 }}>
                  {e.name}
                </div>
              </button>
            </React.Fragment>
          );
        })}
      </div>
      </div>}
    </div>
  );
}
