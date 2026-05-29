/**
 * layout.tsx — Root Layout
 * =========================
 * This wraps EVERY page in the app — like a master template.
 * Anything you put here (nav bar, footer) appears on all pages.
 *
 * `children` is a special React prop meaning "whatever page is
 * currently being shown goes here" — like Python's {% block content %}.
 */

import type { Metadata, Viewport } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Golf Edge",
  description: "Golf betting analytics and value bets",
};

// Tells mobile browsers to render at device width instead of zooming out to 1100px.
// Without this, every responsive CSS rule is invisible on a phone.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,   // allow pinch-zoom but don't lock it
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
        <NavBar />
        <main style={{ flex: 1, padding: "24px 24px 48px" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
