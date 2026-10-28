import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/components/ManualSetup/closureShapes.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const shapes = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

const clock = shapes.clockOf([{ start_time: "16:00", end_time: "00:00" }, { start_time: "08:00", end_time: "16:00" }]);

test("the clock turns over on the day's first shift", () => {
  assert.deepEqual(clock, { start: "08:00", end: "16:00" });
  assert.deepEqual(shapes.clockOf([]), { start: "08:00", end: "12:00" });
});

test("each shape is read back from the row it writes", () => {
  for (const shape of ["friday", "week"]) {
    assert.equal(shapes.shapeOf(shapes.shapeRow(shape, clock, {}), clock), shape);
  }
  assert.equal(shapes.shapeRow("thursday", clock, {}), null);
  assert.equal(shapes.shapeOf(undefined, clock), "thursday");
  assert.equal(shapes.shapeOf(shapes.shapeRow("thursday", clock, {}, true), clock), "thursday");
  assert.equal(shapes.shapeOf({ start_day: -3, start_time: "08:00", end_day: 1, end_time: "16:00" }, clock), "custom");
});

test("a week tiles Sunday to Sunday on one clock", () => {
  const week = shapes.shapeRow("week", clock, {});
  assert.deepEqual([week.start_day, week.start_time, week.end_day, week.end_time], [-6, "16:00", 1, "16:00"]);
  assert.equal(shapes.windowSentence(week), "מראשון 16:00 עד ראשון שאחרי 16:00");
});

test("any day of a weekend names its Saturday", () => {
  assert.equal(shapes.saturdayOf("2027-02-11"), "2027-02-13");
  assert.equal(shapes.saturdayOf("2027-02-13"), "2027-02-13");
  assert.equal(shapes.saturdayOf("2027-02-14"), "2027-02-20");
});
