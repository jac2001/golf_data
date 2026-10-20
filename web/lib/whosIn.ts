/**
 * whosIn.ts — the organizer's view: who's in this week, who isn't yet.
 * ====================================================================
 * The launch plan: "An organizer needs to see who has joined and who
 * still needs to pick, without revealing hidden picks." Completion test:
 * an organizer runs a second tournament without Jack's help.
 *
 * The card in each game shows a headline ("3 of 5 in for Bermuda"), each
 * member's state, and a Share button that drops a ready-made nudge into
 * the group's own chat. The server only ever sends COUNTS per member
 * (how many of their picks are in), never which golfers, so nothing here
 * can reveal a hidden pick.
 *
 * Pure function, no imports from "@/": `npm test` runs it.
 */

export type MemberCount = {
  /** Clerk user id, or "model" for the Golf Edge model. */
  user_id: string;
  /** What friends see them as (lib/displayName). */
  name: string;
  /** How many of their picks are in for this event (0..needed). */
  picked: number;
};

export type WhosIn = {
  /** e.g. "3 of 5 in for Bermuda" (short: it's a card heading). */
  headline: string;
  /** Members with a full entry, in a stable order. */
  inNames: string[];
  /** Members still short (none or some picks), in a stable order. */
  waitingNames: string[];
  /** The message the Share button sends to the group chat; "" when
   *  there's nobody to nudge. */
  shareText: string;
};

// ── TODO(Jack): whosIn ────────────────────────────────────────────────────────
//
// members:    everyone in the group (the model too), with their pick counts
// needed:     picks for a full entry (Let It Ride's players per week; Fade 3;
//             College 1; the Round Game's current round 1)
// eventName:  "Butterfield Bermuda Championship"
// lockDetail: Jack's eventStatusLine detail, e.g. "locks Wed at midnight ET",
//             or "" when unknown
//
// Facts the tests pin:
//   - The model always plays, so it isn't a member to count or to nudge.
//   - In = picked >= needed. Everyone else is waiting (0 or some picks).
//   - The headline counts people: "<in> of <members> in".
//   - Everyone in → shareText is "" (nobody to nudge).
//   - shareText never mentions a golfer (it can't: it only has counts) and
//     never shames: it names who's still to pick and when picks lock.
//   - Same input, same output: sort names so the order doesn't jump around.
//
// Decisions that are yours (reason in a comment):
//   a. Someone with SOME picks (2 of 3): list them as waiting like
//      everyone else, or say "partway"? Does the share text treat them
//      differently?
//   b. The share text's tone and length. It lands in a group chat with
//      friends; a long message gets skipped. Names: all of them, or "3
//      people" past some number?
//   c. The headline: the short event name ("Bermuda") or the full one?
//      Full names can be 40 characters.
//
// Done when: npm test (from web/) passes lib/whosIn.test.ts, plus one test
// of your own for decision (b): the exact shareText for the sample group.
// Decision a: partway (2 of 3) is plain "waiting", same as none: either way they still need to pick.
// Decision b: name everyone still to pick, up to MAX_NAMES; past that, "N people" keeps the chat message short.
// Decision c: the full event name: clearest in a group chat, and the card has room for it.
export function whosIn(members: MemberCount[], needed: number, eventName: string, lockDetail: string): WhosIn {
  const people = members.filter(x => x.user_id !== "model");
  const byName = (a: MemberCount, b: MemberCount) => a.name.localeCompare(b.name);
  const inNames = people.filter(x => x.picked >= needed).sort(byName).map(x => x.name);
  const waitingNames = people.filter(x => x.picked < needed).sort(byName).map(x => x.name);
  const short = eventName;
  const MAX_NAMES = 4;
  const who = waitingNames.length > MAX_NAMES ? `${waitingNames.length} people` : waitingNames.join(", ");
  const lock = lockDetail ? ` Lineup ${lockDetail}.` : "";   // same wording as the pick confirmation
  const shareText = waitingNames.length === 0 ? "" : `Still need picks for ${short}: ${who}.${lock}`;
  return {
  headline: `${inNames.length} of ${people.length} in for ${short}`,
  inNames,
  waitingNames,
  shareText,
};
}
