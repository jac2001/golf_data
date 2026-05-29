"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import SettingsModal from "@/components/SettingsModal";

const NAV_LINKS = [
  { href: "/betting",     label: "Value Bets" },
  { href: "/predictions", label: "This Week" },
  { href: "/live",        label: "Live" },
  { href: "/players",     label: "Players" },
  { href: "/mypicks",     label: "My Picks" },
  { href: "/history",     label: "History" },
  { href: "/assistant",   label: "Assistant" },
];

export default function NavBar() {
  const pathname                        = usePathname();
  const [showSettings, setShowSettings] = useState(false);
  const [menuOpen, setMenuOpen]         = useState(false);

  // Close the drawer when navigating
  function handleNavClick() {
    setMenuOpen(false);
  }

  return (
    <>
      {/* ── Nav bar ─────────────────────────────────────────────────────── */}
      <nav style={{
        background: "#0a1220",
        borderBottom: "1px solid #1e3a5f",
        padding: "0 16px",
        display: "flex",
        alignItems: "center",
        height: 52,
        position: "sticky",
        top: 0,
        zIndex: 200,
      }}>
        {/* Logo */}
        <Link href="/" onClick={handleNavClick} style={{
          fontWeight: 800, fontSize: "1.05em",
          color: "#00c44f", letterSpacing: "-0.02em",
          marginRight: 24, flexShrink: 0,
        }}>
          Golf Edge
        </Link>

        {/* Desktop links — hidden on mobile via CSS */}
        <div className="mobile-hidden" style={{ display: "flex", gap: 4, flex: 1 }}>
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname.startsWith(href);
            return (
              <Link key={href} href={href} style={{
                color:      isActive ? "#dde6f5" : "#8ba0b8",
                fontSize:   "0.88em",
                fontWeight: isActive ? 700 : 500,
                padding:    "6px 12px",
                borderRadius: 6,
                background: isActive ? "#1a2537" : "transparent",
                transition: "color 0.15s, background 0.15s",
              }}>
                {label}
              </Link>
            );
          })}
        </div>

        {/* Right-side controls */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
          {/* Settings gear */}
          <button
            onClick={() => setShowSettings(true)}
            title="Settings"
            style={{
              background: "none", border: "none",
              color: "#5a7090", cursor: "pointer",
              fontSize: "1.1em", padding: "6px 8px",
              lineHeight: 1, borderRadius: 6,
            }}
          >
            ⚙
          </button>

          {/* Hamburger — mobile only */}
          <button
            className="mobile-only"
            onClick={() => setMenuOpen(o => !o)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            style={{
              background: "none", border: "none",
              color: "#dde6f5", cursor: "pointer",
              padding: "6px 8px", borderRadius: 6,
              fontSize: "1.2em", lineHeight: 1,
            }}
          >
            {menuOpen ? "✕" : "☰"}
          </button>
        </div>
      </nav>

      {/* ── Mobile drawer ───────────────────────────────────────────────── */}
      {/* Slides open below the nav bar; tapping a link closes it.          */}
      {menuOpen && (
        <div
          className="mobile-only"
          style={{
            position: "fixed",
            top: 52,
            left: 0,
            right: 0,
            background: "#0a1220",
            borderBottom: "1px solid #1e3a5f",
            zIndex: 199,
            padding: "8px 0 16px",
          }}
        >
          {NAV_LINKS.map(({ href, label }) => {
            const isActive = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={handleNavClick}
                style={{
                  display: "block",
                  padding: "12px 24px",
                  color:      isActive ? "#00c44f" : "#dde6f5",
                  fontWeight: isActive ? 700 : 500,
                  fontSize:   "0.95em",
                  borderLeft: isActive ? "3px solid #00c44f" : "3px solid transparent",
                }}
              >
                {label}
              </Link>
            );
          })}
        </div>
      )}

      {/* ── Backdrop (tap outside drawer to close) ──────────────────────── */}
      {menuOpen && (
        <div
          className="mobile-only"
          onClick={() => setMenuOpen(false)}
          style={{
            position: "fixed", inset: 0, top: 52,
            zIndex: 198,
            background: "rgba(0,0,0,0.4)",
          }}
        />
      )}

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </>
  );
}
