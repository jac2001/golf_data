/**
 * fadeScore.ts — a Fade Game total, with withdrawals voided fairly.
 * ===================================================================
 * Lowest total wins, so a faded golfer who withdraws BEFORE teeing off
 * (and earns $0) was a free perfect fade (Jack, Oct 24: void them). Dropping
 * the slot would be just as free (a smaller sum), so a void slot counts as
 * the average of the member's other fades: neutral, never a reward.
 * A golfer who withdraws mid-round played and flopped: his $0 stands.
 *
 * Pure, no "@/" imports: `npm test` runs it.
 */

/** One fade: earnings, or "void" (never teed off). */
export type FadeSlot = number | "void";

/** The member's total, or null when every fade is void (nothing to score). */
export function fadeTotal(slots: readonly FadeSlot[]): number | null {
  const counted = slots.filter((s): s is number => s !== "void");
  if (counted.length === 0) return null;
  const sum = counted.reduce((a, b) => a + b, 0);
  return counted.length === slots.length ? sum : (sum / counted.length) * slots.length;
}
