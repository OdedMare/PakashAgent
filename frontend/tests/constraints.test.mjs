import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/lib/constraints.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { constraintBlocksSlot } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

// A מכלול duty as the server projects it: a duty with no hours (D44).
const duty = {
  employee: "דנה", constraint_date: "2026-11-10", shift_name: "", available: false,
  start_time: "", end_time: "", is_hard: true, reason: "מטבח", source: "complex",
  constraint_type: "duty",
};
const slot = (start_time, end_time) => ({ shift_name: "x", start_time, end_time });

test("a מכלול duty paints the whole day and the night reaching into it", () => {
  assert.equal(constraintBlocksSlot([duty], "דנה", "2026-11-10", slot("07:00", "15:00")), true);
  assert.equal(constraintBlocksSlot([duty], "דנה", "2026-11-10", slot("23:00", "07:00")), true);
  assert.equal(constraintBlocksSlot([duty], "דנה", "2026-11-09", slot("23:00", "07:00")), true);
});

test("the evening before, the next morning and someone else stay open", () => {
  assert.equal(constraintBlocksSlot([duty], "דנה", "2026-11-09", slot("15:00", "23:00")), false);
  assert.equal(constraintBlocksSlot([duty], "דנה", "2026-11-11", slot("07:00", "15:00")), false);
  assert.equal(constraintBlocksSlot([duty], "יוסי", "2026-11-10", slot("07:00", "15:00")), false);
});
