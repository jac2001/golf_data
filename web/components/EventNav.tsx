"use client";

/**
 * EventNav — the one event navigator every game uses (Let It Ride,
 * Round, Fade, College): PGA / DP World Tour pills when the list spans
 * both tours, prev/next through one tour's events in date order, and a
 * scroll-snap strip grouped Completed | This week | Upcoming that keeps
 * the selection centered. Selecting is the caller's job (onPick).
 */
import React, { useEffect, useRef } from "react";

export type NavEvent = {
  tournament_id: string; name: string; tour: "pga" | "euro"; start_date: string;
  status: "open" | "awaiting" | "live" | "completed" | "upcoming";
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
  locked: boolean; finished: boolean; field_available?: boolean }[]): NavEvent[] {
  return evs.map(e => ({
    tournament_id: e.tournament_id, name: e.name, tour: e.tour === "euro" ? "euro" : "pga",
    start_date: e.start_date,
    // "Picks open" only when there's a field to pick from.
    status: e.finished ? "completed" : e.locked ? "live" : e.field_available === false ? "awaiting" : "open",
  }));
}

/** Where to land: an open slate, else a live one, else the latest final. */
export function landingEvent(evs: NavEvent[]): NavEvent | undefined {
  return evs.find(w => w.status === "open") ?? evs.find(w => w.status === "live")
    ?? evs.find(w => w.status === "awaiting")
    ?? [...evs].filter(w => w.status === "completed").sort((a, b) => b.start_date.localeCompare(a.start_date))[0]
    ?? evs[0];
}

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
  background: on ? "var(--bc-raised)" : "transparent", color: on ? "var(--bc-text)" : "var(--bc-muted)",
  border: `1px solid ${on ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
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

  const selRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    selRef.current?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [selected]);

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
        style={{ ...btn(false), padding: "7px 11px", opacity: target ? 1 : 0.35 }}>
        {dir < 0 ? "‹" : "›"}
      </button>
    );
  };

  return (
    <div style={{ marginBottom: 14 }}>
      {tours.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {(["pga", "euro"] as const).filter(t => tours.includes(t)).map(t => (
            <button key={t} onClick={() => switchTour(t)} style={btn(tour === t)}>
              {t === "euro" ? "DP World Tour" : "PGA Tour"}
            </button>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        {arrow(-1)}
        <div style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
          <div style={{ fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {cur?.name ?? "—"}
          </div>
          {cur && (
            <div style={{ fontSize: "max(var(--fs-min), 0.72em)", fontWeight: 700, color: STATUS_COLOR[cur.status] }}>
              {STATUS_LABEL[cur.status]} · {shortDate(cur.start_date)}
            </div>
          )}
        </div>
        {arrow(1)}
      </div>
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
                background: on ? "var(--bc-raised)" : "var(--bc-card)",
                border: `1px solid ${on ? "var(--bc-line-hi)" : "var(--bc-line)"}`,
              }}>
                <div style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", fontWeight: 700, color: STATUS_COLOR[e.status] }}>
                  {shortDate(e.start_date)} · {STATUS_LABEL[e.status]}
                  {starred[e.tournament_id] ? <span style={{ color: "var(--bc-yellow)", marginLeft: 4 }}><Star /></span> : null}
                </div>
                <div style={{ fontSize: "max(var(--fs-min), 0.78em)", fontWeight: 700, color: on ? "var(--bc-text)" : "var(--bc-muted)",
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 150 }}>
                  {e.name}
                </div>
              </button>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
