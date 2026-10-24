# This Week: keep both headers together

## Reproduced on the live site

After scrolling the Field page 720px, the body's measured height was still
720px. Its bottom was at the top of the screen. The sticky navigation had
moved above the viewport (top -35px, bottom 0), while the research tabs
remained at top 59px. The golfer rows showed through that empty top area.
The nav also measured only 35px despite its declared 56px height.

Two layout rules explain this: the body has height: 100%, and the navigation
is a shrinkable child of a flex column. The tabs separately assume 59px.

## Your three small edits

Search for TODO(Jack) in these locations:

1. `web/app/globals.css`, the `html, body` rule:
   replace the fixed `height: 100%` with `min-height: 100vh`.
   Minimum height fills a short screen but permits a long page to grow.
   Keep margin, padding, colors and fonts as they are.
2. `web/components/NavBar.tsx`, the nav style:
   use `height: "var(--site-nav-height)"` and add `flexShrink: 0`.
   The shared variable is already declared in globals.css. Retain sticky,
   top: 0, and zIndex: 200. No JavaScript scroll listener is needed.
3. `web/app/predictions/summary.module.css`, `.stickyTabs`:
   use `top: var(--site-nav-height)` instead of 59px.
   Border-box means the 3px border is already inside the 56px nav height.
   Keep background and z-index: 100 so text can't show through the tabs.

The scaffold only adds comments and an unused shared variable. It deliberately
leaves the bug in place until you make these edits. Do not switch the tabs to
position: fixed: that removes them from normal flow and introduces overlap.

## Done when

From web/, run `npm run build`. Then visually check the rendered page:

- Desktop: scroll from the top through the Field list, then back up. The logo
  navigation stays at y=0; the tab strip rests directly against its bottom.
- Phone (390px and 375px): repeat, including wrapped tab labels. The tabs stay
  below the nav without a window of moving text above them.
- Switch Field, Tee Times, Course Guide, Vs DataGolf and Course Fit after
  scrolling. All tabs remain usable; no extra horizontal page scrollbar.
- Short page and long page: navigation doesn't compress, footer remains sane.
- Check Home and Match Center too: body height and navigation are shared.
- Light/dark: the pinned backgrounds are opaque and readable.

Optional learning check: inspect the nav's bounding rectangle before and after
scrolling. Its top should stay 0 and its height should stay 56px. The stuck tab
strip should start at 56px. The body's height should grow with page content.

No unit test for literal CSS strings: the useful proof is the layout while
scrolling. If the problem persists after all three edits, inspect ancestor
height and overflow rules before increasing z-index.
