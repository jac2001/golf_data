/** Every This Week column has finished plain-language help. Run from web/: npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { COLUMN_HELP } from "./columnHelp.ts";

const COLUMNS = ["win", "top10", "cut", "owgr", "sg", "form", "edge", "odds", "move"] as const;

test("every field column has a label, definition and example", () => {
  for (const k of COLUMNS) {
    const h = COLUMN_HELP[k];
    for (const f of ["label", "definition", "example"] as const) {
      assert.ok(h[f].trim().length > 0, `${k}.${f} is empty`);
      assert.ok(!/TODO/.test(h[f]), `${k}.${f} unfinished`);
    }
  }
});
