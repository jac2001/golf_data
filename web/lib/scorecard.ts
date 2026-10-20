/**
 * scorecard.ts — the pilot's weekly scorecard (launch plan, section 6).
 * =====================================================================
 * "Track only enough information to understand the experience." Five of
 * the plan's six measures come from app_events (logged since Oct 15); the
 * sixth, support needed per group, is Jack's own notes. The primary signal
 * is REPEAT GROUP PARTICIPATION; sign-ups alone don't show the game works.
 *
 *   1. Invited players who submit their first picks   (joining works?)
 *   2. First-week players who submit picks again       (want another week?)
 *   3. Groups with several active players across all the pilot's events
 *   4. Players who check the Match Center during play  (does it create interest?)
 *   5. Invitations sent without Jack prompting          (do users bring others?)
 *
 * Pure function, no imports from "@/": `npm test` runs it. The admin page
 * (/admin/scorecard) feeds it the rows and shows what you return.
 */

/** One app_events row. */
export type EventRow = {
  user_id: string | null;
  event: string;                       // joined_group, pick_made, match_viewed, invite_shared, ...
  group_id: number | null;
  props: Record<string, unknown>;      // pick_made: { game, tournament_id }, match_viewed: { status }, ...
  created_at: string;                  // ISO time
};

/** Who is in which group (group_members). */
export type Membership = { group_id: number; user_id: string };

/** Each measure as a count over its base, so the page can show "3 of 5". */
export type Ratio = { n: number; of: number };

export type Scorecard = {
  invitedWhoPicked: Ratio;     // 1: of people who joined a group, how many then made a pick
  pickedAgain: Ratio;          // 2: of people whose first pick was in an event, how many picked in a LATER event
  steadyGroups: Ratio;         // 3: of groups with any activity, how many had enough active players in EVERY event
  checkedMatchCenter: Ratio;   // 4: of people who picked, how many viewed the Match Center during play
  invitesShared: Ratio;        // 5: invites/nudges shared (n) by how many different people (of)
};

/** Players who never count. Admins are passed separately as `exclude`. */
export const NOT_PLAYERS = new Set(["model"]);

// ── TODO(Jack): scorecard ─────────────────────────────────────────────────────
//
// rows:        app_events for the pilot (any order)
// members:     group memberships
// events:      the pilot's tournament ids, IN DATE ORDER (e.g. ["R2026528", "R2026540", "R2026457"])
// exclude:     user ids to leave out entirely (admins: Jack prompting his own pilot)
//
// Facts the tests pin:
//   - Never count NOT_PLAYERS or `exclude` anywhere (numerator or base).
//   - 1: the base is people with a joined_group event; n is those who ALSO
//        have a pick_made AFTER they joined.
//   - 2: the base is people with at least one pick_made in `events`; n is
//        those who picked in a LATER event than their first one (order by
//        the `events` list, not by tournament id).
//   - 3: an "active player" in an event = made a pick_made in it. A group's
//        players are its members. The base is groups with at least one
//        active player in any pilot event; n is groups with at least
//        MIN_ACTIVE active players in EVERY pilot event.
//   - 4: the base is people with a pick_made; n is those with a match_viewed
//        whose props.status includes "live".
//   - 5: n = invite_shared + nudge_shared events; of = distinct people who shared.
//   - Same rows in any order, same scorecard.
//
// Decisions that are yours (reason in a comment):
//   a. MIN_ACTIVE for measure 3: 2 ("multiple active players", the plan's
//      words) or 3? Put it in a named constant.
//   b. Measure 4 during play only ("live"), or include "final" too? The
//      plan says "during play"; a Sunday-night look at the final board is
//      engagement too.
//   c. Measure 1: does a pick in ANY game count as "first picks", or only
//      Let It Ride (the recommended starting game)?
//
// Done when: npm test (from web/) passes lib/scorecard.test.ts, plus one
// test of your own for decision (a).

// MIN_ACTIVE can stay at 2 because that would be at least another person in the group made a pick
// Measure 4 can include final because looking at results are still engagement 
// Any game picks count. That is engagement and should be followed
const MIN_ACTIVE = 2;

export function scorecard(rows: EventRow[], members: Membership[], events: string[], exclude: string[]): Scorecard {
  const excluded = new Set([...NOT_PLAYERS, ...exclude]);
  const pilotEvents = new Set(events);
  const joinedAt = new Map<string, number>();
  const lastPickAt = new Map<string, number>();
  const pickedEvents = new Map<string, Set<string>>();
  const viewers = new Set<string>();
  const sharers = new Set<string>();
  let shares = 0;

  for (const row of rows) {
    const user = row.user_id;
    if (user === null || excluded.has(user)) continue;

    if (row.event === "joined_group") {
      const time = Date.parse(row.created_at);
      joinedAt.set(user, Math.min(joinedAt.get(user) ?? Infinity, time));
    } else if (row.event === "pick_made") {
      const time = Date.parse(row.created_at);
      lastPickAt.set(user, Math.max(lastPickAt.get(user) ?? -Infinity, time));
      const tid = row.props.tournament_id;
      if (typeof tid === "string" && pilotEvents.has(tid)) {
        const picked = pickedEvents.get(user) ?? new Set<string>();
        picked.add(tid);
        pickedEvents.set(user, picked);
      }
    } else if (row.event === "match_viewed") {
      const status = row.props.status;
      if (typeof status === "string" && (status.includes("live") || status.includes("final"))) {
        viewers.add(user);
      }
    } else if (row.event === "invite_shared" || row.event === "nudge_shared") {
      shares++;
      sharers.add(user);
    }
  }

  let invitedWhoPicked = 0;
  for (const [user, time] of joinedAt) {
    if ((lastPickAt.get(user) ?? -Infinity) > time) invitedWhoPicked++;
  }

  // Two distinct pilot events always include one later than the first,
  // regardless of the order in which the event rows arrived.
  let pickedAgain = 0;
  for (const picked of pickedEvents.values()) {
    if (picked.size > 1) pickedAgain++;
  }

  const groups = new Map<number, Map<string, Set<string>>>();
  for (const member of members) {
    if (excluded.has(member.user_id)) continue;
    const picked = pickedEvents.get(member.user_id);
    if (!picked) continue;
    const activity = groups.get(member.group_id) ?? new Map<string, Set<string>>();
    for (const tid of picked) {
      const players = activity.get(tid) ?? new Set<string>();
      players.add(member.user_id);
      activity.set(tid, players);
    }
    groups.set(member.group_id, activity);
  }

  let steadyGroups = 0;
  for (const activity of groups.values()) {
    if (events.every(tid => (activity.get(tid)?.size ?? 0) >= MIN_ACTIVE)) steadyGroups++;
  }

  let checkedMatchCenter = 0;
  for (const user of lastPickAt.keys()) {
    if (viewers.has(user)) checkedMatchCenter++;
  }

  return {
    invitedWhoPicked: { n: invitedWhoPicked, of: joinedAt.size },
    pickedAgain: { n: pickedAgain, of: pickedEvents.size },
    steadyGroups: { n: steadyGroups, of: groups.size },
    checkedMatchCenter: { n: checkedMatchCenter, of: lastPickAt.size },
    invitesShared: { n: shares, of: sharers.size },
  };
}
