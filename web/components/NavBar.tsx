"use client";

/**
 * NavBar — Broadcast design system, zone-aware.
 * Public zone: fairway green bar, 3px yellow rule, yellow active tab.
 * League zone (/league/*, plus legacy /fantasy /mypicks): charcoal bar,
 * green rule — so you always know which side of the site you're on.
 */

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import SettingsModal from "@/components/SettingsModal";
import { Show, UserButton } from "@clerk/nextjs";

// Order follows the golf week: research (Forecast, Board) → watch (Live) →
// reference (Players) → trust (How It Works) → utility (Assistant).
// /history stays routable but leaves the nav: its tabs now live on the
// Betting Board (Ledger, My Slip) and in How It Works (Results).
const PUBLIC_LINKS = [
  { href: "/",            label: "Home", exact: true },
  { href: "/predictions", label: "This Week" },
  { href: "/betting",     label: "Betting Board" },
  { href: "/live",        label: "Live" },
  { href: "/players",     label: "Players" },
  { href: "/friends",     label: "Friends Game" },
  { href: "/methodology", label: "How It Works" },
  { href: "/assistant",   label: "Assistant" },
];

// Reserved order for the League zone: Tuesday Call, Season Plan, Star Budget,
// Miss Ledger, Assistant. Season Plan and Miss Ledger get their slots when
// their routes land — insert them here in that order, don't append.
const LEAGUE_LINKS = [
  { href: "/fantasy",   label: "The Tuesday Call" },
  { href: "/mypicks",   label: "Star Budget" },
  { href: "/assistant", label: "Assistant" },
];

const LEAGUE_PREFIXES = ["/fantasy", "/mypicks", "/league"];

export default function NavBar() {
  const pathname                        = usePathname();
  const [showSettings, setShowSettings] = useState(false);
  const [menuOpen, setMenuOpen]         = useState(false);

  const inLeague = LEAGUE_PREFIXES.some(p => pathname.startsWith(p));
  const links    = inLeague ? LEAGUE_LINKS : PUBLIC_LINKS;

  const bar     = inLeague ? "var(--lg-panel)" : "var(--bc-panel)";
  const rule    = inLeague ? "var(--lg-accent)" : "var(--bc-yellow)";
  const muted   = inLeague ? "var(--lg-muted)" : "var(--bc-muted)";
  const text    = inLeague ? "var(--lg-text)" : "var(--bc-text)";
  const activeBg = rule;
  const activeFg = inLeague ? "#0a0d10" : "#081f14";

  const isActive = (l: { href: string; exact?: boolean }) =>
    l.exact ? pathname === l.href : pathname.startsWith(l.href);

  function handleNavClick() { setMenuOpen(false); }

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
        <Link href="/" onClick={handleNavClick} style={{
          display: "flex", alignItems: "center", gap: 10,
          fontWeight: 900, fontSize: "1.15em",
          fontStretch: "115%", textTransform: "uppercase",
          letterSpacing: "0.02em", color: text,
          marginRight: 18, flexShrink: 0,
        }}>
          Golf&nbsp;Edge
          {inLeague && (
            <span style={{
              background: "var(--lg-accent)", color: "#0a0d10",
              fontSize: "0.55em", fontWeight: 900, letterSpacing: "0.08em",
              padding: "3px 8px", borderRadius: 3,
            }}>
              My League
            </span>
          )}
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
            </Link>
          ))}
        </div>

        {/* Right controls */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          {/* Zone switch */}
          <Link href={inLeague ? "/" : "/fantasy"} onClick={handleNavClick} style={{
            ...(inLeague
              ? { border: "1px solid var(--lg-line)", color: "var(--lg-muted)", background: "transparent" }
              : { background: "var(--bc-yellow)", color: "#081f14" }),
            fontWeight: 900, fontSize: "0.72em",
            textTransform: "uppercase", letterSpacing: "0.05em",
            padding: "9px 14px", borderRadius: 4,
          }}>
            {inLeague ? "← Public site" : "My League"}
          </Link>

          {/* Auth: avatar menu when signed in, quiet link when not */}
          <Show when="signed-in">
            <UserButton />
          </Show>
          <Show when="signed-out">
            <Link href="/sign-in" style={{
              border: `1px solid ${inLeague ? "var(--lg-line)" : "var(--bc-line)"}`,
              color: muted, fontWeight: 700, fontSize: "0.72em",
              textTransform: "uppercase", letterSpacing: "0.05em",
              padding: "8px 12px", borderRadius: 4,
            }}>
              Sign in
            </Link>
          </Show>

          {/* League zone keeps the dashboard alert modal; the public
              site's gear goes to the account settings page. */}
          {inLeague ? (
            <button
              onClick={() => setShowSettings(true)}
              title="Dashboard settings"
              style={{
                background: "none", border: "none",
                color: muted, cursor: "pointer",
                fontSize: "1.1em", padding: "6px 8px",
                lineHeight: 1, borderRadius: 6,
              }}
            >
              ⚙
            </button>
          ) : (
            <Show when="signed-in">
              <Link href="/settings" title="Settings" style={{
                color: muted, fontSize: "1.1em", padding: "6px 8px",
                lineHeight: 1, borderRadius: 6,
              }}>
                ⚙
              </Link>
            </Show>
          )}

          <button
            className="mobile-only"
            onClick={() => setMenuOpen(o => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            style={{
              background: "none", border: "none",
              color: text, cursor: "pointer",
              padding: "6px 8px", borderRadius: 6,
              fontSize: "1.2em", lineHeight: 1,
            }}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </nav>

      {/* Mobile drawer */}
      {menuOpen && (
        <div
          className="mobile-only"
          style={{
            position: "fixed", top: 56, left: 0, right: 0,
            background: bar,
            borderBottom: `1px solid ${inLeague ? "var(--lg-line)" : "var(--bc-line)"}`,
            zIndex: 199,
            padding: "8px 0 16px",
          }}
        >
          {links.map(l => (
            <Link
              key={l.href + l.label}
              href={l.href}
              onClick={handleNavClick}
              style={{
                display: "block",
                padding: "12px 24px",
                color:      isActive(l) ? rule : text,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                fontSize:   "0.85em",
                borderLeft: isActive(l) ? `3px solid ${rule}` : "3px solid transparent",
              }}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}

      {menuOpen && (
        <div
          className="mobile-only"
          onClick={() => setMenuOpen(false)}
          style={{
            position: "fixed", inset: 0, top: 56,
            zIndex: 198,
            background: "rgba(0,0,0,0.4)",
          }}
        />
      )}

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </>
  );
}
