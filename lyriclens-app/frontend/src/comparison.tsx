import React, { useMemo, useState } from "react";
type Segment = { start: number; end: number; text: string };
type Result = { state: string; original: Segment[]; edited: Segment[] | null };
type Piece = { text: string; changed: boolean };

function differences(a: string, b: string): [Piece[], Piece[]] {
  if (a === b)
    return [[{ text: a, changed: false }], [{ text: b, changed: false }]];
  const tokenize = (text: string) =>
    typeof Intl.Segmenter === "function"
      ? Array.from(
          new Intl.Segmenter(undefined, { granularity: "word" }).segment(text),
          (s) => s.segment,
        )
      : Array.from(text);
  const left = tokenize(a),
    right = tokenize(b);
  if (left.length * right.length > 200000)
    return [[{ text: a, changed: true }], [{ text: b, changed: true }]];
  const width = right.length + 1;
  const table = new Uint16Array((left.length + 1) * width);
  for (let i = left.length - 1; i >= 0; i--)
    for (let j = right.length - 1; j >= 0; j--)
      table[i * width + j] =
        left[i] === right[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
  const output: [Piece[], Piece[]] = [[], []];
  let i = 0,
    j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && left[i] === right[j]) {
      output[0].push({ text: left[i++], changed: false });
      output[1].push({ text: right[j++], changed: false });
    } else if (
      j === right.length ||
      (i < left.length &&
        table[(i + 1) * width + j] >= table[i * width + j + 1])
    )
      output[0].push({ text: left[i++], changed: true });
    else output[1].push({ text: right[j++], changed: true });
  }
  return output;
}

function passages(direct: Segment[], vocals: Segment[]) {
  const events = [
    ...direct.map((segment) => ({ segment, side: 0 })),
    ...vocals.map((segment) => ({ segment, side: 1 })),
  ].sort((a, b) => a.segment.start - b.segment.start);
  const groups: {
    start: number;
    end: number;
    sides: [Segment[], Segment[]];
  }[] = [];
  for (const { segment, side } of events) {
    let group = groups.at(-1);
    if (!group || segment.start >= group.end) {
      group = { start: segment.start, end: segment.end, sides: [[], []] };
      groups.push(group);
    }
    group.end = Math.max(group.end, segment.end);
    group.sides[side].push(segment);
  }
  return groups.map((group) => {
    const texts = group.sides.map((side) => side.map((s) => s.text).join("\n"));
    return {
      ...group,
      texts,
      changed: texts[0] !== texts[1],
      pieces: differences(texts[0], texts[1]),
    };
  });
}

export function TranscriptComparison({
  results,
  seek,
}: {
  results: Record<string, Result>;
  seek: (time: number) => void;
}) {
  const [onlyDifferent, setOnlyDifferent] = useState(true);
  const direct = results.direct,
    vocals = results.vocals;
  const signature = JSON.stringify([
    direct?.edited ?? direct?.original ?? [],
    vocals?.edited ?? vocals?.original ?? [],
  ]);
  const groups = useMemo(() => {
    const [a, b] = JSON.parse(signature) as [Segment[], Segment[]];
    return passages(a, b);
  }, [signature]);
  if (direct?.state !== "completed" || vocals?.state !== "completed")
    return null;
  const changed = groups.filter((group) => group.changed).length;
  return (
    <details className="transcript-comparison" open>
      <summary>
        Compare saved transcripts · {changed}{" "}
        {changed === 1 ? "passage differs" : "passages differ"}
      </summary>
      <p className="muted">
        Compare saved wording from the original audio and isolated vocals.
        Highlights show differences in passages with overlapping times. Save
        edits before comparing, and listen to check the wording.
      </p>
      <label className="comparison-filter">
        <input
          type="checkbox"
          checked={onlyDifferent}
          onChange={(e) => setOnlyDifferent(e.target.checked)}
        />
        Show only differences
      </label>
      {!changed && <p>No text differences in the saved transcripts.</p>}
      {groups
        .filter((group) => !onlyDifferent || group.changed)
        .map((group, index) => (
          <section
            className="comparison-passage"
            key={index}
            aria-label={`Comparison passage ${index + 1}`}
          >
            <button className="timestamp" onClick={() => seek(group.start)}>
              {group.start.toFixed(2)}–{group.end.toFixed(2)}s
            </button>
            <div className="comparison-columns">
              {group.pieces.map((pieces, side) => (
                <div key={side}>
                  <h4>{side === 0 ? "Original audio" : "Isolated vocals"}</h4>
                  <p>
                    {pieces.length ? (
                      pieces.map((piece, i) =>
                        piece.changed ? (
                          <mark key={i}>{piece.text}</mark>
                        ) : (
                          <React.Fragment key={i}>{piece.text}</React.Fragment>
                        ),
                      )
                    ) : (
                      <em>No segment in this time range</em>
                    )}
                  </p>
                </div>
              ))}
            </div>
          </section>
        ))}
    </details>
  );
}
