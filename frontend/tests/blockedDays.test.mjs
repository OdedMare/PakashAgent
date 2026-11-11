import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/lib/blockedDays.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { blockedDaysOf, withBlockedDays } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

test("blocking Wednesday writes one hard whole-day recurring rule", () => {
  const next = withBlockedDays([], ["רביעי"]);
  assert.deepEqual(next, [{
    days: ["רביעי"], shifts: [], available: false, is_hard: true,
    reason: "יום חסום קבוע", source: "manager",
  }]);
  assert.deepEqual(blockedDaysOf(next), ["רביעי"]);
});

test("days read Sunday first, whatever order they were ticked in", () => {
  assert.deepEqual(blockedDaysOf(withBlockedDays(undefined, ["שישי", "ראשון"])), ["ראשון", "שישי"]);
});

test("a second day joins without a second rule for the first", () => {
  const next = withBlockedDays(withBlockedDays([], ["רביעי"]), ["רביעי", "שני"]);
  assert.deepEqual(blockedDaysOf(next), ["שני", "רביעי"]);
  assert.equal(next.filter((rule) => rule.days.includes("רביעי")).length, 1);
});

test("a rule recorded elsewhere shows as blocked and keeps its reason", () => {
  const studies = { days: ["רביעי", "חמישי"], shifts: [], available: false, reason: "לימודים", source: "manager" };
  assert.deepEqual(blockedDaysOf([studies]), ["רביעי", "חמישי"]);
  assert.deepEqual(withBlockedDays([studies], ["חמישי"]), [{ ...studies, days: ["חמישי"] }]);
  assert.deepEqual(withBlockedDays([studies], []), []);
});

test("rules of any other kind are neither read nor touched", () => {
  const others = [
    "לא עובד בלילות",
    { days: ["רביעי"], shifts: ["לילה"], available: false },
    { days: ["רביעי"], shifts: [], available: false, is_hard: false },
    { days: ["רביעי"], shifts: [], available: true, start_time: "08:00", end_time: "16:00" },
    { days: ["רביעי"], shifts: [], available: false, is_hard: true, start_time: "08:00", end_time: "12:00", constraint_type: "duty" },
  ];
  assert.deepEqual(blockedDaysOf(others), []);
  assert.deepEqual(withBlockedDays(others, []), others);
  assert.deepEqual(withBlockedDays(others, ["שני"]).slice(0, others.length), others);
});

test("a rule naming no day covers the week, and unticking one day names the rest", () => {
  const always = { days: [], shifts: [], available: false };
  assert.equal(blockedDaysOf([always]).length, 7);
  const next = withBlockedDays([always], ["ראשון", "שני", "שלישי", "חמישי", "שישי", "שבת"]);
  assert.deepEqual(next, [{ ...always, days: ["ראשון", "שני", "שלישי", "חמישי", "שישי", "שבת"] }]);
});
