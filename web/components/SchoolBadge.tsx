/**
 * SchoolBadge — a school's monogram in its colors (lib/schoolBadges.ts).
 * Sized in em so it scales with the text it sits beside.
 */
import React from "react";
import { schoolBadge } from "@/lib/schoolBadges";

export default function SchoolBadge({ school, size = 1 }: { school: string; size?: number }) {
  const b = schoolBadge(school);
  return (
    <span aria-hidden title={school} style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      minWidth: `${2.6 * size}em`, height: `${1.7 * size}em`, padding: `0 ${0.35 * size}em`,
      borderRadius: 4, background: b.bg, color: b.fg,
      border: b.known ? "1px solid rgba(255,255,255,0.18)" : "1px solid var(--bc-line-hi)",
      fontWeight: 900, fontSize: `max(var(--fs-min-xs), ${0.72 * size}em)`, letterSpacing: "0.04em",
      lineHeight: 1, verticalAlign: "middle", whiteSpace: "nowrap",
    }}>
      {b.abbr}
    </span>
  );
}
