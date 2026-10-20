# Group chirps — design note (2026-10-20)

Roadmap: Pilot → "Improve during the pilot" → Group chirps (Jack, Oct 17).
The question the pilot answers: will friends talk here when they already
have a group text? Our only reason to exist next to the group text is the
GAME CONTEXT on the message ("Jack just passed you", on the real matchup).
So chirps live on the matchup, not in a separate messaging center.

## v1 scope

- **One thread per group per tournament**, newest at the bottom; past
  weeks stay readable (switching the event switches the thread).
- **Where:** a "Send a chirp" button on the Match Center card (and the
  week-results card), opening the thread as a bottom sheet.
- **Preset lines tied to what just happened** (Jack's
  `web/lib/chirpPresets.ts`): only presets that are TRUE right now are
  offered ("Don't look now" only when one of your golfers leads). Plus a
  short custom message (max 140 characters).
- **Each chirp carries a context card**: a frozen snapshot of the
  situation it reacts to ("2nd · $412K · Rick leads by $38K"), built
  server-side from the Match Center data. Never a hidden pick: the card is
  built only from what the sender could already see (reveal-at-lock, the
  same `pickVisible` rule), so before lock it carries no golfer names.
- **Reactions:** a small fixed set, tap to toggle, counts shown.
- **Unread badge** on the group bar and the Matchup tab: chirps since you
  last opened the thread.
- **Moderation:** report a chirp; the group owner can remove any chirp,
  an author their own. Removed chirps show "Removed".
- **Always sent by the player, never automatic.**

## Not in v1

DMs, images, attachments, push notifications for chirps (the unread badge
only; social push comes later with its own mute, separate from pick
reminders), alerts on every standings change.

## Data (Neon, additive migration `web/scripts/migrate-chirps.mjs`, approved by Jack Oct 20)

- `chirps` (id, group_id, tournament_id, user_id, user_name, preset_id
  NULL, text, card jsonb, created_at, removed_at NULL, removed_by NULL)
- `chirp_reactions` (chirp_id, user_id, emoji, PRIMARY KEY all three)
- `chirp_reports` (chirp_id, user_id, reason, created_at)
- `chirp_reads` (group_id, user_id, last_read_at, PRIMARY KEY first two)

## Routes (members only, via lib/gameScope.ts)

- `GET /api/friends/chirps?group_id&tournament_id` → thread + reactions + unread
- `POST` same → send (preset or custom; server builds the card)
- `DELETE` → remove (author or group owner)
- `POST /api/friends/chirps/react`, `/report`, `/read`

## Measuring it (feeds the weekly scorecard)

`app_events`: `chirp_sent` { preset_id | "custom" }, `chirp_reacted`,
`chirp_opened`. The pilot question is answered by: share of active
players who send at least one chirp in tournaments 2 and 3.
