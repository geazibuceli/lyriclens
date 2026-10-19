import React, { useState, useEffect } from "react";
type Segment = {
  start: number;
  end: number;
  text: string;
  language?: string;
  language_source?: string;
};
export function SegmentTools({
  segments,
  index,
  change,
  stop,
}: {
  segments: Segment[];
  index: number;
  change: (segments: Segment[]) => void;
  stop: () => void;
}) {
  const segment = segments[index],
    next = segments[index + 1];
  const [time, setTime] = useState((segment.start + segment.end) / 2);
  const [cut, setCut] = useState(
    Math.floor(Array.from(segment.text).length / 2),
  );
  const [error, setError] = useState("");
  useEffect(() => {
    setTime((segment.start + segment.end) / 2);
    setCut(Math.floor(Array.from(segment.text).length / 2));
    setError("");
  }, [segment.start, segment.end, segment.text]);
  function split() {
    const chars = Array.from(segment.text);
    if (
      !Number.isFinite(time) ||
      time <= segment.start ||
      time >= segment.end ||
      !Number.isInteger(cut) ||
      cut < 0 ||
      cut > chars.length ||
      segments.length >= 1000
    ) {
      setError(
        "Choose an interior split time and a valid text character position (maximum 1000 segments).",
      );
      return;
    }
    stop();
    setError("");
    change([
      ...segments.slice(0, index),
      { ...segment, end: time, text: chars.slice(0, cut).join("") },
      { ...segment, start: time, text: chars.slice(cut).join("") },
      ...segments.slice(index + 1),
    ]);
  }
  function merge() {
    if (
      !next ||
      segment.language !== next.language ||
      segment.end > next.start ||
      segment.start >= next.start ||
      (segment.text + "\n" + next.text).length > 20000
    ) {
      setError(
        "Merge requires ordered, nonoverlapping segments with the same language and at most 20000 text characters.",
      );
      return;
    }
    stop();
    setError("");
    change([
      ...segments.slice(0, index),
      { ...segment, end: next.end, text: segment.text + "\n" + next.text },
      ...segments.slice(index + 2),
    ]);
  }
  return (
    <details className="segment-tools">
      <summary>Split or merge segment {index + 1}</summary>
      <p className="muted">
        Choose the time and text cut independently. Timing is manual. Merge
        keeps both texts with a newline and includes any gap.
      </p>
      <label>
        Split time (seconds)
        <input
          aria-label={`Segment ${index + 1} split seconds`}
          type="number"
          step="0.01"
          value={time}
          onChange={(e) => setTime(Number(e.target.value))}
        />
      </label>
      <label>
        Text cut (Unicode characters before split)
        <input
          aria-label={`Segment ${index + 1} text cut`}
          type="number"
          min="0"
          max={Array.from(segment.text).length}
          value={cut}
          onChange={(e) => setCut(Number(e.target.value))}
        />
      </label>
      <p className="split-preview">
        {Array.from(segment.text).slice(0, cut).join("")}
        <strong> | </strong>
        {Array.from(segment.text).slice(cut).join("")}
      </p>
      <button className="button small" onClick={split}>
        Split segment {index + 1}
      </button>{" "}
      <button className="text-button" disabled={!next} onClick={merge}>
        Merge segment {index + 1} with next
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
