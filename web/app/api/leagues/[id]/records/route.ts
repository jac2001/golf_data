/**
 * /api/leagues/[id]/records — a Let It Ride season's group records.
 *
 * Most outright weekly wins, longest winning streak, and highest weekly
 * lineup earnings (Jack's lib/groupRecords.ts), rebuilt from settled
 * results on every request (lib/recordHistory.ts). Members only: group
 * ids are sequential. Pending weeks carry no money, so nothing about an
 * unfinished week is revealed. Not shown in the UI yet (the Record Book
 * is next, docs/RECORDS_CHIRPS_WORKBOOK.md).
 */
import { auth } from "@clerk/nextjs/server";
import { getSql } from "@/lib/db";
import { computeGroupRecords, prepareRecordWeeks, type RecordValue } from "@/lib/groupRecords";
import { loadRecordHistory, type SeasonRow } from "@/lib/recordHistory";
import { latestWeekEligibility } from "@/lib/recordWeeks";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in" }, { status: 401 });
  const leagueId = Number((await params).id);
  if (!Number.isSafeInteger(leagueId)) return Response.json({ error: "Bad league id" }, { status: 400 });

  const sql = getSql();
  const season = await sql`
    SELECT l.id, l.group_id, l.season_start::text, l.season_end::text, l.tours
    FROM leagues l JOIN group_members m ON m.group_id = l.group_id
    WHERE l.id = ${leagueId} AND m.user_id = ${userId}` as SeasonRow[];
  if (!season.length) return Response.json({ error: "Not your league" }, { status: 403 });

  const history = await loadRecordHistory(season[0]);
  if (!history) return Response.json({ error: "Records are unavailable right now" }, { status: 503 });
  if (!history.ok) {
    console.warn(`[records] league ${leagueId}: pick on unscheduled event ${history.tournamentId}`);
    return Response.json({ error: "Records are unavailable right now" }, { status: 503 });
  }
  let weeks: ReturnType<typeof prepareRecordWeeks>;
  try { weeks = prepareRecordWeeks(history.weeks); }
  catch (e) {
    console.warn(`[records] league ${leagueId}: ${String(e)}`);
    return Response.json({ error: "Records are unavailable right now" }, { status: 503 });
  }
  const records = computeGroupRecords(weeks, weeks[0]?.scope ?? { groupId: String(season[0].group_id), seasonId: String(leagueId), mode: "let-it-ride" });

  const roster = await sql`SELECT user_id, user_name FROM group_members WHERE group_id = ${season[0].group_id}` as { user_id: string; user_name: string }[];
  const names = new Map(roster.map(r => [r.user_id, r.user_name || "Player"]));
  names.set("model", "The Model");
  const holders = (r: RecordValue | null) => r && {
    value: r.value, holders: r.holderIds.map(id => ({ user_id: id, name: names.get(id) ?? "Former member" })),
  };
  // Which week(s) set the earnings record: the evidence a record card shows.
  const qualifies = (w: (typeof weeks)[number]) => w.status === "final" && w.complete && w.official && w.entries.length >= 2;
  const earningsWeeks = records.earnings
    ? weeks.filter(w => qualifies(w) && w.entries.some(e => e.earningsCents === records.earnings!.value && records.earnings!.holderIds.includes(e.userId)))
        .map(w => ({ week_id: w.weekId, events: history.events[w.weekId] }))
    : [];

  return Response.json({
    league_id: leagueId,
    records: { wins: holders(records.wins), streak: holders(records.streak),
               earnings: records.earnings && { ...holders(records.earnings), weeks: earningsWeeks } },
    latest: latestWeekEligibility(weeks),
    weeks: weeks.map(w => ({ week_id: w.weekId, status: w.status, complete: w.complete, official: w.official,
                             entrants: w.entries.length, events: history.events[w.weekId] })),
  });
}
