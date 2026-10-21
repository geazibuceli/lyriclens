import React, { useState } from "react";
import { Music2 } from "lucide-react";
import type { Job } from "./types";
import { api } from "./api";

export function Library({
  jobs,
  selected,
  select,
}: {
  jobs: Job[];
  selected: string | null;
  select: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState("");
  const [language, setLanguage] = useState("");
  const normalize = (value: string) =>
    value.normalize("NFC").toLocaleLowerCase();
  const visible = jobs.filter(
    (job) =>
      normalize(`${job.title ?? ""} ${job.filename}`).includes(
        normalize(query.trim()),
      ) &&
      (!state || job.state === state) &&
      (!language || job.requested_language === language),
  );
  return (
    <>
      <div className="library-filters">
        <label>
          Search library
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label>
          Job status
          <select
            aria-label="Job status"
            value={state}
            onChange={(event) => setState(event.target.value)}
          >
            <option value="">All statuses</option>
            {[
              "queued",
              "processing",
              "completed",
              "failed",
              "canceled",
              "interrupted",
            ].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          Requested language
          <select
            aria-label="Requested language"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
          >
            <option value="">All languages</option>
            {Object.entries({
              auto: "Automatic",
              ko: "Korean",
              ja: "Japanese",
              zh: "Mandarin Chinese",
              en: "English",
              es: "Spanish",
              pt: "Portuguese",
              fr: "French",
            }).map(([code, name]) => (
              <option value={code} key={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <p role="status">
          {visible.length} of {jobs.length} recordings
        </p>
      </div>
      <nav aria-label="Transcription library">
        {!visible.length ? (
          <p className="library-empty">
            {jobs.length
              ? "No recordings match these filters."
              : "Your listening sessions will live here."}
          </p>
        ) : (
          visible.map((job) => (
            <button
              className={`job-link ${selected === job.id ? "selected" : ""}`}
              key={job.id}
              onClick={() => select(job.id)}
            >
              <Music2 size={17} />
              <span>
                {job.title || job.filename}
                <small>
                  {job.state} · {new Date(job.created_at).toLocaleDateString()}
                </small>
              </span>
            </button>
          ))
        )}
      </nav>
    </>
  );
}

export function JobTitle({ job, refresh }: { job: Job; refresh: () => void }) {
  const [title, setTitle] = useState(job.title ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <details className="job-title">
      <summary>Rename recording</summary>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            await api(`/jobs/${job.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ title }),
            });
            refresh();
          } catch (error) {
            setError((error as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Recording title
          <input
            value={title}
            maxLength={200}
            disabled={busy}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <p className="muted">
          The original filename stays unchanged. Leave blank to display it
          again.
        </p>
        <button
          className="button small"
          disabled={busy || title.trim() === (job.title ?? "")}
        >
          Save title
        </button>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </details>
  );
}
