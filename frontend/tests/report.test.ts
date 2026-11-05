import assert from "node:assert/strict";
import { test } from "node:test";
import { failureMessage, isTerminal, scoreBand, skillsCoverage, sortSuggestions, type Suggestion } from "../lib/report.ts";

test("scoreBand thresholds", () => {
  assert.equal(scoreBand(100), "strong");
  assert.equal(scoreBand(75), "strong");
  assert.equal(scoreBand(74), "fair");
  assert.equal(scoreBand(50), "fair");
  assert.equal(scoreBand(49), "weak");
  assert.equal(scoreBand(0), "weak");
});

test("terminal statuses stop polling", () => {
  assert.equal(isTerminal("DONE"), true);
  assert.equal(isTerminal("FAILED"), true);
  assert.equal(isTerminal("PENDING"), false);
  assert.equal(isTerminal("PROCESSING"), false);
});

test("suggestions sorted high → low, stable within a priority", () => {
  const items: Suggestion[] = [
    { priority: "low", section: "a", advice: "1" },
    { priority: "high", section: "b", advice: "2" },
    { priority: "medium", section: "c", advice: "3" },
    { priority: "high", section: "d", advice: "4" },
  ];
  assert.deepEqual(sortSuggestions(items).map((s) => s.section), ["b", "d", "c", "a"]);
  assert.equal(items[0].section, "a", "input is not mutated");
});

test("skills coverage", () => {
  assert.equal(skillsCoverage({ matched_skills: ["aws", "python"], missing_skills: ["go"] }), 67);
  assert.equal(skillsCoverage({ matched_skills: [], missing_skills: [] }), null);
});

test("failure messages map backend error codes, with a fallback", () => {
  assert.match(failureMessage("InvalidUpload"), /PDF/);
  assert.match(failureMessage("TextractJobFailed"), /text/);
  assert.match(failureMessage("AnalysisBlocked"), /safety/);
  assert.match(failureMessage(undefined), /failed/);
  assert.match(failureMessage("SomethingNew"), /failed/);
});
