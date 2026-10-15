/**
 * installPrompt.ts — should this device see the install / reminders card, and which one?
 * ===================================================================================
 * docs/MOBILE_FIRST_DESIGN.md, flow 4. After someone's first pick, once:
 * help them put Golf Edge on their home screen, then (once installed) ask
 * "Remind me before picks lock?". Never on a first visit: a cold
 * permission prompt gets a reflexive "no", and on iPhone a "no" to
 * notifications is effectively permanent (only Settings can undo it).
 *
 * Why install comes first on iPhone: iOS only allows web push for apps
 * added to the home screen (16.4+). In a Safari tab, PushManager doesn't
 * exist, so "ask for notifications" isn't even possible until installed.
 * Android and desktop browsers allow push in a normal tab.
 *
 * Pure function, no imports from "@/": `npm test` runs it directly.
 * The component (components/InstallCard.tsx) gathers DeviceState and
 * renders whatever you return; it holds no rules of its own.
 */

export type Platform = "ios" | "android" | "desktop";

/** Everything the decision may look at, gathered by the component. */
export type DeviceState = {
  platform: Platform;
  /** Running from the home screen (display-mode: standalone). */
  installed: boolean;
  /** Android/desktop Chrome handed us its install prompt (beforeinstallprompt). */
  canPromptInstall: boolean;
  /** "unsupported" = no PushManager here (e.g. an iPhone Safari tab). */
  notifications: "default" | "granted" | "denied" | "unsupported";
  /** This device already has a push subscription saved. */
  subscribed: boolean;
  /** This device has completed at least one pick (any game). */
  hasPicked: boolean;
  /** How many times the card has been dismissed on this device. */
  dismissCount: number;
  /** When it was last dismissed, or null if never. */
  lastDismissedAt: Date | null;
};

export type CardStep =
  | "none"            // show nothing
  | "install_ios"     // the Share → Add to Home Screen steps
  | "install_prompt"  // a button that fires the browser's own install prompt
  | "ask_reminders";  // "Remind me before picks lock?" → Notification.requestPermission

/** Copy for each visible step, so the component and the tests agree. */
export const CARD_COPY: Record<Exclude<CardStep, "none">, { title: string; body: string; action: string }> = {
  install_ios: {
    title: "Get pick reminders",
    body: "Add Golf Edge to your home screen: tap Share, then Add to Home Screen.",
    action: "Got it",
  },
  install_prompt: {
    title: "Get pick reminders",
    body: "Install Golf Edge so it opens like an app and can remind you before picks lock.",
    action: "Install",
  },
  ask_reminders: {
    title: "Remind me before picks lock?",
    body: "One nudge the day before, only if your picks aren't in.",
    action: "Turn on reminders",
  },
};
export const SNOOZE_DAYS = 7;  // after the 1st dismissal, hide the card for this many days
export const MAX_DISMISSALS = 2;  // after this many dismissals, never show the card again

// ──  TODO(Jack): cardStep ──────────────────────────────────────────────────────
//
// Return which card this device should see right now.
//
// Facts to build from:
//   - Nothing before the first pick (hasPicked false → "none").
//   - Already subscribed → nothing left to ask for.
//   - notifications "denied" → we can't ask again (the browser won't
//     show the prompt), so don't nag about reminders.
//   - iPhone, not installed → "install_ios" (push is impossible until
//     installed, so asking for reminders first would do nothing).
//   - iPhone, installed → reminders can be asked ("ask_reminders") if
//     permission is still "default".
//   - Android/desktop: push works in a tab, so you could ask for
//     reminders directly. If canPromptInstall is true, offering the
//     install too is a nice extra.
//
// Decisions that are yours (reason in a comment):
//   a. Android/desktop, not installed, canPromptInstall true, notifications
//      "default": install first, or reminders first? (Reminders are the
//      real goal; install is a nice-to-have off iPhone.)
//   b. Snoozing. The card can be dismissed. Pick a rule: e.g. after the
//      1st dismissal hide it for N days; after the 2nd, never again.
//      Put N in a named constant. "At or after" N days counts as over,
//      same as the invite expiry.
//   c. notifications "granted" but subscribed false (permission given,
//      subscription lost, e.g. a reinstall): ask again, or "none"?
//      Hint: asking costs nothing here; the browser won't prompt again,
//      we'd just resubscribe.
//
// Done when: npm test (from web/) passes lib/installPrompt.test.ts — and
// you've added one test of your own for your snooze rule.

export function cardStep(state: DeviceState, now: Date): CardStep {
  if (!state.hasPicked) {
    return "none";
  }
  if (state.subscribed) {
    return "none";
  }
  if (state.notifications === "denied") {
    return "none";
  }
  if (state.dismissCount >= MAX_DISMISSALS) {
    return "none";
  }
  if (state.lastDismissedAt !== null && state.dismissCount > 0) {
    const snoozeUntil = new Date(state.lastDismissedAt.getTime() + SNOOZE_DAYS * 24 * 60 * 60 * 1000);
    if (now < snoozeUntil) {
      return "none";
    }
  }
  if (state.platform === "ios" && !state.installed) {
    return "install_ios";
  }
  // iPhone, installed, notifications "default" → ask for reminders
  if (state.platform === "ios" && state.installed && state.notifications === "default") {
    return "ask_reminders";
  }
  // Android/desktop: if canPromptInstall is true, offer install first; otherwise, ask for reminders.
  if (!state.installed && state.canPromptInstall) {
    return "install_prompt";
  }

  // Android/desktop, installed or can't prompt install, notifications "default" → ask for reminders
  if (state.notifications === "default") {
    return "ask_reminders";
  }
  
  return "none";
}
