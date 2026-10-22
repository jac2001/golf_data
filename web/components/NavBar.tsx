"use client";

/**
 * NavBar — Broadcast design system, zone-aware.
 * Public zone: fairway green bar, 3px yellow rule, yellow active tab.
 * League zone (/league/*, plus legacy /fantasy /mypicks): charcoal bar,
 * green rule — so you always know which side of the site you're on.
 * Phones: links live in the bottom tab bar (BottomNav), not a hamburger.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Show, UserButton, useAuth } from "@clerk/nextjs";
import { useLiveEvents } from "@/lib/useLiveEvents";

// Desktop: the game first (review item 14). Four links up front; the rest
// under Explore. Phones use the bottom tab bar (BottomNav), unchanged.
// /history stays routable but leaves the nav: its tabs now live on the
// Betting Board (Ledger) and in How It Works (Results).
type NavLink = { href: string; label: string; exact?: boolean; live?: boolean };

const PUBLIC_LINKS: NavLink[] = [
  { href: "/",            label: "Home", exact: true },
  { href: "/friends",     label: "Friends Game" },
  { href: "/match",       label: "Match Center" },
  { href: "/predictions", label: "This Week" },
];
const EXPLORE_LINKS: NavLink[] = [
  { href: "/betting",     label: "Betting Board" },
  { href: "/live",        label: "Live" },
  { href: "/players",     label: "Players" },
  { href: "/how-to-play", label: "How to Play" },
  { href: "/assistant",   label: "Assistant" },
];

export default function NavBar() {
  const pathname                        = usePathname();

  const { isSignedIn }                  = useAuth();
  const liveEvents                      = useLiveEvents();

  // Tournament weekend + signed in: Match Center moves up next to Home and
  // carries a live dot. Off-weeks the order is the research-first one above.
  const matchFirst = !!isSignedIn && liveEvents.length > 0;
  const links: NavLink[] = matchFirst
    ? [PUBLIC_LINKS[0], { ...PUBLIC_LINKS.find(l => l.href === "/match")!, live: true },
       ...PUBLIC_LINKS.slice(1).filter(l => l.href !== "/match")]
    : PUBLIC_LINKS;

  const bar     = "var(--bc-panel)";
  const rule    = "var(--bc-yellow-fill)";  // a surface: the nav rule and active tab
  const muted   = "var(--bc-muted)";
  const text    = "var(--bc-text)";
  const activeBg = rule;
  const activeFg = "#081f14";

  const isActive = (l: { href: string; exact?: boolean }) =>
    l.exact ? pathname === l.href : pathname.startsWith(l.href);

  // Explore menu: closes on Escape, an outside click, or navigating.
  const [explore, setExplore] = useState(false);
  const exploreRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => { setExplore(false); }, [pathname]);
  useEffect(() => {
    if (!explore) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExplore(false); };
    const onDown = (e: MouseEvent) => { if (!exploreRef.current?.contains(e.target as Node)) setExplore(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [explore]);
  const exploreActive = EXPLORE_LINKS.some(isActive);

  return (
    <>
      <nav style={{
        background: bar,
        borderBottom: `3px solid ${rule}`,
        padding: "0 20px",
        display: "flex",
        alignItems: "stretch",
        height: 56,
        position: "sticky",
        top: 0,
        zIndex: 200,
      }}>
        {/* Wordmark */}
        <Link href="/" style={{
          display: "flex", alignItems: "center", gap: 10,
          fontWeight: 900, fontSize: "1.15em",
          fontStretch: "115%", textTransform: "uppercase",
          letterSpacing: "0.02em", color: text,
          marginRight: 18, flexShrink: 0,
        }}>
          Golf&nbsp;Edge
        </Link>

        {/* Desktop links */}
        <div className="mobile-hidden" style={{ display: "flex", gap: 2, flex: 1, alignItems: "stretch" }}>
          {links.map(l => (
            <Link key={l.href + l.label} href={l.href} style={{
              display: "flex", alignItems: "center",
              padding: "0 12px",
              color:      isActive(l) ? activeFg : muted,
              background: isActive(l) ? activeBg : "transparent",
              fontSize:   "0.8em",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              whiteSpace: "nowrap",
              transition: "color 0.15s, background 0.15s",
            }}>
              {l.label}
              {l.live && <span aria-label="live" style={{ width: 7, height: 7, borderRadius: "50%",
                background: "var(--bc-green)", marginLeft: 7, flexShrink: 0 }} />}
            </Link>
          ))}
          <div ref={exploreRef} style={{ position: "relative", display: "flex", alignItems: "stretch" }}>
            <button onClick={() => setExplore(o => !o)} aria-expanded={explore} aria-haspopup="menu" style={{
              display: "flex", alignItems: "center", gap: 6, padding: "0 12px", cursor: "pointer",
              fontFamily: "inherit", border: "none", fontSize: "0.8em", fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.06em", whiteSpace: "nowrap",
              color: exploreActive ? activeFg : muted, background: exploreActive ? activeBg : "transparent",
            }}>
              Explore
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
                strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
            {explore && (
              <div role="menu" style={{ position: "absolute", top: "100%", left: 0, minWidth: 200, zIndex: 210,
                background: bar, border: "1px solid var(--bc-line-hi)", borderRadius: "0 0 8px 8px", padding: "6px 0",
                boxShadow: "0 8px 24px rgba(0,0,0,0.45)" }}>
                {EXPLORE_LINKS.map(l => (
                  <Link key={l.href} href={l.href} role="menuitem" style={{ display: "block", padding: "10px 16px",
                    color: isActive(l) ? rule : text, fontWeight: 700, fontSize: "0.85em",
                    textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    {l.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right controls */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          

          {/* Auth: avatar menu when signed in, quiet link when not */}
          <Show when="signed-in">
            <UserButton />
          </Show>
          <Show when="signed-out">
            <Link href="/sign-in" style={{
              border: `1px solid var(--bc-line)`,
              color: muted, fontWeight: 700, fontSize: "max(var(--fs-min), 0.72em)",
              textTransform: "uppercase", letterSpacing: "0.05em",
              padding: "8px 12px", borderRadius: 4,
            }}>
              Sign in
            </Link>
          </Show>

                      <Show when="signed-in">
              <Link href="/settings" title="Settings" style={{
                color: muted, fontSize: "1.1em", padding: "6px 8px",
                lineHeight: 1, borderRadius: 6,
              }}>
                ⚙
              </Link>
            </Show>

        </div>
      </nav>

    </>
  );
}
