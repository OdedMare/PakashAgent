import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));

function loadApi(fetch, timers = { setTimeout, clearTimeout }) {
  const module = { exports: {} };
  const source = fs.readFileSync(
    path.resolve(testDir, "../src/services/api.ts"), "utf8",
  );
  const code = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  vm.runInNewContext(code, {
    module,
    exports: module.exports,
    fetch,
    performance: { now: () => 0 },
    console: { debug() {}, error() {} },
    URLSearchParams,
    AbortController,
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
  }, { filename: "api.ts" });
  return module.exports;
}

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  };
}

test("replacement search starts once and polls short reads until complete", async () => {
  const result = { employee: "דנה", slots: [], dates: [], free_dates: [], error: "" };
  const replies = [
    response(202, { id: "job-1", status: "queued" }),
    response(200, { id: "job-1", status: "running" }),
    response(200, { id: "job-1", status: "complete", result }),
  ];
  const calls = [];
  const api = loadApi(async (url, options = {}) => {
    calls.push([url, options.method ?? "GET"]);
    return replies.shift();
  }, {
    setTimeout(fn) { queueMicrotask(fn); return 1; },
    clearTimeout() {},
  });

  assert.deepEqual(
    await api.getReplacementOptions("דנה", "2026-10-05", "2026-10-06"),
    result,
  );
  assert.deepEqual(calls, [
    ["/api/agent/replacements/searches", "POST"],
    ["/api/agent/replacements/searches/job-1", "GET"],
    ["/api/agent/replacements/searches/job-1", "GET"],
  ]);
});

test("changing the form aborts replacement polling", async () => {
  const calls = [];
  const api = loadApi(async (url, options = {}) => {
    calls.push(url);
    return response(202, { id: "job-2", status: "queued" });
  });
  const controller = new AbortController();
  const pending = api.getReplacementOptions(
    "דנה", "2026-10-05", "2026-10-06", { signal: controller.signal },
  );
  await new Promise(setImmediate);
  controller.abort();

  await assert.rejects(pending, (error) => error.name === "AbortError");
  assert.deepEqual(calls, ["/api/agent/replacements/searches"]);
});
