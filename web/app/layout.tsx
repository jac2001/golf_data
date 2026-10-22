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
import { Archivo } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import Link from "next/link";
import "./globals.css";
import NavBar from "@/components/NavBar";
import UpdateToast from "@/components/UpdateToast";
import InstallCard from "@/components/InstallCard";
import BottomNav from "@/components/BottomNav";

// Broadcast display face — variable weight + width axes so headers can use
// the condensed-900 treatment (font-stretch) from the design system.
const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
});

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
  viewportFit: "cover",  // lets the phone tab bar pad for the iPhone home indicator
  // Colors the browser/status bar to match the nav, per the phone's theme.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#081f14" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider>
      {/* data-theme is set by the script before React loads, so React's markup
          and the live <html> differ on purpose: suppressHydrationWarning. */}
      <html lang="en" className={archivo.variable} suppressHydrationWarning>
        <head>
          {/* A theme chosen in Settings, applied before first paint (no flash). */}
          <script dangerouslySetInnerHTML={{ __html:
            `try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}` }} />
        </head>
        <body style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
          <NavBar />
          <main style={{ flex: 1, padding: "24px 24px 48px" }}>
            {children}
          </main>
          <footer style={{
            borderTop: "1px solid var(--bc-line)", padding: "14px 24px",
            display: "flex", flexWrap: "wrap", gap: "6px 18px", justifyContent: "center",
            color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)",
          }}>
            <span>Golf Edge · free to play, no money changes hands</span>
            <Link href="/terms" style={{ color: "inherit" }}>Terms</Link>
            <Link href="/privacy" style={{ color: "inherit" }}>Privacy</Link>
          </footer>
          <UpdateToast />
          <InstallCard />
          <BottomNav />
        </body>
      </html>
    </ClerkProvider>
  );
}
