/**
 * mypicks/page.tsx — retired route
 * =================================
 * The league zone dissolved into the main app (Phase 1): the 2026
 * retrospective lives at /history/league; Let It Ride returns as a
 * hostable friends game (Phase 2). Redirect keeps old bookmarks alive.
 */

import { redirect } from "next/navigation";

export default function MyPicksPage() {
  redirect("/history/league");
}
