# TypeScript Lessons — Golf Edge

Every example is real code from this repo, mostly code you wrote or
reviewed. Each lesson: the feature, why *our* code needed it, and an
explain-back prompt. Companion to `LESSONS_CHEAT_SHEET.md`.

The one idea underneath all of it: **TypeScript is compile-time only.**
Types are erased before the code runs. They can stop you calling a
function wrongly; they can never validate data arriving at runtime.
Every lesson below is some consequence of that line.

---

## Lesson 1 — Annotations vs inference (when to write the type)

TS infers most types; you annotate where inference can't reach or
where you want a *contract*.

```ts
// modelBrain.ts — annotated: parameters and return are the CONTRACT
export function modelCollegePick(
  preds: (Probs & { player_name: string })[],
  purse: number,
  schools: { school: string; players: string[] }[],
): string | null {

// inside — inferred: TS knows evs is number[] from the map
const evs = school.players.map(player => nameToEV[nameKey(player)] ?? 0);
```

**Rule of thumb:** annotate function signatures and empty containers;
let everything else infer. An empty container is the classic
inference failure: `const rows = []` is `never[]` (an array nothing
can go into), which is why you wrote
`const nameToEV: Record<string, number> = {}` — an empty `{}` infers
as having no keys at all.

**Explain back:** why does `const [picks, setPicks] = useState([])`
break the moment you call `setPicks(["Scheffler"])`, and what's the
fix? (Hint: `useState<string[]>([])` — Lesson 6.)

---

## Lesson 2 — Union types and the null discipline

A union type is "one of these." Our most important one:

```ts
// modelBrain.ts
export type Probs = {
  win_prob: number | null;   // the model may have no number for a player
  ...
};
```

`number | null` FORCES every consumer to decide what null means —
the compiler won't let you do arithmetic on it directly. The three
tools, all in your code:

```ts
(b.win_prob ?? 0) - (a.win_prob ?? 0)   // ?? — default ONLY for null/undefined
table?.players?.[nameKey(p.player_name)] // ?. — stop and yield undefined if absent
if (!ev) return ...;                     // guard — after this line TS KNOWS ev exists
```

**`??` vs `||`, the trap:** `||` replaces every falsy value — `0`,
`""`, `false` included. `p.win_prob || 0.01` would silently rewrite a
real 0% probability; `??` only fires on null/undefined. (displayName
uses `||` **on purpose** — an empty-string username should fall
through to the next name source. Choosing between them is choosing
which values count as "missing.")

**Explain back:** in `modelRoundPick`, what does
`(prev.win_prob ?? 0) > (current.win_prob ?? 0)` do to a player whose
win_prob is null, and why is that a *design decision*, not just
syntax?

---

## Lesson 3 — Type aliases, intersections, and literal unions

```ts
type Probs = { win_prob: number | null; ... };        // alias: a named shape
preds: (Probs & { player_name: string })[]            // intersection: BOTH shapes
type GameMode = "picks" | "rounds" | "fades" | "college";  // literal union
```

- An **alias** names a shape so four functions can share it — change
  `Probs` once, every signature updates.
- An **intersection** (`&`) glues shapes: `Probs & { player_name }`
  means "a probability ladder that also knows whose it is." Cheaper
  than defining `NamedProbs` when it's used in two places.
- A **literal union** makes the *values* the type. `GameMode` isn't
  "any string" — it's exactly four strings, so
  `setMode("fdaes")` is a compile error, and this switch-like code
  can't silently miss:

```ts
// friends/page.tsx — localStorage returns string; the union forces a check
const m = localStorage.getItem("friends-game-mode");
if (m === "picks" || m === "rounds" || m === "fades" || m === "college") return m;
return "picks";
```

That `if` is doing **narrowing** (Lesson 7): inside it, TS knows `m`
is a `GameMode`, so returning it type-checks.

**Explain back:** why did StandingsTab need its own narrower union
(`"picks" | "fades" | "college"`) instead of reusing `GameMode`, and
what bug does that prevent at compile time?

---

## Lesson 4 — `as const`, `keyof`, `typeof`: types FROM values

Your `expectedPayout` runs on this trio:

```ts
const ladder = ["win_prob", "top5_prob", "top10_prob", "top20_prob", "cut_prob"] as const;
```

Without `as const`, that's `string[]` — TS forgets which strings.
With it, it's a readonly tuple of exactly those five literals, so
`probs[rung]` type-checks: TS can prove each rung is a real key of
`Probs`. **`as const` = "the values ARE the type."**

```ts
sum + bucketProb[key as keyof typeof bucketProb]
```

Reading inside-out: `typeof bucketProb` = the type of that object;
`keyof ...` = the union of its key names (`"win" | "p2to5" | ...`);
`key as ...` asserts this string is one of them. Why the assertion at
all? `Object.keys()` returns `string[]` — TS deliberately forgets the
keys (objects can carry extra properties at runtime), so you bridge
with `as` when *you* know the object is closed.

**Explain back:** the home page's tour pills iterate
`([["pga","PGA Tour"],["euro","DP World Tour"]] as const)`. What
would `setTour(id)` complain about if the `as const` were removed?

---

## Lesson 5 — Functions as values: callbacks and comparators

Half your code is functions handed to other functions:

```ts
[...preds].sort((a, b) => (b.win_prob ?? 0) - (a.win_prob ?? 0))  // comparator
picks.reduce((s, p) => s + (table[nameKey(p.player_name)]?.earnings ?? 0), 0)
field.filter(r => r.player_name.toLowerCase().includes(q))
```

TS types these *contextually*: because `preds` is `Probs[]`, the `a`
and `b` in the comparator are `Probs` with no annotation needed —
inference flowing INTO the callback. The comparator contract
(negative = a first) isn't in the type at all, which is why the fade
pool's direction bug (Lesson 7 of the ML sheet) compiled cleanly:
**types catch wrong shapes, never wrong logic.**

Note also `const nameKey = (n: string) => ...` — a function stored in
a `const`. Arrow functions are values like any other; that's what
makes "one function, one truth" (fadePool validating on the server
AND rendering in the browser) possible — you export the value.

**Explain back:** in `modelRoundPick` you used `reduce` to find a max
instead of sort-then-take-first. What does each cost on a 150-player
field, and when does the difference matter?

---

## Lesson 6 — Generics: types with parameters

A generic is a type that takes a type argument, like a function takes
a value argument:

```ts
Record<string, number>          // object: string keys → number values
Map<string, EarningsResp>       // your per-event earnings cache
Promise<PredictionsResponse>    // "will eventually deliver this shape"
useState<GameMode>("picks")     // React state locked to the union
```

And you've USED a generic component we wrote:

```ts
// components/broadcast — SubTabs works for ANY string-union tab type
export function SubTabs<T extends string>({ tabs, active, onChange }: {
  tabs: { id: T; label: string }[]; active: T; onChange: (t: T) => void;
})
```

`<T extends string>` says: caller picks the tab type; whatever `T` is,
`active` and every `tabs[i].id` and the `onChange` argument must all
agree. That's why the friends page and methodology page both use
SubTabs with *different* tab unions and both get full checking — one
component, per-caller precision.

**Explain back:** why is `useState<string[]>([])` necessary but
`useState(0)` fine without an argument?

---

## Lesson 7 — Narrowing and the `as` trust boundary

TS *narrows* a union as your code rules cases out:

```ts
if (!tid) return Response.json({ error: "tournament_id required" }, { status: 400 });
// below this line, tid is string, not string | undefined
```

Guards, `typeof x === "string"`, `Array.isArray`, `=== null` — each
one teaches the compiler. Narrowing is free and safe.

`as` is the opposite: it teaches the compiler NOTHING and asserts
YOUR belief. Every `as` in our routes marks a **trust boundary** —
a place where data enters from outside TypeScript's sight:

```ts
const picks = await sql`SELECT ...` as PickRow[];        // the DB's schema, our word
const d = await res.json();                              // any — JSON is untyped
setState(d as never);                                    // the ugly "trust me" escape
```

The sql one is honest: WE created that table, the columns are known,
the annotation documents them. The `as never` ones are debt — they
silence the checker entirely. The discipline: **assert at the
boundary, validate what matters, and never `as` your way past a type
error inside your own logic** (that error is usually a real bug —
like the fade pool's `pool.length` after poolFor started returning
an object; the compiler caught every call site for us).

**Explain back:** why is `payload's own tournament_id` checked at
runtime in PicksTab even though the response is typed as
`PredictionsResponse`? (This is THE lesson: types are erased; the
euro-settle class of bug lives at runtime.)

---

## Lesson 8 — async/await and Promise composition

Network code is Promises; `await` unwraps them:

```ts
const res = await fetch(`${MODEL_API}/api/events/open`);
if (!res.ok) return null;
const { events } = await res.json();     // destructuring the payload
```

Three composition patterns, all in the repo:

```ts
// Sequential — each line NEEDS the previous
const ev = await openEvent(tid);
const pool = await poolFor(ev.tid);

// Parallel — independent fetches, one round-trip of waiting
const [preds, earn] = await Promise.all([
  getPredictions(20, done.tournament_id),
  getEventEarnings(done.tournament_id),
]);

// Fire per item, then wait for all (leaderboard: one fetch PER event)
await Promise.all(tids.map(async tid => { ...fetch and cache... }));
```

The `.then/.catch` chains in the React pages are the same machinery
pre-await; in effects they're convenient because you can't make the
effect callback itself async directly.

One trap you've seen: `async` in a loop with `await` inside is
sequential ON PURPOSE in model-sync (inserts must respect prior
state), while the leaderboard uses `Promise.all` ON PURPOSE
(fetches are independent). Sequential-vs-parallel is a correctness
choice, not a style choice.

**Explain back:** in the recap route, member picks are fetched, THEN
earnings. Could those be `Promise.all`ed? What about the loop in
`shareRecap` → no loop — but why must `reg.pushManager.subscribe`
await `Notification.requestPermission` first?

---

## Lesson 9 — React + TS: state, props, and CSS objects

```ts
const [standings, setStandings] = useState<Standing[] | null>(null);
```

`Standing[] | null` encodes three UI states in one type: `null` =
loading (render the spinner), `[]` = loaded-empty (render "no picks
yet"), non-empty = render the table. The type IS the state machine —
which is why the components read `if (!standings) ... if
(standings.length === 0) ...` in that exact order.

Props are just a typed object parameter:

```ts
function FadeTab() { ... }                          // no props
function GroupsTab({ focusJoin = false }: { focusJoin?: boolean })  // optional + default
function Toggle({ on, busy, onClick }: { on: boolean; busy?: boolean; onClick: () => void })
```

`onClick: () => void` — a function type as a prop; `void` = "returns
nothing I'll use."

And the styling pattern everywhere:

```ts
const card: React.CSSProperties = { background: "var(--bc-card)", ... };
<div style={{ ...card, padding: 0 }}>
```

`React.CSSProperties` catches typo'd property names at compile time;
spread-then-override (`...card, padding: 0`) is the same shallow-copy
idea as `[...preds]` from the mutation lesson — build a new object,
never edit the shared one.

**Explain back:** what breaks (and when — compile or runtime?) if
`useState<Standing[] | null>(null)` became `useState(null)`?

---

## The through-line

Look back at the bugs this month and sort them:

- **Caught by TS at compile time:** every call site when poolFor's
  return shape changed; the missing `getOpenEvents` import; the
  duplicate `modelCollegePick` declaration.
- **Invisible to TS, caught by tests/review:** fade-sort direction,
  alphabetical ladder fill, raw-name joins pricing players at $0,
  Presidents Cup wearing Bank of Utah's label, mtime lying on CI.

TypeScript patrols the first category for free, forever. The second
category is *semantics* — direction, meaning, provenance — and no
type system sees it. That's why the codebase pairs types with the
other guards: payload-label checks, UNIQUE constraints, behavioral
tests, clamps. Types are the cheapest guard, not the only one.
