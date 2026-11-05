import assert from "node:assert/strict";
import { test } from "node:test";
import { displayEmail } from "../lib/user.ts";

test("displayEmail prefers the ID token email over the sub-style username", () => {
  assert.equal(displayEmail({ email: "a@example.com" }, "9436a4b8-uuid"), "a@example.com");
  assert.equal(displayEmail({}, "a@example.com"), "a@example.com");
  assert.equal(displayEmail(undefined, null), null);
  assert.equal(displayEmail({ email: 42 }, "u"), "u");
});
