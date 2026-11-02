// Run with `npm test` (node --test with TypeScript type stripping).
import assert from "node:assert/strict";
import test from "node:test";

import { WEEKDAYS, weekdayName, weekdayNames } from "../src/components/ManualSetup/days.ts";

test("strips the optional יום prefix", () => {
  assert.equal(weekdayName("יום שני"), "שני");
  assert.equal(weekdayName("  יום שלישי "), "שלישי");
  assert.equal(weekdayName("שבת"), "שבת");
});

test("a prefixed shift reads as every stored day ticked", () => {
  // A shift's days spelled with the prefix on all but שבת.
  const stored = ["יום ראשון", "יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "שבת"];
  const selected = weekdayNames(stored);
  assert.deepEqual(selected, WEEKDAYS);
  for (const day of WEEKDAYS) assert.ok(selected.includes(day), day);
});

test("mixed spellings collapse to one entry per day, in week order", () => {
  assert.deepEqual(weekdayNames(["שבת", "יום שני", "שני", "ראשון"]), ["ראשון", "שני", "שבת"]);
});

test("saving unchanged days is a fixed point", () => {
  const once = weekdayNames(["יום שני", "יום שלישי", "שבת"]);
  assert.deepEqual(weekdayNames(once), once);
});

test("values that are not weekdays are kept, junk is dropped", () => {
  assert.deepEqual(weekdayNames(["חג", "יום שני", "", 3, null]), ["שני", "חג"]);
  assert.deepEqual(weekdayNames(undefined), []);
});
