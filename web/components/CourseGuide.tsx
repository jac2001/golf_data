"use client";

/**
 * CourseGuide — This Week's Course Guide tab (Jack's plan, Oct 21).
 * ===================================================================
 * In order: the course at a glance, three things to watch (Jack's
 * lib/thingsToWatch.ts), scoring (this week only once it exists, history
 * only with its years), the hole-by-hole scorecard (collapsed on phones),
 * then the way to Course Fit. Honest empty states: holes nobody has played
 * yet are "not played", never even par; a missing section says why.
 */
import { useState } from "react";
import { CourseResponse, CourseHole, CourseFitResponse, WeatherDay } from "@/lib/api";
import { thingsToWatch, type Watch } from "@/lib/thingsToWatch";
import { scoringPlayed } from "@/lib/courseScoring";
import CourseCard from "@/components/CourseCard";
import HoleStrip from "@/components/HoleStrip";
import styles from "./CourseGuide.module.css";

const unplayed = (h: CourseHole): CourseHole =>
  ({ ...h, scoring_avg: null, scoring_diff: null, difficulty_rank: null, birdies: null, bogeys: null });

const section = { background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 10,
  padding: "14px 16px", marginBottom: 14 } as const;
const h3 = { margin: "0 0 8px", fontSize: 16, color: "var(--bc-text)" } as const;
const muted = { color: "var(--bc-muted)", fontSize: 13, margin: 0, lineHeight: 1.5 } as const;

export default function CourseGuide({ course, fit, weather, location, onExploreFit }: {
  course: CourseResponse;
  fit: CourseFitResponse | null;
  weather: WeatherDay[];
  location?: string;
  onExploreFit: () => void;
}) {
  const [cardOpen, setCardOpen] = useState(false);   // phones only; desktop always shows it
  const played = scoringPlayed(course.holes);
  const holes = played ? course.holes : course.holes.map(unplayed);
  const count = (par: number) => course.holes.filter(h => h.hole_par === par).length;

  let watch: Watch[] | null = null;
  try {
    watch = thingsToWatch({
      profile: fit?.course_profile ?? null,
      holes: course.holes,
      forecast: weather.map(d => ({ day: d.day, wind_mph: Number.isFinite(parseFloat(d.wind_mph)) ? parseFloat(d.wind_mph) : null })),
      history: course.history?.winning_scores?.length
        ? { years: course.history.winning_scores.map(w => w.year),
            winning_to_par: course.history.winning_scores.map(w => parseInt(String(w.to_par).replace("E", "0"), 10)).filter(Number.isFinite) }
        : null,
    });
  } catch { watch = null; }   // until Jack's thingsToWatch lands, the section stays out

  const hist = course.history;
  return (
    <div>
      {/* 1. At a glance */}
      <section style={section}>
        <h3 style={{ ...h3, fontSize: 18 }}>{course.course_name || "Course"}</h3>
        <p style={{ ...muted, color: "var(--bc-text)", fontSize: 14 }}>
          {[location, course.par != null ? `Par ${course.par}` : null,
            course.yardage != null ? `${course.yardage.toLocaleString()} yards` : null].filter(Boolean).join(" · ")}
        </p>
        {course.holes.length > 0 && (
          <p style={{ ...muted, marginTop: 4 }}>
            {count(3)} par 3s, {count(4)} par 4s, {count(5)} par 5s.
          </p>
        )}
      </section>

      {/* 2. Three things to watch */}
      {watch && (
        <section style={section}>
          <h3 style={h3}>Three things to watch</h3>
          {watch.length === 0 ? (
            <p style={muted}>Not enough data on this course yet to say what to watch.</p>
          ) : (
            <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8 }}>
              {watch.map(w => (
                <li key={w.text} style={{ color: "var(--bc-text)", fontSize: 14, lineHeight: 1.5 }}>
                  {w.text} <span style={{ color: "var(--bc-muted)", fontSize: 12 }}>({w.source})</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}

      {/* 3. Scoring: this week and history kept apart, each with its coverage */}
      <section style={section}>
        <h3 style={h3}>Scoring</h3>
        <p style={muted}>
          <strong style={{ color: "var(--bc-text)" }}>This week:</strong>{" "}
          {played ? "hole-by-hole scoring from the rounds played so far is in the scorecard below."
            : "hole scoring shows up once round 1 is underway."}
        </p>
        <p style={{ ...muted, marginTop: 6 }}>
          <strong style={{ color: "var(--bc-text)" }}>History:</strong>{" "}
          {hist && hist.editions > 0
            ? `based on ${hist.editions} past edition${hist.editions === 1 ? "" : "s"} here (${[...hist.years].sort()[0]}–${[...hist.years].sort().slice(-1)[0]}), shown with the scorecard.`
            : "we don't have past scoring for this course."}
        </p>
      </section>

      {/* 3b. The 18-hole strip */}
      {course.holes.length > 0 && <HoleStrip holes={holes} played={played} />}

      {/* 4. Hole-by-hole, collapsed on phones */}
      {course.holes.length > 0 && (
        <section style={{ marginBottom: 14 }}>
          <button type="button" className={styles.toggle} aria-expanded={cardOpen} onClick={() => setCardOpen(o => !o)}>
            <span>Hole-by-hole scorecard</span>
            <span aria-hidden="true">{cardOpen ? "▾" : "▸"}</span>
          </button>
          <div className={`${styles.card} ${cardOpen ? styles.open : ""}`}>
            <CourseCard data={{ ...course, holes }} />
          </div>
        </section>
      )}

      {/* 5. On to picks research */}
      <button type="button" onClick={onExploreFit} style={{ background: "none", border: "none", padding: 0,
        color: "var(--bc-yellow)", fontWeight: 800, fontSize: 15, cursor: "pointer", fontFamily: "inherit", minHeight: 44 }}>
        Explore course fit: which golfers this course suits →
      </button>
    </div>
  );
}
