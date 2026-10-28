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

const handover = "16:00";

test("each round type is read back from the row it writes", () => {
  for (const shape of ["friday", "wednesday", "week"]) {
    assert.equal(shapes.shapeOf(shapes.shapeRow(shape, handover, {}), handover), shape);
  }
  // 11/3 is the server's default: no row, unless a dated exception asks for it.
  assert.equal(shapes.shapeRow("thursday", handover, {}), null);
  assert.equal(shapes.shapeOf(undefined, handover), "thursday");
  assert.equal(shapes.shapeOf(shapes.shapeRow("thursday", handover, {}, true), handover), "thursday");
  assert.equal(shapes.shapeOf({ start_day: -2, start_time: "10:00", end_day: 1, end_time: "16:00" }, handover), "custom");
});

test("a type is named by its days on base and at home", () => {
  assert.equal(shapes.shapeLabel("thursday", 2).title, "11/3");
  assert.equal(shapes.shapeLabel("friday", 2).title, "12/2");
  assert.equal(shapes.shapeLabel("wednesday", 2).title, "10/4");
  assert.equal(shapes.shapeLabel("week", 3).title, "שבוע בבסיס, שבועיים בבית");
});

test("a week tiles Sunday to Sunday on the handover", () => {
  const week = shapes.shapeRow("week", handover, {});
  assert.deepEqual([week.start_day, week.start_time, week.end_day, week.end_time], [-6, "16:00", 1, "16:00"]);
  assert.equal(shapes.windowSentence(week), "מראשון 16:00 עד ראשון שאחרי 16:00");
});

test("any day of a weekend names its Saturday", () => {
  assert.equal(shapes.saturdayOf("2027-02-11"), "2027-02-13");
  assert.equal(shapes.saturdayOf("2027-02-13"), "2027-02-13");
  assert.equal(shapes.saturdayOf("2027-02-14"), "2027-02-20");
});
