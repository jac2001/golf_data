"use client";

import { WeatherDay } from "@/lib/api";

type Props = { days: WeatherDay[]; savedAt?: string };

// Condition code → short label + color
function conditionMeta(code: string): { label: string; color: string; icon: string } {
  if (code.includes("SUNNY"))          return { label: "Sunny",         color: "#f1c40f", icon: "◎" };
  if (code.includes("PARTLY_CLOUDY")) return { label: "Partly Cloudy", color: "#7fb8d4", icon: "◑" };
  if (code.includes("CLOUDY"))         return { label: "Cloudy",        color: "#7f8c8d", icon: "●" };
  if (code.includes("RAIN") || code.includes("SHOWER")) return { label: "Rain", color: "#4cb8ff", icon: "↓" };
  if (code.includes("THUNDER") || code.includes("STORM")) return { label: "Storms", color: "#e74c3c", icon: "!" };
  if (code.includes("SNOW"))           return { label: "Snow",          color: "#dde6f5", icon: "*" };
  if (code.includes("FOG"))            return { label: "Foggy",         color: "#5a7090", icon: "~" };
  return                                      { label: "Mixed",          color: "#8ba0b8", icon: "◌" };
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
  if (isNaN(n)) return "#4a6080";
  if (n >= 50) return "#4cb8ff";
  if (n >= 25) return "#7fb8d4";
  return "#3a5060";
}

function DayCard({ day }: { day: WeatherDay }) {
  const { label, color, icon } = conditionMeta(day.condition);
  const pColor = precipColor(day.precip_pct);
  const windNum = parseInt(day.wind_mph);
  const windColor = windNum >= 15 ? "#f39c12" : windNum >= 10 ? "#8ba0b8" : "#4a6080";

  return (
    <div style={{
      background: "#0d1a30", border: "1px solid #1e3a5f", borderRadius: 8,
      padding: "10px 14px", flex: "1 1 100px", minWidth: 90,
    }}>
      {/* Day label */}
      <div style={{ fontSize: "0.68em", fontWeight: 700, color: "#5a7090", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
        {day.day}
      </div>

      {/* Condition icon + label */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: "1.1em", color, lineHeight: 1 }}>{icon}</span>
        <span style={{ fontSize: "0.72em", color, fontWeight: 600 }}>{label}</span>
      </div>

      {/* Temp range */}
      <div style={{ fontSize: "0.82em", fontWeight: 700, color: "#dde6f5", marginBottom: 4 }}>
        {day.high_f}
        <span style={{ color: "#4a6080", fontWeight: 400, fontSize: "0.85em" }}>
          {" "}/{" "}{day.low_f}
        </span>
      </div>

      {/* Wind */}
      <div style={{ fontSize: "0.68em", color: windColor, marginBottom: 2 }}>
        {day.wind_mph} mph {windLabel(day.wind_dir)}
      </div>

      {/* Precip */}
      <div style={{ fontSize: "0.65em", color: pColor }}>
        {day.precip_pct} rain
      </div>
    </div>
  );
}

export default function WeatherStrip({ days, savedAt }: Props) {
  if (!days.length) return null;

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: "0.62em", color: "#3a5060", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
        Round Week Forecast
        {savedAt && <span style={{ marginLeft: 10, color: "#2a3a50" }}>· {savedAt.slice(0, 10)}</span>}
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {days.map(d => <DayCard key={d.day} day={d} />)}
      </div>
    </div>
  );
}
