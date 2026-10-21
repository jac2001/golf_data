"use client";

/**
 * CourseFitTab — does this course suit him? (This Week, redesigned Oct 21)
 * =========================================================================
 * One question, one number, plain words. Each golfer gets a verdict from
 * Jack's lib/fitVerdict.ts (DataGolf course fit + course history, strokes
 * per round) and sits in Suits / Neutral / Hurts. "First time here" is a
 * tag, not a group: no history is a different fact from the course hurting
 * him. Record, form and DataGolf's full breakdown open on tap. App tokens
 * only, same cards on phones and desktop.
 */
import { useMemo, useState } from "react";
import Link from "next/link";
import { CourseFitResponse, CourseFitPlayer } from "@/lib/api";
import { fitVerdict, type Verdict } from "@/lib/fitVerdict";
import Term from "@/components/Term";

const pct = (v: number | null | undefined, dp = 1) => v == null ? "—" : `${(v * 100).toFixed(dp)}%`;
const signed = (v: number | null | undefined, dp = 2) => v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(dp)}`;
const tone = (v: number | null | undefined) =>
  v == null || Math.abs(v) < 0.005 ? "var(--bc-muted)" : v > 0 ? "var(--bc-green)" : "var(--bc-red-text)";
const flip = (n: string) => n.includes(",") ? n.split(",").reverse().join(" ").trim() : n;

const GROUPS: { key: Verdict | "none"; title: string; blurb: string; color: string }[] = [
  { key: "suits",   title: "Course suits him", blurb: "Worth at least a tenth of a shot per round to him here.", color: "var(--bc-green)" },
  { key: "neutral", title: "Neutral",          blurb: "The course neither helps nor hurts him much.",           color: "var(--bc-muted)" },
  { key: "hurts",   title: "Course hurts him", blurb: "Costs him at least a tenth of a shot per round here.",    color: "var(--bc-red-text)" },
  { key: "none",    title: "No course-fit data", blurb: "DataGolf has no fit number for these golfers.",         color: "var(--bc-muted)" },
];

// ── What the course rewards ───────────────────────────────────────────────────

const SKILLS = [
  { key: "app"  as const, label: "Approach",     term: "APP",  sg: "sg_app_vs_avg"  as const },
  { key: "ott"  as const, label: "Off the tee",  term: "OTT",  sg: "sg_ott_vs_avg"  as const },
  { key: "arg"  as const, label: "Around green", term: "ARG",  sg: null },
  { key: "putt" as const, label: "Putting",      term: "PUTT", sg: "sg_putt_vs_avg" as const },
];

function CourseProfile({ profile, players }: { profile: CourseFitResponse["course_profile"]; players: CourseFitPlayer[] }) {
  const items = [...SKILLS].sort((a, b) => profile[b.key] - profile[a.key]);
  const top = items[0];
  // Point the abstract bars at real golfers: the field's best at what wins here.
  const best = top.sg
    ? [...players].filter(p => p[top.sg!] != null).sort((a, b) => (b[top.sg!] ?? 0) - (a[top.sg!] ?? 0)).slice(0, 3)
    : [];
  return (
    <section style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10, padding: "14px 16px", marginBottom: 16 }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 16, color: "var(--bc-text)" }}>What this course rewards</h3>
      <p style={{ margin: "0 0 12px", fontSize: 14, color: "var(--bc-text)", lineHeight: 1.5 }}>
        <strong>{top.label}</strong> matters most here, then {items[1].label.toLowerCase()}.
        {best.length > 0 && <> Best {top.label.toLowerCase()} players in the field: {best.map(p => flip(p.player_name)).join(", ")}.</>}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {items.map(({ key, label, term }) => {
          const v = profile[key];
          return (
            <div key={key} style={{ display: "grid", gridTemplateColumns: "120px 1fr 40px", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 14, color: "var(--bc-text)" }}><Term term={term}>{label}</Term></span>
              <span style={{ height: 8, background: "var(--bc-card)", borderRadius: 4, overflow: "hidden" }}>
                <span style={{ display: "block", width: `${v * 100}%`, height: "100%", borderRadius: 4,
                  background: key === top.key ? "var(--bc-yellow)" : "var(--bc-green)" }} />
              </span>
              <span style={{ fontSize: 13, color: "var(--bc-muted)", textAlign: "right" }}>{Math.round(v * 100)}%</span>
            </div>
          );
        })}
      </div>
      <p style={{ margin: "10px 0 0", fontSize: 13, color: "var(--bc-muted)" }}>
        Share of what separates players at this course, compared with an average tour event.
      </p>
    </section>
  );
}

// ── One golfer ────────────────────────────────────────────────────────────────

function Detail({ p }: { p: CourseFitPlayer }) {
  const row = (label: React.ReactNode, value: React.ReactNode, color?: string) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 14, padding: "3px 0" }}>
      <span style={{ color: "var(--bc-muted)" }}>{label}</span>
      <span style={{ color: color ?? "var(--bc-text)", fontWeight: 600 }}>{value}</span>
    </div>
  );
  // course_starts is the field with data; has_history and the venue_* /
  // avg_to_par / cut_rate fields came back empty for every Bermuda golfer
  // (Oct 21, roadmap follow-up), so each line shows only when it has a value.
  const starts = p.course_starts ?? 0;
  const top10s = p.venue_starts ? p.venue_top10s : null;
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--bc-line)", display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "4px 24px" }}>
      <div>
        <div style={{ fontSize: 12, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>His record here</div>
        {starts > 0 ? <>
          {row("Starts", starts)}
          {top10s != null && row("Top 10s · wins", `${top10s} · ${p.venue_wins ?? 0}`)}
          {p.avg_to_par != null && row("Average to par", signed(p.avg_to_par, 1))}
          {p.cut_rate != null && row("Made cuts", pct(p.cut_rate, 0))}
          {row("What history adds (DataGolf)", signed(p.dg_hist_adj), tone(p.dg_hist_adj))}
        </> : <div style={{ fontSize: 14, color: "var(--bc-muted)" }}>Hasn&apos;t played here.</div>}
      </div>
      <div>
        <div style={{ fontSize: 12, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
          DataGolf&apos;s view, strokes per round
        </div>
        {row("His skill (baseline)", signed(p.dg_baseline_pred))}
        {row("Recent form", signed(p.dg_timing_adj), tone(p.dg_timing_adj))}
        {row("Course fit", signed(p.dg_fit_adj), tone(p.dg_fit_adj))}
        {row("Course history", signed(p.dg_hist_adj), tone(p.dg_hist_adj))}
        {row("Expected here", signed(p.dg_final_pred))}
      </div>
      <div>
        <div style={{ fontSize: 12, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>
          His game vs the tour
        </div>
        {row(<Term term="OTT">Off the tee</Term>, signed(p.sg_ott_vs_avg), tone(p.sg_ott_vs_avg))}
        {row(<Term term="APP">Approach</Term>, signed(p.sg_app_vs_avg), tone(p.sg_app_vs_avg))}
        {row(<Term term="PUTT">Putting</Term>, signed(p.sg_putt_vs_avg), tone(p.sg_putt_vs_avg))}
        {row("DataGolf win chance", pct(p.dg_win))}
      </div>
    </div>
  );
}

function GolferCard({ p, v, open, onToggle }: {
  p: CourseFitPlayer; v: ReturnType<typeof fitVerdict>; open: boolean; onToggle: () => void;
}) {
  const name = flip(p.player_name);
  const chipColor = v?.verdict === "suits" ? "var(--bc-green)" : v?.verdict === "hurts" ? "var(--bc-red-text)" : "var(--bc-muted)";
  return (
    <div onClick={onToggle} style={{ background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10,
      padding: "10px 12px", cursor: "pointer" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 12, fontWeight: 800, color: "var(--bc-muted)", minWidth: 28 }}>#{p.overall_rank}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <Link href={`/players?player=${encodeURIComponent(name)}`} onClick={e => e.stopPropagation()}
              style={{ color: "var(--bc-text)", fontWeight: 700, textDecoration: "none" }}>{name}</Link>
            {!(p.course_starts ?? 0) && (
              <span style={{ fontSize: 11, color: "var(--bc-muted)", border: "1px solid var(--bc-line-hi)", borderRadius: 4, padding: "0 5px" }}>
                First time here
              </span>
            )}
          </div>
          {v && (
            <div style={{ fontSize: 13, color: chipColor, fontWeight: 700, marginTop: 2 }}>
              {v.verdict === "suits" ? "Suits him" : v.verdict === "hurts" ? "Hurts him" : "Neutral"} · {signed(v.edge)} strokes/round
            </div>
          )}
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ color: "var(--bc-green)", fontWeight: 800 }}>{pct(p.win_prob)}</div>
          <div style={{ color: "var(--bc-muted)", fontSize: 12 }}>top 10 {pct(p.top10_prob, 0)}</div>
        </div>
        <button type="button" aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} details for ${name}`}
          onClick={e => { e.stopPropagation(); onToggle(); }}
          style={{ background: "none", border: "none", color: "var(--bc-muted)", fontFamily: "inherit", fontSize: 12,
            cursor: "pointer", minHeight: 44, minWidth: 44, padding: 0, flexShrink: 0 }}>
          {open ? "Less ▾" : "More ▸"}
        </button>
      </div>
      {open && <Detail p={p} />}
    </div>
  );
}

// ── The tab ───────────────────────────────────────────────────────────────────

export default function CourseFitTab({ data }: { data: CourseFitResponse }) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const graded = useMemo(() => data.players.map(p => {
    let v: ReturnType<typeof fitVerdict> = null;
    try { v = fitVerdict(p.dg_fit_adj, p.dg_hist_adj); } catch { v = null; }   // until Jack's rule lands
    const edge = v?.edge ?? (p.dg_fit_adj == null ? null : p.dg_fit_adj + (p.dg_hist_adj ?? 0));
    return { p, v, edge };
  }), [data.players]);
  const ruled = graded.some(g => g.v);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return graded.filter(g => !q || flip(g.p.player_name).toLowerCase().includes(q))
      .sort((a, b) => (b.edge ?? -Infinity) - (a.edge ?? -Infinity));
  }, [graded, search]);

  const groups = ruled
    ? GROUPS.map(g => ({ ...g, rows: shown.filter(r => (r.v?.verdict ?? "none") === g.key) })).filter(g => g.rows.length)
    : [{ key: "all", title: "Best course fit first", blurb: "DataGolf course fit plus course history, strokes per round.",
         color: "var(--bc-muted)", rows: shown }];

  return (
    <div>
      <CourseProfile profile={data.course_profile} players={data.players} />

      <input placeholder="Search player…" value={search} onChange={e => setSearch(e.target.value)} style={{
        background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 6, color: "var(--bc-text)",
        padding: "8px 12px", fontSize: 14, width: "100%", maxWidth: 320, boxSizing: "border-box", marginBottom: 12, fontFamily: "inherit",
      }} />

      {shown.length === 0 && search.trim() ? (
        <div style={{ padding: "16px", background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10, color: "var(--bc-text)" }}>
          No golfers match &ldquo;{search.trim()}&rdquo;.{" "}
          <button type="button" onClick={() => setSearch("")} style={{ background: "none", border: "none", color: "var(--bc-yellow)",
            fontWeight: 800, cursor: "pointer", font: "inherit", minHeight: 44, padding: 0 }}>Clear search</button>
        </div>
      ) : groups.map(g => (
        <section key={g.key} style={{ marginBottom: 18 }}>
          <h3 style={{ margin: "0 0 2px", fontSize: 15, color: g.color }}>{g.title} <span style={{ color: "var(--bc-muted)", fontWeight: 400 }}>({g.rows.length})</span></h3>
          <p style={{ margin: "0 0 8px", fontSize: 13, color: "var(--bc-muted)" }}>{g.blurb}</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {g.rows.map(({ p, v }) => (
              <GolferCard key={p.player_name} p={p} v={v} open={open === p.player_name}
                onToggle={() => setOpen(o => o === p.player_name ? null : p.player_name)} />
            ))}
          </div>
        </section>
      ))}

      <p style={{ fontSize: 13, color: "var(--bc-muted)", lineHeight: 1.6 }}>
        The verdict adds DataGolf&apos;s course-fit and course-history adjustments, in strokes per round against
        his own baseline. Win and top-10 are our model&apos;s chances. Tap a golfer for his record here and the full breakdown.
      </p>
    </div>
  );
}
