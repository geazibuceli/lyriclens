import React, { useState } from "react";
import type { Segment, Job, Models } from "./types";
import { active, api, clock } from "./api";

export function RegionRetry({
  job,
  pipeline,
  segments,
  models,
}: {
  models: Models | null;
  job: Job;
  pipeline: string;
  segments: Segment[];
}) {
  const sourceLanguage =
    job.results[pipeline]?.detected_language || job.requested_language;
  const [index, setIndex] = useState(0),
    [language, setLanguage] = useState(
      ["ko", "ja", "zh", "en", "es", "pt", "fr"].includes(sourceLanguage)
        ? sourceLanguage
        : "en",
    ),
    [modelProfile, setModelProfile] = useState("same"),
    [reduceHallucinations, setReduceHallucinations] = useState(
      job.inference?.hallucination_silence_threshold != null,
    ),
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
          reduce_hallucinations: reduceHallucinations,
          ...(modelProfile !== "same" ? { model_profile: modelProfile } : {}),
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
      <summary>Retranscribe an unclear passage</summary>
      <p className="muted">
        Retry unclear words with a prepared model and an explicit language.
        Recognition includes two seconds of surrounding audio and opens a
        separate result using the original timeline.
      </p>
      <div className="settings">
        <label>
          Retry model
          <select
            aria-label="Passage recognition model"
            value={modelProfile}
            onChange={(e) => setModelProfile(e.target.value)}
          >
            <option value="same">Same model as this result</option>
            {models?.profiles?.map((profile) => (
              <option
                key={profile.id}
                value={profile.id}
                disabled={!profile.prepared}
              >
                {profile.label}
                {profile.prepared ? "" : " (not prepared)"}
              </option>
            ))}
          </select>
        </label>
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
      <label>
        <input
          type="checkbox"
          checked={reduceHallucinations}
          onChange={(e) => setReduceHallucinations(e.target.checked)}
        />{" "}
        Reduce suspected hallucinations around gaps (experimental; may omit
        words)
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </details>
  );
}
