"use client";

/**
 * /friends — the Friends Game.
 * =============================
 * Signed-in friends pick 3 players for the current tournament (same
 * format as Jack's league), see the season leaderboard graded by real
 * earnings, and track the model bets they've tailed. proxy.ts ensures
 * everyone here is signed in.
 */


import { useEffect, useState } from "react";
import { PageHead, SubTabs } from "@/components/broadcast";
import { MyBetsTab } from "./_components/MyBetsTab";
import { GamesTab } from "./_components/GamesTab";
import { GroupsTab } from "./_components/GroupsTab";
import { TailsTab } from "./_components/TailsTab";
import { ReminderBell } from "./_components/shared";

type GameTab = "games" | "groups" | "bets" | "tails";
const TABS: { id: GameTab; label: string }[] = [
  { id: "games",     label: "Games" },
  { id: "groups",    label: "Groups" },
  { id: "bets",      label: "My Bets" },
  { id: "tails",     label: "My Tails" },
];

export default function FriendsPage() {
  const [tab, setTab] = useState<GameTab>("games");
  const [invited, setInvited] = useState(false);

  // Invite links land here (/friends?invite=1) but deliberately DON'T
  // auto-join: a link gets forwarded, screenshotted, and re-shared — the
  // invite CODE, texted separately, stays the actual key. The link's only
  // job is to get a friend signed in and standing in front of the join
  // form. (Read in an effect, not useSearchParams — one-shot action, and
  // the hook would force a Suspense boundary.)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("invite") || q.get("join")) {   // ?join= is the old link format
      window.history.replaceState(null, "", "/friends");
      setInvited(true);
      setTab("groups");
    }
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <PageHead
        kicker="Graded by real prize money (DPWT estimated from the purse) · bragging rights only"
        title="Friends Game"
      />
      <SubTabs tabs={TABS} active={tab} onChange={setTab} />
      {invited && (
        <div style={{ background: "var(--bc-raised)", border: "1px solid var(--bc-line-hi)",
          borderRadius: 8, padding: "10px 14px", marginBottom: 14,
          color: "var(--bc-text)", fontSize: "0.9em", fontWeight: 600 }}>
          You&apos;ve been invited to a group — type the invite code from your
          friend&apos;s message below and hit Join.
        </div>
      )}
      {/* The game first; reminders are a setting, not the headline. */}
      {tab === "games" && <><GamesTab /><ReminderBell /></>}
      {tab === "groups" && <GroupsTab focusJoin={invited} />}
      {tab === "bets" && <MyBetsTab />}
      {tab === "tails" && <TailsTab />}
    </div>
  );
}
