"use client";

import { useState } from "react";
import { WeatherDay } from "@/lib/api";
import styles from "./WeatherStrip.module.css";

// credit: a source whose licence requires attribution (Open-Meteo: CC BY 4.0).
type Props = { days: WeatherDay[]; savedAt?: string; credit?: { label: string; href: string } };

// Condition code → short label + color
function conditionMeta(code: string): { label: string; color: string; icon: string } {
  if (code.includes("SUNNY"))          return { label: "Sunny",         color: "var(--bc-yellow)", icon: "◎" };
  if (code.includes("PARTLY_CLOUDY")) return { label: "Partly Cloudy", color: "var(--bc-blue)", icon: "◑" };
  if (code.includes("CLOUDY"))         return { label: "Cloudy",        color: "var(--bc-muted)", icon: "●" };
  if (code.includes("RAIN") || code.includes("SHOWER")) return { label: "Rain", color: "var(--bc-yellow)", icon: "↓" };
  if (code.includes("THUNDER") || code.includes("STORM")) return { label: "Storms", color: "var(--bc-red)", icon: "!" };
  if (code.includes("SNOW"))           return { label: "Snow",          color: "var(--bc-text)", icon: "*" };
  if (code.includes("FOG"))            return { label: "Foggy",         color: "var(--bc-muted)", icon: "~" };
  return                                      { label: "Mixed",          color: "var(--bc-muted)", icon: "◌" };
}

// Wind direction → short compass label
function windLabel(dir: string): string {
  const map: Record<string, string> = {
    "North":       "N",  "North West":   "NW", "North East":   "NE",
    "South":       "S",  "South West":   "SW", "South East":   "SE",
    "East":        "E",  "West":         "W",
  };
  return map[dir] ?? dir;
}

// Precipitation % → color
function precipColor(pct: string): string {
  const n = parseInt(pct);
  if (isNaN(n)) return "var(--bc-muted)";
  if (n >= 50) return "var(--bc-yellow)";
  if (n >= 25) return "var(--bc-blue)";
  return "var(--bc-muted)";
}

function DayCard({ day }: { day: WeatherDay }) {
  const { label, color, icon } = conditionMeta(day.condition);
  const pColor = precipColor(day.precip_pct);
  const windNum = parseInt(day.wind_mph);
  const windColor = windNum >= 15 ? "var(--warning)" : windNum >= 10 ? "var(--bc-muted)" : "var(--bc-muted)";

  return (
    <div style={{
      background: "var(--bc-panel)", border: "1px solid var(--bc-line)", borderRadius: 8,
      padding: "10px 14px", flex: "1 1 100px", minWidth: 90,
    }}>
      {/* Day label */}
      <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", fontWeight: 700, color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
        {day.day}
      </div>

      {/* Condition icon + label */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: "1.1em", color, lineHeight: 1 }}>{icon}</span>
        <span style={{ fontSize: "max(var(--fs-min), 0.72em)", color, fontWeight: 600 }}>{label}</span>
      </div>

      {/* Temp range */}
      <div style={{ fontSize: "max(var(--fs-min), 0.82em)", fontWeight: 700, color: "var(--bc-text)", marginBottom: 4 }}>
        {day.high_f}
        <span style={{ color: "var(--bc-muted)", fontWeight: 400, fontSize: "max(var(--fs-min-xs), 0.85em)" }}>
          {" "}/{" "}{day.low_f}
        </span>
      </div>

      {/* Wind */}
      <div style={{ fontSize: "max(var(--fs-min-xs), 0.68em)", color: windColor, marginBottom: 2 }}>
        {day.wind_mph} mph {windLabel(day.wind_dir)}
      </div>

      {/* Precip */}
      <div style={{ fontSize: "max(var(--fs-min-xs), 0.65em)", color: pColor }}>
        {day.precip_pct} rain
      </div>
    </div>
  );
}

export default function WeatherStrip({ days, savedAt, credit }: Props) {
  const [open, setOpen] = useState(false);   // collapsed by default, phone and desktop
  if (!days.length) return null;

  // Collapsed summary: the week's range in one line ("Thu–Sun · 74–80°F · wind 3–12 mph").
  const nums = (k: "high_f" | "wind_mph") => days.map(d => parseInt(String(d[k]))).filter(n => !isNaN(n));
  const range = (xs: number[], unit: string) => xs.length
    ? `${Math.min(...xs)}${Math.min(...xs) === Math.max(...xs) ? "" : `–${Math.max(...xs)}`}${unit}` : "";
  const summary = [`${days[0].day}–${days[days.length - 1].day}`,
    range(nums("high_f"), "°F"), range(nums("wind_mph"), " mph wind")].filter(Boolean).join(" · ");

  return (
    <div style={{ marginBottom: 20 }}>
      <button type="button" className={styles.toggle} aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span>Forecast: {summary}</span>
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      <div className={open ? undefined : styles.heading} style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", color: "var(--bc-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
        Round Week Forecast
        {savedAt && <span style={{ marginLeft: 10, color: "var(--bc-line)" }}>· {savedAt.slice(0, 10)}</span>}
      </div>
      <div className={`${styles.days} ${open ? styles.open : ""}`}>
        {days.map(d => <DayCard key={d.day} day={d} />)}
      </div>
      {credit && (
        <div style={{ fontSize: "max(var(--fs-min-xs), 0.62em)", color: "var(--bc-muted)", marginTop: 6 }}>
          Weather data by <a href={credit.href} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "underline" }}>{credit.label}</a> (CC BY 4.0)
        </div>
      )}
    </div>
  );
}
