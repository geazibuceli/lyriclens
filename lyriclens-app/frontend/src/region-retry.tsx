import React, { useState } from "react";
import type { Segment, Job } from "./types";
import { active, api, clock } from "./api";

export function RegionRetry({
  job,
  pipeline,
  segments,
}: {
  job: Job;
  pipeline: string;
  segments: Segment[];
}) {
  const [index, setIndex] = useState(0),
    [language, setLanguage] = useState("en"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  if (!segments.length || active(job)) return null;
  async function retry() {
    setBusy(true);
    setError("");
    try {
      const segment = segments[Math.min(index, segments.length - 1)];
      const child = await api<Job>(`/jobs/${job.id}/retranscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          language,
          pipeline,
          start: segment.start,
          end: segment.end,
          context_seconds: 2,
        }),
      });
      window.location.assign(`?job=${child.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <details className="region-retry">
      <summary>
        Experimental: retranscribe a passage in another language
      </summary>
      <p className="muted">
        Choose a language for this passage. Recognition includes two seconds of
        surrounding audio and opens a separate result using the original
        timeline.
      </p>
      <div className="settings">
        <label>
          Passage
          <select
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
          >
            {segments.map((s, i) => (
              <option key={i} value={i}>
                {clock(s.start)}–{clock(s.end)} · {s.text.slice(0, 30)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Language instruction
          <select
            aria-label="Passage language instruction"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {Object.entries({
              ko: "Korean",
              ja: "Japanese",
              zh: "Mandarin Chinese",
              en: "English",
              es: "Spanish",
              pt: "Portuguese",
              fr: "French",
            }).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button className="button small" disabled={busy} onClick={retry}>
        {busy ? "Queuing…" : "Retranscribe passage"}
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </details>
  );
}
