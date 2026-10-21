# Glossary exercise

This is the learning portion of This Week roadmap step 5. No UI imports the
unfinished glossary yet. Steps 3, 4 and 6 remain separate work.

1. Open `web/lib/glossary.ts`. SG is the worked example. Add the other six
   entries with the same label / definition / example structure.
2. Implement `getGlossaryEntry`. Normalize the input, find a matching canonical
   term, then return its dictionary entry or null. Matching is exact, not fuzzy.
3. Add one test of your own in `web/lib/glossary.test.ts`.
4. Remove `Partial` from the dictionary type once all entries exist. TypeScript
   will then catch a missing term at compile time.
5. From `web/`, run `node --test lib/glossary.test.ts`, then `npm test`.

The tests intentionally fail while the exercise is unfinished. Do not skip
or weaken them to turn the suite green. They check lookup behavior and basic
content completeness, not the accuracy of your explanations; review the copy
against the comments in glossary.ts before calling it done.

TypeScript guide:
- `as const` retains the exact seven strings instead of widening to string[].
- `GlossaryTerm` is a union: only those seven terms are allowed as keys.
- `Record<Key, Value>` describes a dictionary whose values share a shape.
- `Partial` temporarily allows missing keys; `Readonly` forbids assignment.
- `string | null | undefined` makes missing input explicit.
- Returning `null` lets the future UI render an ordinary label without an empty help box.

Next plumbing step after your implementation passes: add a reusable tap/keyboard
help control and wire it into the relevant labels. It should open on tap or
Enter/Space, close on Escape/outside click, and avoid triggering table sorting.
Use explicit context for EV; a lineup-earnings definition must not be reused
for betting-return EV. Verify the actual UI at phone width before checking
roadmap step 5 complete.
