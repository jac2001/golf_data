/**
 * bottomNav.ts — the phone tab bar's map of the site.
 * =====================================================
 * docs/MOBILE_FIRST_DESIGN.md, "Mobile shell": on phone widths a bar of
 * four tabs replaces the hamburger menu. Desktop keeps the top nav.
 *
 *   Home     /           this week: your games, what needs a pick
 *   Play     /friends    make picks (the games)
 *   Matchup  /match      am I winning?
 *   More     (a sheet)   everything else
 *
 * Pure data + one function, no imports from "@/": `npm test` runs it.
 * components/BottomNav.tsx renders whatever this file says.
 */

export type Tab = "home" | "play" | "matchup" | "more";

export type TabDef = { tab: Tab; label: string; href: string | null };

/** The four tabs, in order. More has no href: it opens the sheet. */
export const TABS: TabDef[] = [
  { tab: "home",    label: "Home",    href: "/" },
  { tab: "play",    label: "Play",    href: "/friends" },
  { tab: "matchup", label: "Matchup", href: "/match" },
  { tab: "more",    label: "More",    href: null },
];

/** What the More sheet lists, in order. */
export const MORE_LINKS: { href: string; label: string }[] = [
  { href: "/predictions", label: "This Week" },
  { href: "/live",        label: "Live" },
  { href: "/betting",     label: "Betting Board" },
  { href: "/players",     label: "Players" },
  { href: "/how-to-play", label: "How to Play" },
  { href: "/assistant",   label: "Assistant" },
  { href: "/settings",    label: "Settings" },
];

// ── TODO(Jack): activeTab ─────────────────────────────────────────────────────
//
// Given the current path (usePathname(), e.g. "/friends" or
// "/predictions/R2026554"), return which tab should light up, or null for
// none.
//
// Facts:
//   - "/" is Home, but ONLY exactly "/". Every path starts with "/", so a
//     startsWith("/") check would make Home light up everywhere.
//   - "/friends" and anything under it is Play.
//   - "/match" and anything under it is Matchup. Careful: a startsWith
//     check on "/match" would also match a future "/matchups" page. A
//     path is "under" a section when it's equal to it, or starts with it
//     plus "/".
//   - Every MORE_LINKS page (and anything under it) is More, so you can
//     see where you are even inside the sheet's pages.
//
// Decisions that are yours (reason in a comment):
//   a. Legacy league pages /fantasy, /mypicks, /history/league: they're
//      the picks game's old home. Play, More, or none?
//   b. Pages that belong to no tab: /join/<token>, /sign-in, /sign-up,
//      /terms, /privacy, /methodology. Light up nothing (null), or More?
//      Think about what someone who just opened an invite should see.
//   c. /history (not /history/league): it's off the nav already. Where?
//
// Done when: npm test (from web/) passes lib/bottomNav.test.ts, plus one
// test of your own for decision (a) or (b).

export function activeTab(pathname: string): Tab | null {
  // We do not need the legacy league pages, so we will return null for them. 
  // This is because they are not part of the new design and should not be highlighted in the bottom navigation.
  // The pages with no tab do not need to be highlighted in the bottom navigation, so we will return null for them as well.
  // History is nto relevant for users
  if (pathname === "/") {
    return "home";
  } else if (pathname === "/friends" || pathname.startsWith("/friends/")) {
    return "play";
  } else if (pathname === "/match" || pathname.startsWith("/match/")) {
    return "matchup";
  } else if (MORE_LINKS.some(link => pathname === link.href || pathname.startsWith(link.href + "/"))) {
    return "more";
  } else if (pathname === "/fantasy" || pathname === "/mypicks" || pathname.startsWith("/history/league")) {
    return null;
  } else {
    return null;
  }
}
