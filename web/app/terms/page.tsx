/**
 * /terms — Terms of Service. Plain English, written to match what the
 * product actually does (free, no money handled, picks games among
 * friends, betting information that is not advice).
 */

import type { Metadata } from "next";
import { LegalPage, H, Para, List, CONTACT_EMAIL } from "@/components/LegalPage";

export const metadata: Metadata = { title: "Terms of Service · Golf Edge" };

export default function TermsPage() {
  return (
    <LegalPage kicker="The rules for using Golf Edge" title="Terms of Service">
      <Para>
        These terms cover your use of Golf Edge at playgolfedge.com (&ldquo;Golf Edge,&rdquo;
        &ldquo;we,&rdquo; &ldquo;us&rdquo;). By creating an account or using the site, you agree to them.
        If you don&rsquo;t agree, please don&rsquo;t use the site.
      </Para>

      <H>What Golf Edge is</H>
      <Para>
        Golf Edge is a free golf analytics site and a set of picks games you play with friends.
        It publishes model predictions for PGA Tour and DP World Tour events, and lets groups
        run games such as Let It Ride, the Round Game, the Fade Game and the College Game.
      </Para>
      <List items={[
        <>Golf Edge is <strong>free</strong>. We don&rsquo;t take entry fees, hold money, pay out prizes or accept wagers.</>,
        <>&ldquo;Earnings&rdquo; and &ldquo;prize money&rdquo; in the games are the golfers&rsquo; real
          tournament purses, used only as a scoring system. Nobody wins or loses money through Golf Edge.</>,
        <>Any arrangement you make with friends outside the site is between you and them, and is your responsibility.</>,
      ]} />

      <H>Predictions and betting information are not advice</H>
      <Para>
        The site shows model probabilities, odds comparisons and &ldquo;value&rdquo; estimates. These are
        statistical estimates for information and entertainment. They are often wrong, and past results
        don&rsquo;t predict future ones. Nothing on Golf Edge is financial, betting or professional advice,
        and you&rsquo;re solely responsible for any bet you place elsewhere.
      </Para>
      <Para>
        Only bet where it&rsquo;s legal for you and you&rsquo;re of legal age. If gambling stops being fun,
        call or text 1-800-GAMBLER (US) for free, confidential help.
      </Para>

      <H>Who can use it</H>
      <Para>
        You must be at least 18 years old to create an account. You&rsquo;re responsible for keeping your
        sign-in secure and for everything done under your account.
      </Para>

      <H>Groups and what others see</H>
      <List items={[
        <>Your display name and picks are visible to members of groups you join. Picks stay hidden until
          the event or round locks, then everyone in the group can see them.</>,
        <>Anyone with a group&rsquo;s invite link can join that group, so share links only with people you want in it.</>,
        <>Group owners can change season settings for their group.</>,
      ]} />

      <H>Acceptable use</H>
      <Para>Please don&rsquo;t:</Para>
      <List items={[
        "scrape, bulk-download or resell the site's data or predictions;",
        "try to get around rate limits, usage quotas, pick locks or access controls;",
        "use the AI assistant to generate abuse, spam or anything unlawful, or try to make it run up costs;",
        "pick a display name that impersonates someone or is offensive;",
        "interfere with the site or other people's use of it.",
      ]} />
      <Para>We may suspend or remove accounts that break these rules.</Para>

      <H>The AI assistant</H>
      <Para>
        The assistant is powered by a third-party AI model. Its answers can be incomplete or wrong,
        including about live scores, so check anything important. Daily usage limits apply.
      </Para>

      <H>Data sources and ownership</H>
      <Para>
        Golf data comes from third parties including DataGolf and official tour feeds. Golf Edge is
        independent and is not affiliated with or endorsed by the PGA TOUR, the DP World Tour or
        DataGolf. Tournament, tour and player names belong to their owners. The site&rsquo;s design,
        code, models and written content belong to Golf Edge.
      </Para>

      <H>No warranty</H>
      <Para>
        Golf Edge is provided &ldquo;as is&rdquo; and &ldquo;as available.&rdquo; Data can be late, missing or
        incorrect, games can have bugs, and the site can go down. We don&rsquo;t promise it will be accurate,
        uninterrupted or error-free.
      </Para>

      <H>Limitation of liability</H>
      <Para>
        To the fullest extent the law allows, Golf Edge isn&rsquo;t liable for any indirect, incidental or
        consequential losses, including betting losses, arising from your use of the site. Because the
        service is free, our total liability for any claim is limited to $0, or the lowest amount the law permits.
      </Para>

      <H>Changes and ending</H>
      <Para>
        We may update these terms. If a change is significant, we&rsquo;ll note it on the site. Continuing to use
        Golf Edge after a change means you accept the new terms. You can stop using the site at any time
        and ask us to delete your account (see the <a href="/privacy">Privacy Policy</a>).
      </Para>

      <H>Contact</H>
      <Para>
        Questions about these terms: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </Para>
    </LegalPage>
  );
}
