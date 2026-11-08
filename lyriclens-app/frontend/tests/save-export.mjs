import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(new URL("../src/transcript-editor.tsx", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React } },
).outputText;
const original = [{ start: 0, end: 1, text: "Original" }];
const edited = [{ start: 0, end: 1, text: "Latest Unicode lyrics: café 世界" }];
const flush = () => new Promise((resolve) => setImmediate(resolve));

async function scenario(format, failure) {
  const state = [];
  const refs = [];
  let stateIndex = 0;
  let refIndex = 0;
  let segments = original;
  let finishSave;
  const calls = [];
  const react = {
    createElement: (type, props, ...children) => ({ type, props, children }),
    useMemo: (factory) => factory(),
    useRef: (value) => {
      const index = refIndex++;
      return (refs[index] ??= { current: value });
    },
    useState: (value) => {
      const index = stateIndex++;
      if (!(index in state)) state[index] = value;
      return [state[index], (next) => (state[index] = next)];
    },
  };
  const mocks = {
    react: { ...react, default: react },
    "./history": { useHistory: () => ({ value: segments, set: () => {} }) },
    "./drafts": { useDraft: () => null },
    "./review-flags": { reviewFlags: () => [] },
    "./listening-studio": { useAudioTime: () => 0 },
    "./api": {
      clock: () => "00:00",
      api: async (_, options) => {
        calls.push(JSON.parse(options.body));
        await new Promise((resolve) => (finishSave = resolve));
        if (failure === "save") throw new Error("Save rejected");
      },
    },
    "./download-transcript": {
      downloadTranscript: async (...args) => {
        calls.push(args);
        if (failure === "download") throw new Error("Download rejected");
      },
    },
  };
  const exports = {};
  new Function("require", "exports", code)((name) => mocks[name] ?? {}, exports);
  function render() {
    stateIndex = refIndex = 0;
    return exports.Transcript({
      job: { id: "fixture", requested_language: "en", audio: { duration: 1 } },
      pipeline: "direct",
      result: { state: "completed", original, seconds: 1 },
      audio: { current: null },
      saved: () => calls.push("saved"),
    });
  }
  function nodes(tree) {
    if (!tree || typeof tree !== "object") return [];
    if (Array.isArray(tree)) return tree.flatMap(nodes);
    return [tree, ...tree.children.flatMap(nodes)];
  }
  render();
  segments = edited;
  const button = nodes(render()).find(
    (node) => node.type === "button" &&
      node.children.join("") === `Save and export ${format.toUpperCase()}`,
  );
  assert.ok(button);
  button.props.onClick();
  button.props.onClick();
  assert.equal(calls.length, 1, "Repeated clicks must not submit twice");
  assert.deepEqual(calls[0], { pipeline: "direct", segments: edited });
  finishSave();
  await flush();
  assert.deepEqual(segments, edited, "Failures must preserve editor contents");
  if (failure === "save") {
    assert.equal(calls.length, 1, "A failed save must prevent export");
    assert.equal(state[0], JSON.stringify(original));
    assert.equal(state[1], "Save rejected");
  } else {
    assert.deepEqual(calls.slice(1), ["saved", ["fixture", "direct", format]]);
    assert.equal(state[0], JSON.stringify(edited));
    assert.equal(state[1], failure ? "Download rejected" : "");
  }
  assert.equal(state[2], false, "Controls must be released after completion");
}

for (const format of ["txt", "json", "srt", "lrc"]) await scenario(format);
await scenario("txt", "save");
await scenario("lrc", "download");
console.log("Save/export: four formats, sequencing, duplicate clicks and failure recovery passed.");
