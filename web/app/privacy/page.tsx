/**
 * /privacy — Privacy Policy. Each section maps to something the code
 * really does: Clerk accounts, Neon game tables, web-push subscriptions,
 * the assistant's Anthropic calls, in-memory IP rate limits, localStorage
 * UI choices. Update this page whenever one of those changes.
 */

import type { Metadata } from "next";
import { LegalPage, H, Para, List, CONTACT_EMAIL } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Privacy Policy · Golf Edge" };

export default function PrivacyPage() {
  return (
    <LegalPage kicker="What we collect, why, and who sees it" title="Privacy Policy">
      <Para>
        Golf Edge collects only what it needs to run your account and your games. We don&rsquo;t show
        ads, we don&rsquo;t sell or rent personal information, and we don&rsquo;t run third-party analytics
        or advertising trackers.
      </Para>

      <H>What we collect</H>
      <List items={[
        <><strong>Account details.</strong> When you sign up, our sign-in provider (Clerk) collects your
          email address, your name and any profile image that you or your sign-in provider share.</>,
        <><strong>Game activity.</strong> The groups you create or join, your display name, your picks,
          season settings, and the results and standings calculated from them.</>,
        <><strong>Notification settings.</strong> If you turn on reminders, we store your browser&rsquo;s
          push subscription (a delivery address and keys issued by your browser), your reminder preferences,
          and a record of which reminders we&rsquo;ve sent so you don&rsquo;t get duplicates.</>,
        <><strong>Assistant conversations.</strong> Questions you ask the AI assistant, its answers, and any
          thumbs-up or thumbs-down rating you give may be saved so we can improve it.</>,
        <><strong>Technical data.</strong> Your IP address is used briefly, in memory only, to enforce rate
          limits and usage quotas. Our hosting providers also keep standard request logs.</>,
        <><strong>On your device.</strong> The site saves small preferences, such as which tab or tour you
          last viewed, in your browser&rsquo;s local storage. Clerk uses cookies to keep you signed in.</>,
      ]} />

      <H>How we use it</H>
      <List items={[
        "to sign you in and keep your account secure;",
        "to run your games: saving picks, locking them on time, scoring them and showing standings to your group;",
        "to send the reminders you turned on;",
        "to answer assistant questions and improve answer quality;",
        "to prevent abuse, such as scraping or running up assistant costs.",
      ]} />

      <H>Who can see it</H>
      <List items={[
        <><strong>Your groups.</strong> Members of a group see your display name, and see your picks once
          they lock. Results and standings are shared with the group.</>,
        <><strong>Service providers</strong> that run the site for us, under their own privacy terms:
          Clerk (accounts and sign-in), Neon (database), Vercel and Render (hosting), Anthropic (the AI model
          that answers assistant questions), and your browser&rsquo;s push service (for reminders).</>,
        <><strong>Legal requests.</strong> We&rsquo;ll disclose information if the law requires it.</>,
      ]} />
      <Para>
        Assistant questions are sent to Anthropic to generate the answer. Please don&rsquo;t put personal or
        sensitive information in them.
      </Para>

      <H>How long we keep it</H>
      <Para>
        We keep account and game data while your account is active, so seasons and standings stay intact.
        Push subscriptions are deleted when your browser reports them as expired, or when you turn
        reminders off. Rate-limit records reset within a day and aren&rsquo;t stored.
      </Para>

      <H>Your choices</H>
      <List items={[
        "Turn reminders off at any time in Settings or in your browser's notification settings.",
        "Update your name, email address or profile image in your account settings.",
        <>Ask us for a copy of your data, or to delete your account and game data, by emailing{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Picks that were part of a group&rsquo;s
          finished season may be kept in an anonymized form so the group&rsquo;s results still add up.</>,
      ]} />

      <H>Children</H>
      <Para>
        Golf Edge is not intended for anyone under 18, and we don&rsquo;t knowingly collect information from
        children. If you believe a child has signed up, contact us and we&rsquo;ll delete the account.
      </Para>

      <H>Security</H>
      <Para>
        Data is sent over HTTPS, sign-in is handled by Clerk, and access to your games is limited to members
        of your groups. No system is perfectly secure, but we work to protect what you share with us.
      </Para>

      <H>Changes</H>
      <Para>
        If this policy changes in a meaningful way, we&rsquo;ll update the effective date and note the change
        on the site.
      </Para>

      <H>Contact</H>
      <Para>
        Privacy questions or requests: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </Para>
    </LegalPage>
  );
}
