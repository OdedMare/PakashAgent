import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/components/Employee/shiftTimes.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { timedShifts, splitByNow, untilLabel, hoursLabel } = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

const shift = (date, name) => ({ date, shift: name, hours: 8, is_on_call: false, weekday: "יום" });

function view({ shifts, slots = [], profile = [], teammates = [] }) {
  return {
    schedule: { slots },
    shifts: profile,
    teammates,
    summary: { shifts },
  };
}

test("hours come from the slot before the profile", () => {
  const [row] = timedShifts(view({
    shifts: [shift("2026-12-01", "בוקר")],
    slots: [{ slot_date: "2026-12-01", shift_name: "בוקר", start_time: "08:00:00", end_time: "16:00:00" }],
    profile: [{ name: "בוקר", start_time: "07:00", end_time: "15:00" }],
  }));
  assert.equal(hoursLabel(row), "08:00–16:00");
});

test("the profile fills in when the slot carries no hours", () => {
  const [row] = timedShifts(view({
    shifts: [shift("2026-12-01", "בוקר")],
    profile: [{ name: "בוקר", start_time: "7:00", end_time: "15:00" }],
  }));
  assert.equal(hoursLabel(row), "07:00–15:00");
  assert.equal(row.start.getHours(), 7);
});

test("a night ends the next morning", () => {
  const [row] = timedShifts(view({
    shifts: [shift("2026-12-01", "לילה")],
    profile: [{ name: "לילה", start_time: "23:00", end_time: "07:00" }],
  }));
  assert.equal(row.end.getDate(), 2);
  assert.equal(row.end.getHours(), 7);
});

test("no known hours shows none and spans the whole date", () => {
  const [row] = timedShifts(view({ shifts: [shift("2026-12-01", "תורנות")] }));
  assert.equal(hoursLabel(row), "");
  assert.equal(row.end.getTime() - row.start.getTime(), 24 * 3600 * 1000);
});

test("teammates ride along on their own shift", () => {
  const [row] = timedShifts(view({
    shifts: [shift("2026-12-01", "בוקר")],
    teammates: [{ date: "2026-12-01", shift: "בוקר", with: ["יוסי"] }],
  }));
  assert.deepEqual(row.with, ["יוסי"]);
});

test("the shift under way is current, the next one is next, ended ones are past", () => {
  const shifts = timedShifts(view({
    shifts: [shift("2026-12-03", "בוקר"), shift("2026-12-01", "בוקר"), shift("2026-12-02", "בוקר")],
    profile: [{ name: "בוקר", start_time: "07:00", end_time: "15:00" }],
  }));
  const split = splitByNow(shifts, new Date(2026, 11, 2, 10, 0));
  assert.equal(split.current.date, "2026-12-02");
  assert.equal(split.next.date, "2026-12-03");
  assert.deepEqual(split.past.map((s) => s.date), ["2026-12-01"]);
  assert.deepEqual(split.upcoming.map((s) => s.date), ["2026-12-02", "2026-12-03"]);
});

test("the countdown reads in minutes, hours today, tomorrow, then days", () => {
  const now = new Date(2026, 11, 1, 9, 0);
  assert.equal(untilLabel(new Date(2026, 11, 1, 9, 20), now), "בעוד 20 דקות");
  assert.equal(untilLabel(new Date(2026, 11, 1, 11, 0), now), "היום, בעוד שעתיים");
  assert.equal(untilLabel(new Date(2026, 11, 1, 15, 0), now), "היום, בעוד 6 שעות");
  assert.equal(untilLabel(new Date(2026, 11, 2, 7, 0), now), "מחר");
  assert.equal(untilLabel(new Date(2026, 11, 3, 7, 0), now), "בעוד יומיים");
  assert.equal(untilLabel(new Date(2026, 11, 5, 7, 0), now), "בעוד 4 ימים");
});
