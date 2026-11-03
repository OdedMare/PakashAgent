import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/lib/warningSummary.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const summary = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

const warning = (code, details, message = "") => ({
  code, severity: "warning", message, employee: "דנה", date: "2026-11-05", shift: "ערב", details,
});

test("a constraint names its kind, its hours and its reason", () => {
  const row = warning(
    "unavailable",
    { is_hard: true, start_time: "08:00", end_time: "14:00", constraint_type: "availability" },
    "דנה משובץ לערב בתאריך 2026-11-05 בזמן אילוץ (08:00–14:00) (מילואים).",
  );
  assert.equal(summary.warningHeadline(row), "אילוץ \u206608:00–14:00\u2069 · מילואים");
});

test("a time window in the last parentheses is not mistaken for a reason", () => {
  const row = warning(
    "unavailable",
    { is_hard: true, start_time: "08:00", end_time: "14:00" },
    "דנה משובץ לערב בתאריך 2026-11-05 בזמן אילוץ (08:00–14:00).",
  );
  assert.equal(summary.warningHeadline(row), "אילוץ \u206608:00–14:00\u2069");
  const open = warning("unavailable", { is_hard: true, start_time: "08:00" }, "דנה משובץ לערב בזמן אילוץ (החל מ-08:00).");
  assert.equal(summary.warningHeadline(open), "אילוץ מ-08:00");
});

test("the reason the audit puts in details wins over the sentence", () => {
  const row = warning("unavailable", { is_hard: true, reason: "יום הולדת" }, "דנה משובץ לערב בזמן אילוץ (משהו אחר).");
  assert.equal(summary.warningHeadline(row), "אילוץ · יום הולדת");
});

test("duty and soft availability read differently from a hard constraint", () => {
  assert.match(summary.warningHeadline(warning("unavailable", { constraint_type: "duty", is_hard: true })), /^תורנות חוסמת/);
  assert.match(summary.warningHeadline(warning("unavailable", { is_hard: false })), /^העדפה/);
});

test("the numbers that broke a rule are on the line", () => {
  assert.equal(
    summary.warningHeadline(warning("short_rest", { rest_hours: 6, minimum: 8, earlier_shift: "לילה" })),
    "רק 6 ש׳ מנוחה (נדרש 8) אחרי לילה",
  );
  assert.equal(
    summary.warningHeadline(warning("short_rest", { rest_hours: -2, minimum: 8, earlier_shift: "בוקר" })),
    "חופף למשמרת בוקר",
  );
  assert.equal(summary.warningHeadline(warning("over_hours", { hours: 52.5, limit: 48 })), "52.5 ש׳ השבוע (תקרה 48)");
  assert.equal(summary.warningHeadline(warning("consecutive", { days: 13, limit: 11 })), "13 ימים ברצף (מקס׳ 11)");
  assert.equal(
    summary.warningHeadline(warning("below_level", { competence: "weak", required: "high" })),
    "רמה חלשה · המשמרת דורשת גבוהה ומעלה",
  );
  assert.equal(
    summary.warningHeadline(warning("below_level", { competence: "high", required: "excellent" })),
    "רמה גבוהה · המשמרת דורשת מצטיינת",
  );
  assert.equal(summary.warningHeadline(warning("cross_rotation", { rotation_group: "ב" })), "בבית לפי הסבב (קבוצה ב)");
});

test("an unknown code falls back to the audit's own sentence", () => {
  assert.equal(summary.warningHeadline(warning("something_new", {}, "משהו חדש.")), "משהו חדש.");
});

test("a constraint the board found itself is described the same way", () => {
  const row = {
    id: "1", employee: "דנה", constraint_date: "2026-11-05", shift_name: "", available: false,
    start_time: "08:00", end_time: "14:00", is_hard: true, reason: "מילואים", source: "manager",
    constraint_type: "availability",
  };
  assert.equal(summary.constraintHeadline(row), "אילוץ \u206608:00–14:00\u2069 · מילואים");
  assert.equal(summary.constraintSentence("דנה", row), "דנה — נרשם/ה אילוץ למשמרת הזו, בשעות \u206608:00–14:00\u2069, סיבה: מילואים.");
});
