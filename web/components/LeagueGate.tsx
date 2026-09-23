/**
 * LeagueGate — owner-only wall for the My League zone.
 * =====================================================
 * proxy.ts already guarantees the visitor is signed in; this server
 * component adds the second check: is the signed-in account the league
 * owner? The Tuesday Call and Star Budget are decision support for a
 * league played AGAINST the site's other likely visitors, so friends
 * get a polite lock screen instead of the model's suggestions.
 */

import { currentUser } from "@clerk/nextjs/server";

export default async function LeagueGate({ children }: { children: React.ReactNode }) {
  const user = await currentUser();
  const owner = (process.env.LEAGUE_OWNER_EMAIL ?? "").toLowerCase();
  const isOwner = !!owner && (user?.emailAddresses ?? [])
    .some(e => e.emailAddress.toLowerCase() === owner);

  if (isOwner) return <>{children}</>;

  return (
    <div style={{
      margin: "-24px -24px -48px", padding: "24px 24px 48px",
      minHeight: "calc(100vh - 56px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "var(--bc-card)", border: "1px solid var(--bc-line)",
        borderRadius: 10, padding: "36px 40px", maxWidth: 440, textAlign: "center",
      }}>
        <div style={{
          fontWeight: 900, fontSize: "1.3em", textTransform: "uppercase",
          letterSpacing: "0.04em", color: "var(--bc-text)", marginBottom: 10,
        }}>
          League members only
        </div>
        <p style={{ color: "var(--bc-muted)", fontSize: "0.9em", lineHeight: 1.6, margin: 0 }}>
          This zone holds one team&apos;s weekly strategy — and you might be the
          competition. The public side of the site (predictions, betting board,
          live) is all yours, and the Friends Game is coming soon.
        </p>
      </div>
    </div>
  );
}
