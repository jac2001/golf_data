/**
 * /api/friends/chirps — a group's thread for one tournament (docs/CHIRPS_DESIGN.md).
 * ===================================================================================
 * GET    ?group_id&tournament_id → { chirps, is_owner, me }   (also marks the thread read)
 * GET    ?group_id&unread=1 → { unread }   (chirps by others since you last opened; doesn't mark)
 * POST   { group_id, tournament_id, preset_id?, text } → the new chirp
 * DELETE { id } → remove (the author, or the group's owner)
 *
 * Members only (lib/gameScope.ts: 403 otherwise). Always sent by a person:
 * nothing here posts on anyone's behalf. The context card is built on the
 * server from what the sender could see (lib/chirpCard.ts), never trusted
 * from the client.
 */
import { auth, currentUser } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { visibleUserIds } from "@/lib/gameScope";
import { nameOf } from "@/lib/displayName";
import { track } from "@/lib/track";
import { LINES } from "@/lib/chirpPresets";
import { buildChirpCard } from "@/lib/chirpCard";

const MAX_TEXT = 140;
const REACTIONS = ["👏", "😂", "🔥", "😬"];   // route files may only export handlers

type Row = { id: string; user_id: string; user_name: string; preset_id: string | null; text: string;
  card: unknown; created_at: string; removed_at: string | null };

export async function GET(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const url = new URL(req.url);
  const groupId = Number(url.searchParams.get("group_id") || 0);
  const tid = url.searchParams.get("tournament_id")?.toUpperCase();
  if (!groupId) return Response.json({ error: "group_id required" }, { status: 400 });
  if (!(await visibleUserIds(userId, groupId))) return Response.json({ error: "Not a member of this group." }, { status: 403 });
  const sql = getSql();

  if (url.searchParams.get("unread") === "1") {
    const r = await sql`
      SELECT count(*)::int AS n FROM chirps c
      LEFT JOIN chirp_reads rd ON rd.group_id = c.group_id AND rd.user_id = ${userId}
      WHERE c.group_id = ${groupId} AND c.user_id <> ${userId} AND c.removed_at IS NULL
        AND (rd.last_read_at IS NULL OR c.created_at > rd.last_read_at)` as { n: number }[];
    return Response.json({ unread: r[0]?.n ?? 0 });
  }
  if (!tid) return Response.json({ error: "tournament_id required" }, { status: 400 });

  const [rowsRaw, reactsRaw, ownerRaw] = await Promise.all([
    sql`SELECT id::text, user_id, user_name, preset_id, text, card, created_at::text, removed_at::text
        FROM chirps WHERE group_id = ${groupId} AND tournament_id = ${tid} ORDER BY created_at, id`,
    sql`SELECT r.chirp_id::text AS chirp_id, r.emoji, count(*)::int AS n, bool_or(r.user_id = ${userId}) AS mine
        FROM chirp_reactions r JOIN chirps c ON c.id = r.chirp_id
        WHERE c.group_id = ${groupId} AND c.tournament_id = ${tid} GROUP BY 1, 2`,
    sql`SELECT owner_id FROM groups WHERE id = ${groupId}`,
  ]);
  const rows = rowsRaw as Row[];
  const reacts = reactsRaw as { chirp_id: string; emoji: string; n: number; mine: boolean }[];
  const owner = ownerRaw as { owner_id: string }[];
  // Opening the thread reads it (the unread badge counts from here).
  await sql`INSERT INTO chirp_reads (group_id, user_id, last_read_at) VALUES (${groupId}, ${userId}, now())
    ON CONFLICT (group_id, user_id) DO UPDATE SET last_read_at = now()`;

  const byChirp = new Map<string, { emoji: string; n: number; mine: boolean }[]>();
  for (const r of reacts) byChirp.set(r.chirp_id, [...(byChirp.get(r.chirp_id) ?? []), { emoji: r.emoji, n: r.n, mine: r.mine }]);
  const chirps = rows.map(r => r.removed_at
    ? { id: r.id, user_id: r.user_id, user_name: r.user_name, removed: true, created_at: r.created_at }
    : { id: r.id, user_id: r.user_id, user_name: r.user_name, preset_id: r.preset_id, text: r.text, card: r.card,
        created_at: r.created_at, removed: false, reactions: byChirp.get(r.id) ?? [] });
  return Response.json({ chirps, is_owner: owner[0]?.owner_id === userId, me: userId, reactions: REACTIONS });
}

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const groupId = Number(body.group_id || 0);
  const tid = String(body.tournament_id ?? "").toUpperCase();
  const presetId = body.preset_id ? String(body.preset_id) : null;
  let text = String(body.text ?? "").replace(/\s+/g, " ").trim();
  if (!groupId || !tid) return Response.json({ error: "group_id and tournament_id required" }, { status: 400 });
  if (presetId) {
    // A preset's words come from the server's list, not the client.
    const line = (LINES as Record<string, string>)[presetId];
    if (!line) return Response.json({ error: "unknown preset" }, { status: 400 });
    text = line;
  }
  if (!text) return Response.json({ error: "Say something first." }, { status: 400 });
  if (text.length > MAX_TEXT) return Response.json({ error: `Keep it under ${MAX_TEXT} characters.` }, { status: 400 });
  if (!(await visibleUserIds(userId, groupId))) return Response.json({ error: "Not a member of this group." }, { status: 403 });

  const sql = getSql();
  const card = await buildChirpCard(groupId, tid, userId);
  const me = nameOf(await currentUser());
  const rows = await sql`
    INSERT INTO chirps (group_id, tournament_id, user_id, user_name, preset_id, text, card)
    VALUES (${groupId}, ${tid}, ${userId}, ${me}, ${presetId}, ${text}, ${JSON.stringify(card)}::jsonb)
    RETURNING id::text, created_at::text` as { id: string; created_at: string }[];
  await sql`INSERT INTO chirp_reads (group_id, user_id, last_read_at) VALUES (${groupId}, ${userId}, now())
    ON CONFLICT (group_id, user_id) DO UPDATE SET last_read_at = now()`;
  await track(sql, userId, "chirp_sent", { preset_id: presetId ?? "custom", tournament_id: tid }, groupId);
  return Response.json({ chirp: { id: rows[0].id, user_id: userId, user_name: me, preset_id: presetId, text, card,
    created_at: rows[0].created_at, removed: false, reactions: [] } });
}

export async function DELETE(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });
  const id = String((await req.json().catch(() => ({}))).id ?? "");
  if (!/^\d+$/.test(id)) return Response.json({ error: "id required" }, { status: 400 });
  const sql = getSql();
  // The author, or the owner of the chirp's group: nobody else.
  const rows = await sql`
    UPDATE chirps c SET removed_at = now(), removed_by = ${userId}
    FROM groups g
    WHERE c.id = ${id} AND g.id = c.group_id AND c.removed_at IS NULL
      AND (c.user_id = ${userId} OR g.owner_id = ${userId})
    RETURNING c.id::text` as { id: string }[];
  if (!rows.length) return Response.json({ error: "Not yours to remove (or already removed)." }, { status: 403 });
  return Response.json({ removed: rows[0].id });
}
