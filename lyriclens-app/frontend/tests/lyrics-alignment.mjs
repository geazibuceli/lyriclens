import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const code = ts.transpileModule(
  readFileSync(new URL("../src/lyrics-alignment.ts", import.meta.url), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;
const { alignLyrics } = await import(
  `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`
);
const source = [
  { start: 1, end: 5, text: "Hello, world!" },
  { start: 6, end: 10, text: "Hello world" },
];
const repeated = alignLyrics(["HELLO world", "hello world"], source, 12);
assert.deepEqual(
  repeated.map((s) => [s.start, s.end]),
  [
    [1, 6],
    [6, 10],
  ],
);
assert.equal(repeated[0].text, "HELLO world");
assert.throws(
  () => alignLyrics(["unrelated words"], source, 12),
  /Could not match/,
);
assert.throws(() => alignLyrics(["hello"], [], 12), /valid timestamps/);
assert.throws(() => alignLyrics(["!!!"], source, 12), /letters or numbers/);
assert.throws(
  () =>
    alignLyrics(
      ["hello"],
      [
        { start: 0, end: 4, text: "hello" },
        { start: 3, end: 8, text: "world" },
      ],
      10,
    ),
  /overlapping/,
);
const japanese = alignLyrics(
  ["君の声", "聞こえる"],
  [{ start: 2, end: 8, text: "君の声、聞こえる" }],
  10,
);
assert.deepEqual(
  japanese.map((s) => s.start),
  [2, 2 + 18 / 7],
);
const astral = alignLyrics(
  ["𠮷野", "声"],
  [{ start: 0, end: 3, text: "𠮷野声" }],
  3,
);
assert.equal(astral[1].start, 2);
console.log(
  "Lyrics alignment: repetition, punctuation, mismatch, invalid input, overlap and Unicode passed.",
);
