// web/lib/modelBrain.ts  — YOUR function to write


/** Average % of purse paid per finishing bucket (PGA standard table). */
const BUCKET_PAYOUT_PCT = {
  win: 18.0,        // P1
  p2to5: 6.6,       // avg of positions 2–5
  p6to10: 3.0,      // avg of 6–10
  p11to20: 1.6,     // avg of 11–20
  madeCutRest: 0.45 // avg of 21st through last paid spot
};

export type Probs = {
  win_prob: number | null;    // e.g. 0.055  (cumulative!)
  top5_prob: number | null;
  top10_prob: number | null;
  top20_prob: number | null;
  cut_prob: number | null;
};


/** Expected prize money for one player: purse × Σ (bucketProb × bucketPct). */
export function expectedPayout(purse: number, probs: Probs): number {
    const ladder = ["win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob"] as const;
    const filled: Record<string, number> = {};
    let prev = 0;
    for (const rung of ladder) {
        filled[rung] = probs[rung] ?? prev;   // copy, never mutate the input
        prev = filled[rung];
    }

    const bucketProb = {
        win: filled.win_prob,
        p2to5: Math.max(filled.top5_prob - filled.win_prob, 0),
        p6to10: Math.max(filled.top10_prob - filled.top5_prob, 0),
        p11to20: Math.max(filled.top20_prob - filled.top10_prob, 0),
        madeCutRest: Math.max(filled.cut_prob - filled.top20_prob, 0)
    };
    return purse * (Object.keys(bucketProb).reduce((sum, key) => sum + bucketProb[key as keyof typeof bucketProb] * BUCKET_PAYOUT_PCT[key as keyof typeof BUCKET_PAYOUT_PCT] / 100, 0));
}

/** Round Game: the model's pick for a round — best win chance it hasn't used. */
export function modelRoundPick(
  field: { player_name: string; win_prob: number | null }[],
  alreadyUsed: string[],
): string | null {
  // TODO(Jack): filter out used names, return the highest win_prob player
    // (null if the field is empty). One line of filter + one reduce/sort.
    if (field.length === 0) {
        return null;
    }
    const availablePlayers: { player_name: string; win_prob: number | null }[] = field.filter(player => !alreadyUsed.includes(player.player_name));
    if (availablePlayers.length === 0) {
        return null;
    }
    const bestPlayer = availablePlayers.reduce((prev, current) => (prev.win_prob ?? 0) > (current.win_prob ?? 0) ? prev : current);
    return bestPlayer.player_name; 
}