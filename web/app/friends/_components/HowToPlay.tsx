"use client";

/**
 * How to play, per game: the "How to play" tab inside each game.
 * The Round, Fade and College text moved here word for word from the
 * bottom of each game's screen; Let It Ride's is the How to Play page's.
 */

import type { GameMode } from "./GamesTab";
import { card } from "./shared";

const text = { margin: 0, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)", lineHeight: 1.6 } as const;

export function HowToPlay({ game }: { game: GameMode }) {
  return (
    <div style={{ ...card, background: "var(--bc-panel)" }}>
      {game === "ride" && (
        <p style={text}>
          Pick 3 golfers each week — their prize money is your score. The
          catch: each golfer can only be used a few times a season (your group
          sets it — 3 per tour by default), so every week you choose who to
          spend and who to save. Best week earns a star; most money wins the
          season. Picks stay hidden until lock. The Golf Edge model plays too,
          as a member of your group.
        </p>
      )}
      {game === "rounds" && (<>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.6 }}>
          one pick per round, each player only once per event,
          scored by that round&apos;s score to par — lowest event total wins.
          Round 1 locks at midnight ET the night before it starts (UK time for
          DP World Tour events); each later round locks at the same midnight
          before its own day. The +5: if
          your pick doesn&apos;t post a score for a locked round — missed the
          cut, withdrew, or never teed off — you take +5 for it, but only
          once the field has finished that round (until then it just shows
          pending). Boards hide everyone&apos;s pick for a round until that
          round locks.
        </p>
      </>)}
      {game === "fades" && (<>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.6 }}>
          before lock (midnight ET the night before round 1 (UK time for DP World Tour events)), fade 3 of the 20 betting favorites —
          the favorites you think are overhyped. Your score is their combined
          prize money and the LOWEST total wins, so fading the eventual champion
          is a disaster. The model plays too: it fades the three favorites it expects to earn the least.
        </p>
      </>)}
      {game === "college" && (<>
        <p style={{ margin: 0, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.6 }}>
          claim ONE school per event — you can change it until
          lock, midnight ET the night before round 1 (UK time for DP World Tour
          events). Only schools with alumni in that week&apos;s field can be
          claimed. Schools stay hidden until lock.
        </p>
        <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.82em)", lineHeight: 1.6 }}>
          <li><strong style={{ color: "var(--bc-text)" }}>Schools aren&apos;t exclusive.</strong> Two
            friends can claim the same school — they&apos;ll post the same score and tie.</li>
          <li><strong style={{ color: "var(--bc-text)" }}>Best two count.</strong> Your score is the
            prize money of your school&apos;s two best finishers. With only one alumnus in the
            field, his earnings are your whole score.</li>
          <li><strong style={{ color: "var(--bc-text)" }}>Ties share the week.</strong> Everyone tied
            for the top score gets a win; if nobody&apos;s school earns anything, nobody does. The
            season ranks event wins.</li>
        </ul>
      </>)}
      <p style={{ ...text, marginTop: 12 }}>
        <a href="/how-to-play" style={{ color: "var(--bc-yellow)", fontWeight: 700 }}>All games and a practice round</a>
      </p>
    </div>
  );
}
