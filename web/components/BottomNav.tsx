"use client";

/**
 * BottomNav — the phone tab bar (Home · Play · Matchup · More).
 * ==============================================================
 * Phone widths only (.mobile-only); desktop keeps the top nav. Which tab
 * is lit comes from lib/bottomNav.ts activeTab(); this file only draws.
 * More opens a sheet of the remaining pages (it replaced the hamburger).
 *
 * Height lives in --bottom-nav-h (globals.css) so <main>, the install
 * card and the update toast all clear it, including the iPhone home
 * indicator (env(safe-area-inset-bottom)).
 */

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { MORE_LINKS, TABS, activeTab } from "@/lib/bottomNav";
import type { Tab } from "@/lib/bottomNav";
import { useLiveEvents } from "@/lib/useLiveEvents";

function safeActive(pathname: string): Tab | null {
  try { return activeTab(pathname); } catch { return null; }
}

const ICONS: Record<Tab, React.ReactNode> = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  play: <><path d="M12 3v18" /><path d="M12 4l7 3-7 3" /><circle cx="12" cy="21" r="0.5" /></>,
  matchup: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
  more: <><circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" /></>,
};

export default function BottomNav() {
  const pathname = usePathname();
  const [sheet, setSheet] = useState(false);
  const { isSignedIn } = useAuth();
  const live = useLiveEvents();
  const lit = sheet ? "more" : safeActive(pathname);

  // Navigating anywhere closes the sheet.
  useEffect(() => { setSheet(false); }, [pathname]);

  const tabStyle = (on: boolean): React.CSSProperties => ({
    flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
    gap: 3, height: "100%", position: "relative",
    color: on ? "var(--bc-yellow)" : "var(--bc-muted)",
    fontSize: 11, fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase",
    background: "none", border: "none", fontFamily: "inherit", cursor: "pointer", padding: 0,
  });

  return (
    <>
      {sheet && (
        <div className="mobile-only" onClick={() => setSheet(false)} style={{
          position: "fixed", inset: 0, zIndex: 300, background: "rgba(0,0,0,0.45)",
        }} />
      )}
      {sheet && (
        <div className="mobile-only" role="dialog" aria-label="More pages" style={{
          position: "fixed", left: 0, right: 0, bottom: "var(--bottom-nav-h)", zIndex: 301,
          background: "var(--bc-panel)", borderTop: "1px solid var(--bc-line-hi)",
          borderRadius: "12px 12px 0 0", padding: "8px 0 10px",
        }}>
          {MORE_LINKS.map(l => {
            const on = pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link key={l.href} href={l.href} onClick={() => setSheet(false)} style={{
                display: "block", padding: "14px 24px",
                color: on ? "var(--bc-yellow)" : "var(--bc-text)",
                fontWeight: 700, fontSize: "0.95em",
                borderLeft: `3px solid ${on ? "var(--bc-yellow)" : "transparent"}`,
              }}>{l.label}</Link>
            );
          })}
        </div>
      )}

      <nav className="mobile-only" aria-label="Main" style={{
        position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 302,
        height: "var(--bottom-nav-h)", paddingBottom: "env(safe-area-inset-bottom)",
        background: "var(--bc-panel)", borderTop: "1px solid var(--bc-line)",
      }}>
        <div style={{ display: "flex", height: "var(--bottom-nav-bar)" }}>
          {TABS.map(t => {
            const on = lit === t.tab;
            const icon = (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                {ICONS[t.tab]}
              </svg>
            );
            const dot = t.tab === "matchup" && isSignedIn && live.length > 0 && (
              <span aria-label="live" style={{ position: "absolute", top: 8, left: "calc(50% + 10px)",
                width: 7, height: 7, borderRadius: "50%", background: "var(--bc-green)" }} />
            );
            return t.href === null ? (
              <button key={t.tab} onClick={() => setSheet(s => !s)} aria-expanded={sheet} style={tabStyle(on)}>
                {icon}{t.label}
              </button>
            ) : (
              <Link key={t.tab} href={t.href} aria-current={on ? "page" : undefined}
                onClick={() => setSheet(false)} style={tabStyle(on)}>
                {icon}{t.label}{dot}
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
