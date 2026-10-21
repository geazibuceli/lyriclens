import React, { useRef, useState } from "react";
import { api } from "./api";

type Entry = { file: File; state: string; error?: string };

export function BatchUpload({
  language,
  pipeline,
  modelProfile,
  ready,
}: {
  language: string;
  pipeline: string;
  modelProfile: string;
  ready: boolean;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stopped = useRef(false);
  async function send() {
    setBusy(true);
    setError("");
    stopped.current = false;
    try {
      for (let index = 0; index < entries.length; index++) {
        if (stopped.current) break;
        if (entries[index].state === "accepted") continue;
        setEntries((current) =>
          current.map((entry, i) =>
            i === index
              ? { ...entry, state: "uploading", error: undefined }
              : entry,
          ),
        );
        const form = new FormData();
        form.append("file", entries[index].file);
        form.append("language", language);
        form.append("pipeline", pipeline);
        form.append("model_profile", modelProfile);
        try {
          await api("/jobs", { method: "POST", body: form });
          setEntries((current) =>
            current.map((entry, i) =>
              i === index ? { ...entry, state: "accepted" } : entry,
            ),
          );
        } catch (error) {
          setEntries((current) =>
            current.map((entry, i) =>
              i === index
                ? { ...entry, state: "failed", error: (error as Error).message }
                : entry,
            ),
          );
          // Stop on failure so a full server queue does not reject every remaining file.
          break;
        }
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="batch-upload">
      <summary>Transcribe multiple recordings</summary>
      <p>
        Choose up to 20 files. Each uses the language, model and listening mode
        selected above. Uploads run one at a time; accepted jobs appear in the
        library with their own progress and cancellation.
      </p>
      <label>
        Batch audio files
        <input
          type="file"
          multiple
          accept=".wav,.mp3,.flac,.m4a,.mp4"
          disabled={busy}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length > 20) {
              setError("Choose at most 20 recordings per batch.");
              return;
            }
            setError("");
            setEntries(files.map((file) => ({ file, state: "waiting" })));
          }}
        />
      </label>
      <ul aria-live="polite">
        {entries.map((entry, index) => (
          <li key={index}>
            {entry.file.name}: {entry.state}
            {entry.error ? ` — ${entry.error}` : ""}
          </li>
        ))}
      </ul>
      <p className="muted">
        If a request fails, uploads pause. Check the library before retrying a
        failed upload in case the server accepted it before the connection was
        lost. This pending file list stays in this open page only.
      </p>
      <button
        type="button"
        className="button small"
        disabled={
          busy || !ready || !entries.some((entry) => entry.state !== "accepted")
        }
        onClick={() => void send()}
      >
        Send pending recordings
      </button>
      {busy && (
        <button
          type="button"
          className="text-button"
          onClick={() => {
            stopped.current = true;
          }}
        >
          Stop after current upload
        </button>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
