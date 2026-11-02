import assert from "node:assert/strict";
import { test } from "node:test";
import { parseConfig } from "../lib/config.ts";

const valid = {
  apiUrl: "https://abc.execute-api.us-east-1.amazonaws.com",
  region: "us-east-1",
  userPoolId: "us-east-1_abc",
  clientId: "client",
};

test("parseConfig adds a trailing slash to apiUrl", () => {
  assert.equal(parseConfig(valid).apiUrl, "https://abc.execute-api.us-east-1.amazonaws.com/");
});

test("parseConfig rejects missing keys and non-https API", () => {
  assert.throws(() => parseConfig(null));
  assert.throws(() => parseConfig({ ...valid, clientId: "" }), /clientId/);
  assert.throws(() => parseConfig({ ...valid, apiUrl: "http://example.com" }), /https/);
});
