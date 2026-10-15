# Mobile-first Golf Edge — design

Drafted 2026-10-15. Status: **proposed**; decisions A–D below are open.
Build order at the bottom. Sequenced on the roadmap after the PGA retrain.

## Goal

Most of the people we want playing aren't golf fans. They'll open a link
a friend texted them, on a phone, once. If joining and picking take more
than a minute or two, or the screen reads like a stats terminal, they're
gone. The goal is that someone who doesn't know golf can, on a phone:

1. **Join**: open a friend's invite → sign in → be in the group.
2. **Pick**: choose a game → make picks → see a clear "you're in".
3. **Follow**: open the matchup → understand where they stand → share
   the result.

…and come back next week because a reminder brought them back.

The website stays one product for everyone. This changes the phone-facing
surface, not the data, the API, or the games.

## What exists today

| Piece | State |
|---|---|
| Installable app | **Built.** `app/manifest.ts`: standalone display, icons, theme colors. "Add to Home Screen" already installs it like an app. |
| Push reminders | **Built.** `public/sw.js` shows them and opens the right page on tap; `web-push` + `/api/reminders-cron` send them. |
| Install guidance | **Missing.** Nobody is told they can install. iPhone needs Share → Add to Home Screen, and iOS only allows push for *installed* web apps (16.4+), so most iPhone players can't get reminders today. |
| Joining | **Two pieces.** The link (`/friends?invite=1`) only gets someone signed in; they then type the group's 6-character code, sent separately. The code is permanent and the same for everyone (`groups.invite_code`). |
| Navigation | **Desktop-shaped.** 9 top-nav links (`components/NavBar.tsx`), a hamburger on phones. No bottom navigation. |
| The game screen | **One 1,654-line page** (`app/friends/page.tsx`): groups, every game, picks, boards, settings, reminders. |
| Matchup | **Good bones.** `app/match/page.tsx` (425 lines) already has the three-layer cards and shares a recap image. |

## The three flows

### 1. Join (the biggest drop-off today)

```
Text from a friend ──► golfedge.com/join/<token>
                         │
                         ├─ signed out ─► Clerk sign-up (Google/Apple/email)
                         │                  └─ returns to /join/<token>
                         ▼
               "Jack invited you to RIVERSIDE GOLF"
               [ Join the group ]          ← one tap
                         ▼
               The group's current game, "Make your picks"
```

- A new `invite_links` table: `token` (random, 128-bit), `group_id`,
  `created_by`, `expires_at`, `max_uses`, `uses`, `revoked_at`.
- `/join/[token]` shows the group name and who invited you **before**
  sign-in (motivation), and joins on one tap **after**.
- The permanent code keeps working as a fallback.
- Owners see who joined through which link and can revoke one.

### 2. Pick

- Lands on **this week's game**, not a menu of games.
- **Golfer cards for phones:** name, a one-line "why" in plain English
  ("Top-10 in 4 of his last 5"), the price or uses left, one big pick
  button. Stats, advice and odds move behind **Details**.
- **A confirmation screen**, not a toast: "You're in: Scheffler,
  McIlroy, Åberg. Picks lock Thu 7:00am. We'll remind you."
- First successful pick → the one-time **install card** (flow 4 below).

### 3. Follow

- `/match` becomes the **Matchup** tab, unchanged in substance; it's
  already the strongest phone screen.
- The top of the card answers "am I winning?" in one line before any
  numbers.
- **Share result** is the primary action after Sunday (the recap image
  exists; this makes it one tap).

### 4. Install + reminders (supports all three)

- After the first pick, once: "Get pick reminders: add Golf Edge to
  your home screen." On iPhone, the actual three steps with the Share
  icon; on Android, the browser's own install prompt.
- Once installed, ask for notification permission **in context**
  ("Remind me before picks lock?"), never on first visit.

## Mobile shell

On phone widths only (desktop keeps the top nav), a persistent bottom
bar with four tabs:

| Tab | Goes to | Replaces |
|---|---|---|
| **Home** | This week: your games, what needs a pick, live scores | `/` |
| **Play** | Make picks for the current game | the picks part of `/friends` |
| **Matchup** | `/match` | — |
| **More** | Predictions, Betting Board, Players, How to Play, Settings | the hamburger menu |

`app/friends/page.tsx` gets split behind Home and Play: one component
per game, so a non-fan never scrolls past the Fade Game to find Weekly 3.

## Decisions (open)

- **A. Invite links: single-use, or expiring multi-use?** Single-use is
  safest, but one link can't go in a group chat. **Recommend:**
  multi-use, expiring in 7 days, max 20 uses, revocable. That's safer
  than today's permanent code, and it still works in a group text.
- **B. Can someone see the group before signing in?** **Recommend:**
  group name and inviter's first name only. No members, no picks.
- **C. Which game does a new member land on?** **Recommend:** the group's
  most-played game this week; Weekly 3 if there's no history.
- **D. Plain-English "why" lines on golfer cards: template or model?**
  **Recommend:** templates from data we already have (form, course
  history, the model's reason). Fast, free, and never wrong in tone.

## Not now

- **A dedicated phone app (React Native/Expo).** The backend is ready
  for one: the API routes and FastAPI service are what an app would
  call, and Clerk supports Expo. But it's a second interface, App Store
  review, a $99/yr account, and release cycles. Revisit once people
  return weekly. If a store listing is ever wanted first, wrapping this
  site (Capacitor) is the cheap route.
- **Offline mode / caching.** Scores must be live; the service worker
  stays push-only.

## How we'll know it worked

Measured per new member, before vs after:

- Invite → joined (today: unknown; instrument it first).
- Joined → first pick within the same visit.
- First pick → installed (and push permission granted).
- Week-2 return: picked again the following week.

And one qualitative test, before building past flow 1: hand a phone to
the friend who doesn't know golf, say nothing, and watch them join and
pick.

## Build order

1. **Instrument** the three flows (join, first pick, return) so there's
   a "before". (Small.)
2. **One-tap invites:** `invite_links` table, `/join/[token]`, owner
   view. (Small–medium; highest value.)
3. **Install card + in-context push permission.** (Small.)
4. **Bottom nav + split the game screen** behind Home/Play. (Largest.)
5. **Phone golfer cards + confirmation screen.** (Medium.)
6. **Matchup polish + one-tap share.** (Small.)
7. **The non-fan test**, then measure, then decide on a native app.

Teaching split: Jack writes the invite-token rules (expiry, max uses,
revocation) and their tests, and the "why"-line templates (decision D);
Claude does the plumbing (tables, routes, nav shell).
