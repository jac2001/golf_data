/**
 * history/page.tsx — retired route
 * =================================
 * Every tab moved in the Broadcast redesign: Bets + My Slip live on the
 * Betting Board (/betting), Results + Model on How It Works (/methodology).
 * Kept as a redirect so old bookmarks keep working.
 */

import { redirect } from "next/navigation";

export default function HistoryPage() {
  redirect("/betting");
}
