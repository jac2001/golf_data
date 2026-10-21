/** Plain-language glossary content and exact term lookup. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { GLOSSARY, GLOSSARY_TERMS, getGlossaryEntry } from "./glossary.ts";

for (const term of GLOSSARY_TERMS) {
  test(`glossary: ${term} has a readable label, definition and example`, () => {
    const entry = GLOSSARY[term];
    assert.ok(entry, `Add the ${term} entry in glossary.ts`);
    for (const field of ["label", "definition", "example"] as const) {
      assert.ok(entry[field].trim().length > 0, `${term}.${field} is empty`);
      assert.ok(!/TODO|<[^>]+>/.test(entry[field]), `${term}.${field} must be finished plain text`);
    }
  });
}

test("glossary: lookup accepts every canonical term and returns its entry", () => {
  for (const term of GLOSSARY_TERMS) {
    assert.ok(GLOSSARY[term], `Write ${term} first`);
    assert.equal(getGlossaryEntry(term), GLOSSARY[term]);
  }
});

test("glossary: lookup ignores case and surrounding whitespace", () => {
  for (const term of GLOSSARY_TERMS) {
    assert.ok(GLOSSARY[term], `Write ${term} first`);
    assert.equal(getGlossaryEntry(`  ${term.toLowerCase()}  `), GLOSSARY[term]);
    assert.equal(getGlossaryEntry(`\t${term.toUpperCase()}\n`), GLOSSARY[term]);
  }
});

test("glossary: missing, unknown and partial terms return null", () => {
  for (const raw of [null, undefined, "", "  ", "APPROACH", "SG APP", "S", "constructor", "__proto__"]) {
    assert.equal(getGlossaryEntry(raw), null);
  }
});

test("glossary: looking up help leaves the dictionary unchanged", () => {
  const before = JSON.stringify(GLOSSARY);
  getGlossaryEntry("sg");
  getGlossaryEntry("unknown");
  assert.equal(JSON.stringify(GLOSSARY), before);
});

test("glossary: PP header resolves to percentage points, not a partial match", () => {
  assert.equal(getGlossaryEntry("PP"), GLOSSARY.pp);
  assert.equal(getGlossaryEntry("SG OTT"), null);
});
