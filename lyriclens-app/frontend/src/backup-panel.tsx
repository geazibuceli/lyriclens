import React, { useState } from "react";

export function BackupPanel({
  jobId,
  active,
  onRestored,
}: {
  jobId?: string;
  active: boolean;
  onRestored: (id: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function restore() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/backups/restore", {
        method: "POST",
        body,
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Backup could not be restored",
        );
      setFile(null);
      onRestored(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="backup-panel">
      <summary>Backup and restore a job</summary>
      <p>
        Save your edits, then download the recording, transcripts, translations,
        raw responses and job settings in one archive. Model files, cache and
        browser drafts are stored separately. Keep backups private.
      </p>
      {jobId && !active && (
        <a className="button small" href={`/api/jobs/${jobId}/backup`}>
          Download this job backup
        </a>
      )}
      {active && <p>Stop active work before creating a consistent backup.</p>}
      <p>
        Restore adds a separate job to your library. To transcribe the recording
        again, upload it as a new job.
      </p>
      <label>
        Job backup ZIP
        <input
          aria-label="Job backup ZIP"
          type="file"
          accept=".zip"
          disabled={busy}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <button
        className="button small"
        disabled={!file || busy}
        onClick={restore}
      >
        {busy ? "Restoring backup…" : "Restore as a separate job"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
