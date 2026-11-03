import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/components/ManualSetup/rosterGroups.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const roster = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

const services = { standard: "תקן", overlap: "נחפף/ת", reserve: "מילואים" };
const shifts = ["בוקר", "ערב", "לילה"];
const person = (service, shiftList, counts = true, exitKey = "round|א") => ({ service, counts, shifts: shiftList, exitKey, exitLabel: exitKey });
const people = [
  person("standard", ["בוקר"]),
  person("reserve", ["ערב", "לילה"], true, "triplet|ב"),
  person("overlap", [], false),
  person("reserve", ["בוקר"]),
];
const all = () => true;

test("only reservists are left when the filter asks for them", () => {
  const [group] = roster.groupRoster(people, "none", services, shifts, (p) => p.service === "reserve");
  assert.deepEqual(group.indices, [1, 3]);
});

test("status groups follow the status order and skip empty ones", () => {
  const groups = roster.groupRoster(people, "service", services, shifts, all);
  assert.deepEqual(groups.map((g) => [g.label, g.indices]), [["תקן", [0]], ["נחפף/ת", [2]], ["מילואים", [1, 3]]]);
});

test("a person allowed on two shifts is under both, and nobody is lost", () => {
  const groups = roster.groupRoster(people, "shift", services, shifts, all);
  assert.deepEqual(groups.map((g) => [g.key, g.indices]), [["בוקר", [0, 3]], ["ערב", [1]], ["לילה", [1]], [roster.NO_SHIFT, [2]]]);
});

test("staffing splits who fills the quota from who does not", () => {
  const groups = roster.groupRoster(people, "staffing", services, shifts, all);
  assert.deepEqual(groups.map((g) => [g.key, g.indices]), [["counts", [0, 1, 3]], ["extra", [2]]]);
});

test("exit groups are by pattern and group letter", () => {
  const groups = roster.groupRoster(people, "exit", services, shifts, all);
  assert.deepEqual(groups.map((g) => [g.key, g.indices]), [["round|א", [0, 2, 3]], ["triplet|ב", [1]]]);
});
