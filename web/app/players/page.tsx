"use client";

/** Players: the page shell and tab switching. The tabs live in ./_components
 *  (split from one 2,300-line file, Players audit #24, Oct 22). */

import React, { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { getAllPlayers, getOwnerPicks } from "@/lib/api";
import { useIsAdmin } from "@/lib/useIsAdmin";
import { PageHead, SubTabs } from "@/components/broadcast";
import { BG, GREEN, MUTED, TEXT } from "./_components/shared";
import { LookupTab } from "./_components/ProfileTab";
import { StatsTab } from "./_components/StatsTab";
import { H2HTab } from "./_components/H2HTab";


type PageTab = "lookup" | "h2h" | "stats";

const PAGE_TABS: { id: PageTab; label: string }[] = [
  { id: "lookup",     label: "Profiles"     },
  { id: "h2h",        label: "Head-to-Head" },
  { id: "stats",      label: "Stats"        },
];


function PlayersPageInner() {
  const searchParams = useSearchParams();
  const deepLinkPlayer = searchParams.get("player") ?? undefined;

  const [pageTab, setPageTab]       = useState<PageTab>(deepLinkPlayer ? "lookup" : "lookup");
  const [players, setPlayers]       = useState<string[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [myPicks, setMyPicks]       = useState<string[]>([]);
  const admin = useIsAdmin();

  useEffect(() => {
    getAllPlayers()
      .then(d => setPlayers(d.players))
      .finally(() => setListLoading(false));
  }, []);

  // Pick highlights are Jack's personal-league picks: owner-only (audit #9).
  useEffect(() => {
    if (admin) getOwnerPicks().then(setMyPicks).catch(() => {});
  }, [admin]);

  // Jump to the Lookup tab whenever a ?player= link is followed — needed
  // because clicking a player link while already on /players (e.g. from the
  // Course Fit or Stats tab) only changes the URL; it doesn't remount this
  // component, so pageTab wouldn't otherwise follow.
  useEffect(() => {
    if (deepLinkPlayer) setPageTab("lookup");
  }, [deepLinkPlayer]);

  const tabBtn = (key: PageTab, label: string) => (
    <button
      key={key}
      onClick={() => setPageTab(key)}
      style={{
        background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none", cursor: "pointer",
        padding: "8px 16px", fontSize: "max(var(--fs-min), 0.88em)", fontWeight: pageTab === key ? 700 : 500,
        color: pageTab === key ? TEXT : MUTED,
        borderBottom: `2px solid ${pageTab === key ? GREEN : "transparent"}`,
        marginBottom: -1, transition: "color 0.15s",
      }}
    >
      {label}
    </button>
  );

  return (
    <main style={{ background: BG, minHeight: "100vh", color: TEXT, padding: "24px 20px" }}>
      <div className="page-wrap-md">

        {/* Page header */}
        <PageHead kicker="Profiles · head-to-head · course fit" title="Players" />

        {/* Tab bar */}
        <SubTabs tabs={PAGE_TABS} active={pageTab} onChange={setPageTab} />
        {/* Course fit has one home (Players audit #10): this page's own tab
            ran on a default profile in production and contradicted it. */}
        <Link href="/predictions?tab=coursefit" style={{ display: "inline-flex", alignItems: "center", minHeight: 44,
          color: "var(--bc-yellow)", fontWeight: 700, textDecoration: "none", fontSize: 14 }}>
          Which golfers suit this week&apos;s course? See Course Fit on This Week →
        </Link>

        {listLoading ? (
          <p style={{ color: MUTED }}>Loading players…</p>
        ) : pageTab === "lookup" ? (
          <LookupTab players={players} defaultPlayer={deepLinkPlayer} />
        ) : pageTab === "h2h" ? (
          <H2HTab players={players} />
        ) : (
          <StatsTab myPicks={myPicks} />
        )}
      </div>
    </main>
  );
}


export default function PlayersPage() {
  return (
    <Suspense>
      <PlayersPageInner />
    </Suspense>
  );
}
