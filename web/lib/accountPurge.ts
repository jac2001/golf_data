/**
 * The database half of account deletion (see app/api/account/route.ts
 * for the policy). Takes the sql client as a parameter and has no "@/"
 * imports, so a script can run it against a throwaway user.
 */
import type { NeonQueryFunction } from "@neondatabase/serverless";

export const FORMER = "Former player";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function purgeUserData(sql: NeonQueryFunction<any, any>, userId: string, unlocked: string[], anon: string) {
  const owned = await sql`SELECT id FROM groups WHERE owner_id = ${userId}` as { id: number }[];
  const heirs = new Map<number, string | null>();
  for (const g of owned) {
    const next = await sql`
      SELECT user_id FROM group_members
      WHERE group_id = ${g.id} AND user_id <> ${userId} AND user_id <> 'model'
      ORDER BY joined_at LIMIT 1` as { user_id: string }[];
    heirs.set(g.id, next[0]?.user_id ?? null);
  }
  const orphaned = [...heirs].filter(([, h]) => !h).map(([id]) => id);
  // The names friends saw for this person (chirp snapshots store the leader
  // by name), from the groups they were in.
  const shown = (await sql`SELECT DISTINCT user_name FROM group_members WHERE user_id = ${userId}` as
    { user_name: string }[]).map(r => r.user_name).filter(Boolean);

  const steps = [
    // Personal, never shared: gone.
    sql`DELETE FROM reminders_sent WHERE endpoint IN (SELECT endpoint FROM push_subscriptions WHERE user_id = ${userId})`,
    sql`DELETE FROM push_subscriptions WHERE user_id = ${userId}`,
    sql`DELETE FROM user_prefs WHERE user_id = ${userId}`,
    sql`DELETE FROM user_bets WHERE user_id = ${userId}`,
    sql`DELETE FROM tailed_bets WHERE user_id = ${userId}`,
    sql`DELETE FROM picks WHERE user_id = ${userId}`,
    // Measurement events and invite attributions: gone (2026-10-20 review:
    // these tables postdated the purge and kept user ids and names).
    sql`DELETE FROM app_events   WHERE user_id = ${userId}`,
    sql`DELETE FROM invite_joins WHERE user_id = ${userId}`,
    // Chirps they wrote go, with the reactions and reports on them; their own
    // reactions and read markers go too. Reports THEY filed stay for the
    // group owner, without the reporter; "removed by" marks lose the id.
    sql`DELETE FROM chirp_reactions WHERE chirp_id IN (SELECT id FROM chirps WHERE user_id = ${userId})`,
    sql`DELETE FROM chirp_reports   WHERE chirp_id IN (SELECT id FROM chirps WHERE user_id = ${userId})`,
    sql`DELETE FROM chirps          WHERE user_id = ${userId}`,
    sql`DELETE FROM chirp_reactions WHERE user_id = ${userId}`,
    sql`DELETE FROM chirp_reads     WHERE user_id = ${userId}`,
    sql`UPDATE chirp_reports SET user_id = ${anon} WHERE user_id = ${userId}`,
    sql`UPDATE chirps SET removed_by = ${anon} WHERE removed_by = ${userId}`,
    // Their name inside OTHER people's chirp snapshots ("Jack leads by …"),
    // in the groups they were in: "Former player", like their picks.
    sql`UPDATE chirps SET card = jsonb_set(card, '{leader}', to_jsonb(${FORMER}::text))
        WHERE group_id IN (SELECT group_id FROM group_members WHERE user_id = ${userId})
          AND card->>'leader' = ANY(${shown})`,
    // Invite links they made keep working for friends, with no creator.
    sql`UPDATE invite_links SET created_by = ${anon} WHERE created_by = ${userId}`,
    // Groups nobody else is in: delete with their seasons, picks, chirps and links.
    sql`DELETE FROM chirp_reactions WHERE chirp_id IN (SELECT id FROM chirps WHERE group_id = ANY(${orphaned}))`,
    sql`DELETE FROM chirp_reports   WHERE chirp_id IN (SELECT id FROM chirps WHERE group_id = ANY(${orphaned}))`,
    sql`DELETE FROM chirps      WHERE group_id = ANY(${orphaned})`,
    sql`DELETE FROM chirp_reads WHERE group_id = ANY(${orphaned})`,
    sql`DELETE FROM invite_joins WHERE link_id IN (SELECT id FROM invite_links WHERE group_id = ANY(${orphaned}))`,
    sql`DELETE FROM invite_links WHERE group_id = ANY(${orphaned})`,
    sql`DELETE FROM league_picks WHERE league_id IN (SELECT id FROM leagues WHERE group_id = ANY(${orphaned}))`,
    sql`DELETE FROM leagues WHERE group_id = ANY(${orphaned})`,
    sql`DELETE FROM group_members WHERE group_id = ANY(${orphaned})`,
    sql`DELETE FROM groups WHERE id = ANY(${orphaned})`,
    // Picks nobody has seen yet: gone.
    sql`DELETE FROM league_picks  WHERE user_id = ${userId} AND tournament_id = ANY(${unlocked})`,
    sql`DELETE FROM fade_picks    WHERE user_id = ${userId} AND tournament_id = ANY(${unlocked})`,
    sql`DELETE FROM round_picks   WHERE user_id = ${userId} AND tournament_id = ANY(${unlocked})`,
    sql`DELETE FROM college_picks WHERE user_id = ${userId} AND tournament_id = ANY(${unlocked})`,
    // Picks that are part of a played week: anonymized.
    sql`UPDATE league_picks  SET user_id = ${anon}, user_name = ${FORMER} WHERE user_id = ${userId}`,
    sql`UPDATE fade_picks    SET user_id = ${anon}, user_name = ${FORMER} WHERE user_id = ${userId}`,
    sql`UPDATE round_picks   SET user_id = ${anon}, user_name = ${FORMER} WHERE user_id = ${userId}`,
    sql`UPDATE college_picks SET user_id = ${anon}, user_name = ${FORMER} WHERE user_id = ${userId}`,
    // Ownership passes on; then leave every group.
    ...[...heirs].filter(([, h]) => h).flatMap(([gid, heir]) => [
      sql`UPDATE groups  SET owner_id   = ${heir} WHERE id = ${gid}`,
      sql`UPDATE leagues SET created_by = ${heir} WHERE group_id = ${gid} AND created_by = ${userId}`,
    ]),
    sql`UPDATE leagues SET created_by = ${anon} WHERE created_by = ${userId}`,
    sql`DELETE FROM group_members WHERE user_id = ${userId}`,
  ];
  await sql.transaction(steps);
}
