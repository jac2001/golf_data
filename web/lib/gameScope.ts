/**
 * Who a signed-in user may see on a game board.
 * ==============================================
 * With a groupId: that group's members — or null when the caller isn't
 * one of them (the route turns null into a 403). Without one: everyone
 * who shares at least one group with the caller. A user with no groups
 * sees only themselves. The model plays everywhere, so its id is always
 * appended — its picks reveal at lock like anyone's.
 *
 * This is the page's whole privacy model in one function: "no group
 * selected" means "my people", never "the entire site".
 */

import { getSql } from "@/lib/db";

export async function visibleUserIds(userId: string, groupId?: number): Promise<string[] | null> {
  const sql = getSql();

  if (groupId) {
    const rows = await sql`
      SELECT user_id FROM group_members WHERE group_id = ${groupId}` as { user_id: string }[];
    const ids = rows.map(r => r.user_id);
    if (!ids.includes(userId)) return null;
    ids.push("model");
    return ids;
  }

  // "Members of any group I'm a member of" — the inner query finds my
  // groups, the outer collects everyone standing in them.
  const rows = await sql`
    SELECT DISTINCT user_id FROM group_members
    WHERE group_id IN (SELECT group_id FROM group_members WHERE user_id = ${userId})` as { user_id: string }[];

  const ids = new Set(rows.map(r => r.user_id));
  ids.add(userId);
  ids.add("model");
  return [...ids];
}
