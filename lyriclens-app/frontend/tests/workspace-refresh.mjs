import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(new URL("../src/use-workspace-refresh.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText;
const timers = new Map();
const requests = [];
const updates = [];
const errors = [];
let cleanup;
let visibilityChanged;
let timerId = 0;
const document = {
  hidden: false,
  addEventListener: (_, handler) => (visibilityChanged = handler),
  removeEventListener: () => (visibilityChanged = undefined),
};
const react = {
  useCallback: (callback) => callback,
  useRef: (value) => ({ current: value }),
  useEffect: (effect) => (cleanup = effect()),
};
const api = {
  active: (job) => ["queued", "processing"].includes(job.state),
  api: (path, options) =>
    new Promise((resolve, reject) => {
      requests.push({ path, resolve, reject, signal: options.signal });
    }),
};
const module = { exports: {} };
new Function("require", "exports", "document", "setTimeout", "clearTimeout", code)(
  (name) => (name === "react" ? react : api),
  module.exports,
  document,
  (callback, delay) => {
    timers.set(++timerId, { callback, delay });
    return timerId;
  },
  (id) => timers.delete(id),
);
const flush = () => new Promise((resolve) => setImmediate(resolve));
function finish(jobs = []) {
  requests.shift().resolve(jobs);
  requests.shift().resolve({ prepared: true });
}
function tick(delay) {
  assert.equal(timers.size, 1);
  const [id, timer] = [...timers][0];
  assert.equal(timer.delay, delay);
  timers.delete(id);
  timer.callback();
}
const refresh = module.exports.useWorkspaceRefresh(
  (jobs) => updates.push(jobs),
  () => {},
  (error) => errors.push(error),
);
assert.equal(requests.length, 2);
finish();
await flush();
tick(30000);
finish([{ state: "processing" }]);
await flush();
tick(2500);
finish([{ state: "completed", translations: { en: { state: "queued" } } }]);
await flush();
tick(2500);
// Concurrent explicit refreshes queue one newer request, without overlapping.
const pending = refresh();
void refresh();
assert.equal(requests.length, 2);
finish();
await flush();
assert.equal(requests.length, 2);
finish();
await pending;
document.hidden = true;
visibilityChanged();
assert.equal(timers.size, 0);
document.hidden = false;
visibilityChanged();
assert.equal(requests.length, 2);
// One failed endpoint must not discard a successful library response.
requests.shift().resolve([{ state: "completed" }]);
requests.shift().reject(new Error("Models unavailable"));
await flush();
assert.deepEqual(updates.at(-1), [{ state: "completed" }]);
assert.deepEqual(errors, ["Models unavailable"]);
tick(30000);
const signal = requests[0].signal;
const updateCount = updates.length;
cleanup();
assert.equal(signal.aborted, true);
assert.equal(visibilityChanged, undefined);
finish();
await flush();
assert.equal(updates.length, updateCount);
assert.equal(timers.size, 0);
console.log("Workspace refresh: adaptive intervals, visibility, concurrency, partial failures and cleanup passed.");
