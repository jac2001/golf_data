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
import { PageHead } from "@/components/broadcast";
import { MyBetsTab } from "./_components/MyBetsTab";
import { GamesTab } from "./_components/GamesTab";
import { GroupsTab } from "./_components/GroupsTab";
import { TailsTab } from "./_components/TailsTab";
import { ReminderBell } from "./_components/shared";
import { ActiveGroupProvider, useActiveGroup } from "./_components/ActiveGroup";
import { GroupBar } from "./_components/GroupBar";

// The page answers four questions, top to bottom: who (the group bar),
// which game, which event, what to do (both inside GamesTab). Groups'
// full screen opens from the group sheet; My Bets / My Tails sit at the
// bottom until they move to the Betting Board.
type View = "play" | "manage" | "bets" | "tails";

export default function FriendsPage() {
  return (
    <ActiveGroupProvider>
      <FriendsBody />
    </ActiveGroupProvider>
  );
}

function FriendsBody() {
  const { reload } = useActiveGroup();
  const [view, setView] = useState<View>("play");
  const [invited, setInvited] = useState(false);

  // Old invite links land here (/friends?invite=1) but deliberately DON'T
  // auto-join: the invite CODE, texted separately, stays the key; the
  // link's job is to get a friend signed in and in front of the join
  // form (now the group sheet). (An effect, not useSearchParams: a
  // one-shot action, and the hook would force a Suspense boundary.)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("invite") || q.get("join")) {   // ?join= is the old link format
      window.history.replaceState(null, "", "/friends");
      setInvited(true);
    }
  }, []);

  const back = () => { setView("play"); reload(); };
  const backBtn = (
    <button onClick={back} style={{ background: "transparent", border: "none", color: "var(--bc-yellow)",
      fontWeight: 700, fontFamily: "inherit", cursor: "pointer", minHeight: 44, padding: 0, marginBottom: 8 }}>
      ‹ Back to the games
    </button>
  );
  const quiet = { background: "transparent", border: "none", color: "var(--bc-muted)", fontFamily: "inherit",
    fontWeight: 700, cursor: "pointer", minHeight: 44, padding: "0 6px" } as const;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div className="mobile-hidden">
        <PageHead
          kicker="Graded by real prize money (DPWT estimated from the purse) · bragging rights only"
          title="Friends Game"
        />
      </div>
      {invited && (
        <div style={{ background: "var(--bc-raised)", border: "1px solid var(--bc-line-hi)",
          borderRadius: 8, padding: "10px 14px", marginBottom: 14,
          color: "var(--bc-text)", fontSize: "0.9em", fontWeight: 600 }}>
          You&apos;ve been invited to a group: type the invite code from your
          friend&apos;s message under Join with a code.
        </div>
      )}
      {view === "play" && <>
        <GroupBar startJoin={invited} onManage={() => setView("manage")} />
        <GamesTab />
        <ReminderBell />
        <div style={{ display: "flex", justifyContent: "center", gap: 4, marginTop: 8 }}>
          <button onClick={() => setView("bets")} style={quiet}>My bets</button>
          <span aria-hidden="true" style={{ color: "var(--bc-line-hi)", alignSelf: "center" }}>·</span>
          <button onClick={() => setView("tails")} style={quiet}>My tails</button>
        </div>
      </>}
      {view === "manage" && <>{backBtn}<GroupsTab /></>}
      {view === "bets" && <>{backBtn}<MyBetsTab /></>}
      {view === "tails" && <>{backBtn}<TailsTab /></>}
    </div>
  );
}
