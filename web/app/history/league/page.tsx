import LeagueGate from "@/components/LeagueGate";
import LeagueRetro from "@/components/LeagueRetro";
import { PageHead } from "@/components/broadcast";

/** Server page: LeagueGate reads LEAGUE_OWNER_EMAIL (a server env var —
 *  a client component could never check it without leaking it) and
 *  only then ships the client retro. */
export default function LeagueHistoryPage() {
  return (
    <LeagueGate>
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <PageHead kicker="The family league · 2026 · retired with honors" title="League Season" />
        <LeagueRetro />
      </div>
    </LeagueGate>
  );
}