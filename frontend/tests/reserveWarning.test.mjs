import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(testDir, "../src/components/ManualSetup/reserveWarning.ts"), "utf8");
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const warning = await import(`data:text/javascript,${encodeURIComponent(outputText)}`);

test("reserve warning lists only reservists with future shifts", () => {
  const message = warning.reserveFutureWarning([
    { employee: "דנה", shifts: 2 },
    { employee: "יוסי", shifts: 0 },
    { employee: "רון", shifts: 1 },
  ]);

  assert.match(message, /3 משמרות עתידיות/);
  assert.match(message, /דנה — 2/);
  assert.match(message, /רון — 1/);
  assert.doesNotMatch(message, /יוסי/);
  assert.match(message, /לא מוחק שיבוצים/);
});

test("reserve warning stays quiet when nobody has future shifts", () => {
  assert.equal(warning.reserveFutureWarning([{ employee: "דנה", shifts: 0 }]), "");
});
