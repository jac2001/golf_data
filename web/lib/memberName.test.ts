/** Tests for memberName.ts. Run from web/:  npm test */
import { test } from "node:test";
import assert from "node:assert/strict";
import { memberName } from "./memberName.ts";

test("a real name wins, capitalized when typed lowercase", () => {
  assert.equal(memberName({ firstName: "rick", lastName: "legnon", username: "rickl" }), "Rick Legnon");
  assert.equal(memberName({ firstName: "Davis", lastName: null }), "Davis");
  assert.equal(memberName({ firstName: "  mary  ", lastName: " o'brien-smith " }), "Mary O'Brien-Smith");
});

test("names with any capital are left as typed", () => {
  assert.equal(memberName({ firstName: "Bryson", lastName: "DeChambeau" }), "Bryson DeChambeau");
  assert.equal(memberName({ firstName: "rory", lastName: "McIlroy" }), "rory McIlroy");
});

test("a username is kept exactly", () => {
  assert.equal(memberName({ username: "jack123", email: "jack@x.com" }), "jack123");
  assert.equal(memberName({ firstName: "", lastName: "  ", username: "GolfNut" }), "GolfNut");
});

test("an email prefix loses its +tag and separators", () => {
  assert.equal(memberName({ email: "jacklegnon+invite2@gmail.com" }), "Jacklegnon");
  assert.equal(memberName({ email: "jack.legnon_golf@x.com" }), "Jack Legnon Golf");
});

test("nothing usable is 'Player'", () => {
  assert.equal(memberName(null), "Player");
  assert.equal(memberName({}), "Player");
  assert.equal(memberName({ email: "+tag@x.com" }), "Player");
});
