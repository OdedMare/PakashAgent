import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = path.dirname(fileURLToPath(import.meta.url));

// Run the actual hooks with controlled effects and API responses, without a DOM.
function hook(file, name, api, args = [], stored = {}) {
  const slots = [], effects = [], modules = new Map();
  let cursor = 0;
  const memo = (fn, deps) => {
    const i = cursor++;
    if (!slots[i] || deps.some((dep, n) => dep !== slots[i].deps[n])) slots[i] = { value: fn(), deps };
    return slots[i].value;
  };
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial;
      return [slots[i], (next) => { slots[i] = typeof next === "function" ? next(slots[i]) : next; }];
    },
    useRef: (initial) => memo(() => ({ current: initial }), []),
    useMemo: memo,
    useCallback: (fn, deps) => memo(() => fn, deps),
    useEffect(fn, deps) {
      const i = cursor++;
      if (!slots[i] || deps.some((dep, n) => dep !== slots[i].deps[n])) {
        const previous = slots[i];
        slots[i] = { deps };
        effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); });
      }
    },
  };
  const storage = { getItem: (key) => stored[key] ?? null, setItem: (key, value) => { stored[key] = value; } };
  function load(filename) {
    if (modules.has(filename)) return modules.get(filename);
    const loaded = { exports: {} };
    modules.set(filename, loaded.exports);
    const code = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    }).outputText;
    vm.runInNewContext(code, {
      module: loaded, exports: loaded.exports, setTimeout, clearTimeout, AbortController, Error,
      crypto: webcrypto,
      window: { sessionStorage: storage, localStorage: storage },
      require(id) {
        if (id === "react") return react;
        if (id === "@/services/api") return api;
        if (id.startsWith(".")) return load(path.resolve(path.dirname(filename), `${id}.ts`));
        throw new Error(`Unexpected import: ${id}`);
      },
    }, { filename });
    return loaded.exports;
  }
  const fn = load(path.resolve(testDir, "../src", file))[name];
  const render = () => {
    cursor = 0;
    const value = fn(...args);
    effects.splice(0).forEach((effect) => effect());
    return value;
  };
  render();
  return { render, settle: async () => { await new Promise(setImmediate); return render(); } };
}

const plan = { kind: "changes", schedule_id: "old-week", operations: [{ date: "2026-10-05" }], constraints: [] };
const conversation = (status) => ({ id: "chat", messages: [{ id: "plan", status, payload: { plan } }] });
async function chat(api, onApplied = async () => {}) {
  const h = hook("components/Management/useManagerChat.ts", "useManagerChat", {
    listManagerChats: async () => [{ id: "chat" }], readManagerChat: async () => conversation("pending"), ...api,
  }, ["team", "old-week", "2026-10-04", "", onApplied]);
  await h.settle();
  return h;
}
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

test("approval remains busy until the saved plan has refreshed the board", async () => {
  const refresh = deferred();
  let received;
  const h = await chat({ applyManagerPlan: async () => conversation("applied") }, async (p) => {
    received = p;
    await refresh.promise;
  });
  const applying = h.render().apply("plan", false);
  await h.settle();
  assert.equal(h.render().busy, true);
  assert.equal(received, plan);
  refresh.resolve();
  await applying;
  assert.equal(h.render().busy, false);
  assert.equal(h.render().error, null);
});

test("a successful HTTP response without an applied plan cannot announce success", async () => {
  let refreshed = false;
  const h = await chat({ applyManagerPlan: async () => conversation("pending") }, async () => { refreshed = true; });
  await h.render().apply("plan", false);
  assert.equal(refreshed, false);
  assert.match(h.render().error, /לא אישר/);
});

test("lost approval responses recover the committed plan without another write", async () => {
  let writes = 0, refreshed = 0, reads = 0;
  const h = await chat({
    readManagerChat: async () => conversation(reads++ ? "applied" : "pending"),
    applyManagerPlan: async () => { writes++; throw new Error("response lost"); },
  }, async () => { refreshed++; });
  await h.render().apply("plan", true);
  assert.equal(writes, 1);
  assert.equal(refreshed, 1);
  assert.equal(h.render().error, null);
});

test("a request that never arrived is retried once, and its lost response is recovered", async () => {
  let writes = 0, refreshed = 0;
  const h = await chat({
    readManagerChat: async () => conversation(writes === 2 ? "applied" : "pending"),
    applyManagerPlan: async (chatId, messageId, exceptions) => {
      assert.deepEqual([chatId, messageId, exceptions], ["chat", "plan", true]);
      writes++;
      throw new Error("connection lost");
    },
  }, async () => { refreshed++; });
  await h.render().apply("plan", true);
  assert.equal(writes, 2);
  assert.equal(refreshed, 1);
  assert.equal(h.render().error, null);
});

test("persistent failures stop after one retry and keep the plan pending", async () => {
  let writes = 0;
  const h = await chat({ applyManagerPlan: async () => { writes++; throw new Error("offline"); } });
  await h.render().apply("plan", false);
  assert.equal(writes, 2);
  assert.equal(h.render().chat.messages[0].status, "pending");
  assert.equal(h.render().error, "offline");
});

test("a failed board refresh can be retried without applying the plan again", async () => {
  let writes = 0, reads = 0;
  const h = await chat({ applyManagerPlan: async () => { writes++; return conversation("applied"); } }, async () => {
    if (++reads === 1) throw new Error("overview unavailable");
  });
  await h.render().apply("plan", false);
  assert.equal(h.render().chat.messages[0].status, "applied");
  assert.equal(h.render().refreshPending, plan);
  assert.match(h.render().error, /התוכנית נשמרה/);
  await h.render().retryRefresh();
  assert.equal(writes, 1);
  assert.equal(reads, 2);
  assert.equal(h.render().refreshPending, null);
  assert.equal(h.render().error, null);
});

test("text approval uses the same refresh and recovery path", async () => {
  let refreshes = 0;
  const h = await chat({ sendManagerMessage: async () => conversation("applied") }, async () => {
    if (++refreshes === 1) throw new Error("refresh failed");
  });
  assert.equal(await h.render().send("מאשר"), false);
  assert.equal(h.render().refreshPending, plan);
  assert.equal(await h.render().retryRefresh(), true);
  assert.equal(refreshes, 2);
});

test("double clicks share one in-flight approval", async () => {
  const response = deferred();
  let writes = 0;
  const h = await chat({ applyManagerPlan: async () => { writes++; return response.promise; } });
  const first = h.render().apply("plan", false);
  const second = h.render().apply("plan", false);
  assert.equal(writes, 1);
  response.resolve(conversation("applied"));
  await Promise.all([first, second]);
});

test("board refresh reads the changed week and its calendar range before navigating", async () => {
  let version = "before";
  const weeks = [], spans = [];
  const h = hook("components/Board/useBoard.ts", "useBoard", {
    scheduleAt: async (date) => { weeks.push(date); return { id: version }; },
    schedulesBetween: async (start, end) => { spans.push([start, end]); return [{ id: version }]; },
  }, [], { "pakash.board.week": "2026-09-06", "pakash.board.view": "month" });
  await h.settle();
  version = "after";
  await h.render().refresh("2026-10-05");
  const board = h.render();
  assert.equal(board.focus, "2026-10-05");
  assert.equal(board.weekSchedule.id, "after");
  assert.equal(board.rangeSchedules[0].id, "after");
  assert.equal(weeks[1], "2026-10-04");
  assert.deepEqual(spans[1], ["2026-09-27", "2026-10-31"]);
});

test("board refresh rejects failed reads instead of treating them as an empty schedule", async () => {
  let failed = false;
  const h = hook("components/Board/useBoard.ts", "useBoard", {
    scheduleAt: async () => { if (failed) throw new Error("offline"); return { id: "week" }; },
  }, [], { "pakash.board.week": "2026-10-05" });
  await h.settle();
  failed = true;
  await assert.rejects(h.render().refresh(), /offline/);
});

test("an older overview response cannot replace the read made after approval", async () => {
  const old = deferred();
  let reads = 0, failed = false;
  const fresh = { schedule: null, employees: [] };
  const h = hook("components/Management/useManagement.ts", "useManagement", {
    scheduleOverview: async () => {
      if (++reads === 1) return old.promise;
      if (failed) throw new Error("offline");
      return fresh;
    },
  });
  await h.render().refresh(true);
  old.resolve({ schedule: null, employees: ["stale"] });
  await h.settle();
  assert.equal(h.render().overview, fresh);
  failed = true;
  await assert.rejects(h.render().refresh(true), /offline/);
  assert.equal(h.render().overview, fresh);
});
