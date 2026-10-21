/** Plain-language help for This Week. Not wired into the UI until complete. */
export const GLOSSARY_TERMS = ["SG", "OTT", "APP", "ARG", "PUTT", "EV", "pp"] as const;

// `typeof ...[number]` means any one of the strings in that tuple.
export type GlossaryTerm = (typeof GLOSSARY_TERMS)[number];
export type GlossaryEntry = Readonly<{
  label: string;
  definition: string;
  example: string;
}>;

// Record requires every glossary term. Readonly prevents reassignment.
export const GLOSSARY: Readonly<Record<GlossaryTerm, GlossaryEntry>> = {
  SG: {
    label: "Strokes gained",
    definition: "Shots gained or lost against a comparison benchmark. Positive is better; check the displayed period and benchmark.",
    example: "+1.0 SG per round means one shot better per round than that benchmark.",
  },
  OTT: {
    label: "Off the tee",
    definition: "Driving on par-4 and par-5 holes. Positive strokes gained means those drives saved shots compared with the displayed benchmark.",
    example: "+0.7 SG OTT per round means gaining an average of 0.7 shots per round through those drives compared with the benchmark.",
  },
  APP: {
    label: "Approach",
    definition: "Shots toward the green, including tee shots on par-3 holes. The green is the closely cut area around the hole. Positive strokes gained means better approach play than the displayed benchmark.",
    example: "+0.5 SG APP per round means gaining an average of half a shot per round through approach shots compared with the benchmark.",
  },
  ARG: {
    label: "Around the green",
    definition: "Short shots near the green, including shots from nearby sand traps, but excluding putts. Positive strokes gained means better short-shot play than the displayed benchmark.",
    example: "+0.3 SG ARG per round means gaining an average of 0.3 shots per round through these short shots compared with the benchmark.",
  },
  PUTT: {
    label: "Putting",
    definition: "Shots played from the putting green to roll the ball into the hole. Positive strokes gained means better putting than the displayed benchmark.",
    example: "If the benchmark averages 1.5 putts from a starting position and a golfer takes one, the golfer gains 0.5 shots on that hole through putting.",
  },
  EV: {
    label: "Expected value",
    definition: "Here, the estimated average golfer earnings across possible tournament outcomes, used as game points. This is an estimate, not a guaranteed result or money paid to you. Betting expected value is a separate measure.",
    example: "A golfer with a 50% chance of earning 100,000 points and a 50% chance of earning zero has an EV of 50,000 points, even though neither outcome awards 50,000.",
  },
  pp: {
    label: "Percentage points",
    definition: "The difference between two percentages, found by subtraction. This differs from the relative percentage change.",
    example: "A chance rising from 10% to 12% increases by 2 percentage points (2 pp). Its relative increase is 20% because 2 divided by 10 is 0.20.",
  },
};

/**
 * Look up a whole canonical term without guessing.
 * 1. Missing/empty input -> null.
 * 2. Trim surrounding spaces; accept any letter case, including "PP".
 * 3. Match a whole canonical term; "APPROACH" and "SG APP" are unknown.
 * 4. Return the entry from GLOSSARY, or null when unknown.
 */
export function getGlossaryEntry(raw: string | null | undefined): GlossaryEntry | null {
  const key = raw?.trim().toLowerCase();
  if (!key) return null;

  const term = GLOSSARY_TERMS.find(term => term.toLowerCase() === key);
  return term === undefined ? null : GLOSSARY[term];
}
