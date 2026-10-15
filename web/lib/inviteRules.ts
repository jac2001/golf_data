/**
 * inviteRules.ts — does this invite link work for this person, right now?
 * ========================================================================
 * One-tap invites (docs/MOBILE_FIRST_DESIGN.md, decision A): a link is
 * multi-use, expires after 7 days, allows 20 joins, and can be revoked by
 * its group's owner or its creator. These functions decide what a person
 * opening a link SEES. The accept route also enforces expiry/uses/revoke
 * in one guarded SQL UPDATE, so two friends tapping at once can't push a
 * link past 20; that's the database's job, not this file's.
 *
 * Pure functions, no imports from "@/": `npm test` runs them directly.
 */

export const INVITE_TTL_DAYS = 7;
export const INVITE_MAX_USES = 20;

/** The parts of an invite_links row these rules look at. */
export type InviteLink = {
  expires_at: Date;
  max_uses: number;
  uses: number;
  revoked_at: Date | null;
};

export type InviteStatus = "ok" | "already_member" | "revoked" | "expired" | "used_up";

// ── TODO(Jack): three small functions ────────────────────────────────────────
//
// 1. inviteExpiry(now): when a link created at `now` stops working.
//    INVITE_TTL_DAYS days later. (Date math: milliseconds are safest.)
//
// 2. inviteStatus(link, now, isMember): which InviteStatus applies.
//      - expired:  now is AT or after expires_at (a link "expiring at noon"
//                  does not work at noon)
//      - used_up:  uses has reached max_uses
//      - revoked:  revoked_at is set
//      - already_member: this person is already in the group
//      - ok:       none of the above
//    Several can be true at once (an old link can be both expired AND
//    revoked). Decision that's yours, with the reason in a comment:
//    which one wins? Think about what the person should be told, and
//    what they can do about it. One hint: an existing member opening an
//    old link probably just wants to get to their group.
//
// 3. inviteMessage(status, groupName): the one line the person reads.
//    Plain words, says what happened AND what to do next, e.g. for
//    expired: "This invite to {group} expired — ask whoever sent it for
//    a new link." No error codes, no blame. "ok" gets an inviting line.
//
// Done when: npm test (from web/) passes lib/inviteRules.test.ts — and
// you've added one test of your own for the precedence you chose.

export function inviteExpiry(now: Date): Date {
  throw new Error("Jack: inviteExpiry");
}

export function inviteStatus(link: InviteLink, now: Date, isMember: boolean): InviteStatus {
  throw new Error("Jack: inviteStatus");
}

export function inviteMessage(status: InviteStatus, groupName: string): string {
  throw new Error("Jack: inviteMessage");
}
