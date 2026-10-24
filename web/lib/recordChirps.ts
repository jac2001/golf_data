import type { GroupRecords } from "./groupRecords.ts";
import type { Preset } from "./chirpPresets.ts";


export const RECORD_LINES = {
  recordEarnings: "New group earnings record. Your move.",
  tiedEarnings: "Matched the group earnings record. Who's next?",
  recordStreak: "New group winning-streak record. Come stop it.",
} as const;
export type RecordChirpContext = {
  status: "open" | "live" | "settling" | "final";
  userId: string;
  played: boolean;
  /** True only for latest finalized week, with older official history. */
  eligible: boolean;
  before: GroupRecords;
  after: GroupRecords;
};
/**
 * TODO(Jack): optional suggestions, NEVER send automatically.
 * Only final + played + eligible. A first-ever baseline isn't a broken record.
 * Offer earnings when user holds after and value exceeds a non-null before.
 * Offer tied earnings when same value, user newly joins holders (not already held).
 * Offer streak when user holds after and exceeds non-null before (at least 2).
 * Order earnings then streak; max 2; stable IDs from RECORD_LINES; no duplicates.
 * Server must rebuild this context when sending; client booleans are not proof.
 */
export function recordChirps(c: RecordChirpContext): Preset[] {
  if (c.status !== "final" || !c.played || !c.eligible) {
    return [];
  }
  const presets: Preset[] = [];
  const beforeEarnings = c.before.earnings;
  const afterEarnings = c.after.earnings;
  if (
  beforeEarnings &&
  afterEarnings &&
  afterEarnings.holderIds.includes(c.userId)
) {
    if (afterEarnings.value > beforeEarnings.value) {
      presets.push({
        id: 'recordEarnings',
        text: RECORD_LINES.recordEarnings,
      });
    } else if (
      afterEarnings.value === beforeEarnings.value && 
      !beforeEarnings.holderIds.includes(c.userId)
    )
    {presets.push({
    id: "tiedEarnings",
    text: RECORD_LINES.tiedEarnings,
  });
      
      }
  }
  const beforeStreak = c.before.streak;
const afterStreak = c.after.streak;

if (
  beforeStreak &&
  afterStreak &&
  afterStreak.holderIds.includes(c.userId) &&
  afterStreak.value > beforeStreak.value &&
  afterStreak.value >= 2
) {
  presets.push({
    id: "recordStreak",
    text: RECORD_LINES.recordStreak,
  });
}

return presets;



}
