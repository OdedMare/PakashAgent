// Run with: node tests/markdown.mjs
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

// Compile the real shared component using the project's existing TypeScript.
const temp = await mkdtemp(new URL("../.markdown-check-", import.meta.url).pathname);
try {
  const source = await readFile(new URL("../src/components/Markdown.tsx", import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext },
  });
  const file = join(temp, "Markdown.mjs");
  await writeFile(file, outputText);
  const { Markdown } = await import(pathToFileURL(file).href);
  const render = (text) => renderToStaticMarkup(React.createElement(Markdown, { text }));

  const rich = render("## סיכום\n\n**דנה** זמינה.\n\n- בוקר\n- ערב\n\n| עובד | שעות |\n| --- | --- |\n| דנה | 8 |\n\n```js\nconst hours = 8;\n```");
  for (const tag of ["h2", "strong", "ul", "table", "pre", "code"]) assert.ok(rich.includes(`<${tag}`), `Missing ${tag}`);
  assert.ok(rich.includes("העתקת קוד"));
  assert.ok(rich.includes('dir="ltr"'));
  const untrusted = render('<script>alert(1)</script>\n\n[click](javascript:alert)\n\n![image](https://example.com/tracker.png)');
  assert.ok(!untrusted.includes("<script"));
  assert.ok(!untrusted.includes("javascript:"));
  assert.ok(!untrusted.includes("<img"));
  const link = render("[reference](https://example.com)");
  assert.ok(link.includes('href="https://example.com"'));
  assert.ok(link.includes('rel="noopener noreferrer"'));
  assert.ok(render("עברית\nשורה נוספת").includes("עברית\nשורה נוספת"));
  console.log("Markdown rendering and untrusted content checks passed.");
} finally {
  await rm(temp, { recursive: true, force: true });
}
