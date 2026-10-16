/**
 * activeGroup.ts — which group the Friends Game shows when it opens.
 * ==================================================================
 * Redesign step 3: the group switcher at the top of the Friends page
 * scopes EVERYTHING below it (boards, standings, "3 of 5 have picked").
 * This decides which group is selected before anyone taps anything.
 *
 * Pure function, no imports from "@/": `npm test` runs it.
 */

// ── TODO(Jack): pickActiveGroup ───────────────────────────────────────────────
//
// memberOf: ids of the groups this person is in, in the order the server
//           lists them (oldest joined first). May be empty.
// linked:   a group id from the URL (?group=12), e.g. where the invite page
//           sends someone right after they join. null if none.
// stored:   the group this device last switched to, or null.
//
// Return the group id to show, or null when they're in no group.
//
// Facts:
//   - Never return a group they aren't in. A link or a stored id can be
//     stale (they left, the group was deleted) or simply wrong.
//   - Someone who just joined through an invite should see THAT group.
//   - Otherwise keep the group they last chose on this device.
//   - Otherwise one of their groups: say which in a comment (decision a).
//
// Decision that's yours (reason in a comment):
//   a. No usable link or stored id, several groups: the first listed
//      (oldest joined) or the last (newest)? Think about who opens the
//      page with no stored choice: often someone on a new phone.
//
// Done when: npm test (from web/) passes lib/activeGroup.test.ts, plus one
// test of your own for decision (a).

export function pickActiveGroup(memberOf: number[], linked: number | null, stored: number | null): number | null {
  // Decision a: Pick the newest group (last in the list) when no link or stored id is usable. A person on a new phone is often a new member, and they want to see their new group.
  memberOf = memberOf.filter(g => g !== null);
  if (linked !== null && memberOf.includes(linked)) {
    return linked;
  }
  if (stored !== null && memberOf.includes(stored)) {
    return stored;
  }
  return memberOf.length > 0 ? memberOf[memberOf.length - 1] : null;
}
