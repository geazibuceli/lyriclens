import React, { useMemo, useState } from "react";
import { alignLyrics } from "./lyrics-alignment";
import type { Segment } from "./types";

export function parseLyrics(
  text: string,
  mode: string,
  current: Segment[],
  duration: number,
): Segment[] {
  if (!Number.isFinite(duration) || duration <= 0)
    throw new Error("Audio duration is unavailable.");
  if (text.length > 2000000)
    throw new Error("Lyrics exceed the two-million-character limit.");
  const lines = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) throw new Error("Add at least one lyric line.");
  let segments: Segment[];
  if (mode === "lrc") {
    const timed: { start: number; text: string }[] = [];
    for (const line of lines) {
      if (/^\[(ar|ti|al|by|re|ve|length):[^\]]*\]$/i.test(line)) continue;
      const prefix = line.match(/^(?:\[\d+:\d{2}(?:\.\d{1,3})?\])+/)?.[0];
      if (!prefix)
        throw new Error(
          "Use timestamped LRC lines; offset and word timestamps are not supported.",
        );
      const lyric = line.slice(prefix.length).trim();
      if (/<\d+:\d{2}(?:\.\d+)?>/.test(lyric))
        throw new Error(
          "Enhanced word timestamps are not supported. Use passage-level LRC.",
        );
      for (const match of prefix.matchAll(
        /\[(\d+):(\d{2})(?:\.(\d{1,3}))?\]/g,
      )) {
        const start =
          Number(match[1]) * 60 +
          Number(match[2]) +
          Number(`0.${match[3] ?? 0}`);
        if (
          Number(match[2]) >= 60 ||
          !Number.isFinite(start) ||
          start < 0 ||
          start > duration ||
          (start === duration && !!lyric)
        )
          throw new Error(
            "LRC timestamps must be inside the audio, with seconds below 60.",
          );
        timed.push({ start, text: lyric });
        if (timed.length > 1000)
          throw new Error("Import at most 1000 timestamped lines.");
      }
    }
    timed.sort((a, b) => a.start - b.start);
    const grouped = new Map<number, string[]>();
    for (const line of timed)
      grouped.set(line.start, [
        ...(grouped.get(line.start) ?? []),
        ...(line.text ? [line.text] : []),
      ]);
    const entries = [...grouped.entries()];
    segments = entries.flatMap(([start, words], index) =>
      words.length
        ? [
            {
              start,
              end: entries[index + 1]?.[0] ?? duration,
              text: words.join("\n"),
            },
          ]
        : [],
    );
  } else {
    if (lines.length > 1000) throw new Error("Import at most 1000 lines.");
    if (mode === "align") return alignLyrics(lines, current, duration);
    if (mode === "existing") {
      if (lines.length !== current.length)
        throw new Error(
          `Provide exactly ${current.length} nonempty lines to keep the current passage times.`,
        );
      segments = current.map((segment, index) => ({
        ...segment,
        text: lines[index],
      }));
    } else {
      segments = lines.map((line, index) => ({
        start: (index * duration) / lines.length,
        end: ((index + 1) * duration) / lines.length,
        text: line,
      }));
    }
  }
  if (!segments.length) throw new Error("No lyric text found.");
  if (segments.some((segment) => segment.text.length > 20000))
    throw new Error("Each passage must contain at most 20000 characters.");
  return segments;
}

export function LyricsImport({
  segments,
  duration,
  apply,
  disabled,
}: {
  segments: Segment[];
  duration: number;
  apply: (segments: Segment[]) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState("existing");
  const [fileError, setFileError] = useState("");
  const [notice, setNotice] = useState("");
  const preview = useMemo(() => {
    try {
      return {
        segments: parseLyrics(text, mode, segments, duration),
        error: "",
      };
    } catch (error) {
      return { segments: [], error: (error as Error).message };
    }
  }, [text, mode, segments, duration]);
  return (
    <details className="lyrics-import">
      <summary>Import lyrics (TXT / LRC)</summary>
      <p>
        Replace the editor text with your own lyrics. Review the preview before
        applying; undo restores the previous editor. Save edits to update
        exports.
      </p>
      <label>
        Lyrics file
        <input
          type="file"
          accept=".txt,.lrc,text/plain"
          disabled={disabled}
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            setFileError("");
            setNotice("");
            if (file.size > 2000000) {
              setFileError("Choose a file smaller than 2 MB.");
              return;
            }
            try {
              setText(await file.text());
              if (file.name.toLowerCase().endsWith(".lrc")) setMode("lrc");
            } catch {
              setFileError("The lyrics file could not be read.");
            }
          }}
        />
      </label>
      <label>
        Lyrics text
        <textarea
          aria-label="Lyrics text"
          value={text}
          maxLength={2000000}
          disabled={disabled}
          onChange={(event) => {
            setText(event.target.value);
            setNotice("");
          }}
        />
      </label>
      <label>
        Import timing
        <select
          aria-label="Import timing"
          value={mode}
          disabled={disabled}
          onChange={(event) => {
            setMode(event.target.value);
            setNotice("");
          }}
        >
          <option value="existing">
            Keep current passage times (one line per passage)
          </option>
          <option value="align">
            Suggest timing from the existing transcript
          </option>
          <option value="even">
            Distribute lines evenly for manual synchronization
          </option>
          <option value="lrc">Use timestamps from LRC</option>
        </select>
      </label>
      <p className="muted">
        Timing suggestions match lyrics to recognized text in order and estimate
        positions within each passage. They do not analyze the audio again;
        review by listening. Even distribution is only a starting point. Adjust
        passage times while listening. LRC uses the next timestamp as the end; a
        blank timestamp ends the preceding passage.
      </p>
      {fileError && (
        <p role="alert" className="error">
          {fileError}
        </p>
      )}
      {text.trim() && preview.error && (
        <p role="alert" className="error">
          {preview.error}
        </p>
      )}
      {!!preview.segments.length && (
        <>
          <p>
            {preview.segments.length} passages ready to replace the current
            editor.
          </p>
          <ol className="import-preview">
            {preview.segments.slice(0, 5).map((segment, index) => (
              <li key={index}>
                {segment.start.toFixed(2)}–{segment.end.toFixed(2)}s:{" "}
                {segment.text}
              </li>
            ))}
          </ol>
        </>
      )}
      <button
        className="button small"
        disabled={disabled || !preview.segments.length || !!fileError}
        onClick={() => {
          apply(preview.segments);
          setText("");
          setNotice(
            "Lyrics applied to the editor. Review timing and save edits.",
          );
        }}
      >
        Apply imported lyrics
      </button>
      {notice && <p role="status">{notice}</p>}
    </details>
  );
}
