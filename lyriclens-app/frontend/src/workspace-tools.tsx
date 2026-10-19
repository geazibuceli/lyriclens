import React, { useEffect, useState } from "react";

type Diagnostics = {
  checks: { name: string; ok: boolean; detail: string }[];
  note: string;
};
type Storage = {
  jobs: {
    id: string;
    filename: string;
    bytes: number | null;
    cache_bytes: number | null;
    active?: boolean;
    error?: string;
  }[];
  models: Record<string, number | null>;
  free_bytes: number;
  note: string;
};
const bytes = (value: number | null) =>
  value === null ? "Unavailable" : `${(value / 1024 / 1024).toFixed(1)} MiB`;
async function request<T>(path: string, method = "GET"): Promise<T> {
  const response = await fetch("/api" + path, { method });
  const result = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      result.detail || `Request failed (HTTP ${response.status})`,
    );
  return result;
}
export function WorkspaceTools() {
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [storage, setStorage] = useState<Storage | null>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function diagnose() {
    try {
      setDiagnostics(await request<Diagnostics>("/diagnostics"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void diagnose();
  }, []);
  async function measure() {
    setBusy(true);
    setError("");
    try {
      setStorage(await request<Storage>("/storage"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function clear(id: string) {
    setBusy(true);
    setError("");
    try {
      await request(`/jobs/${id}/cleanup-cache`, "POST");
      setStorage(await request<Storage>("/storage"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workspace-tools">
      <details>
        <summary>
          Environment checks{" "}
          {diagnostics
            ? `· ${diagnostics.checks.filter((c) => !c.ok).length} unavailable checks (including optional features)`
            : "· checking…"}
        </summary>
        <button className="text-button" onClick={diagnose}>
          Refresh environment checks
        </button>
        {diagnostics?.checks.map((check) => (
          <p key={check.name}>
            <strong>
              {check.name}: {check.ok ? "Ready" : "Setup needed"}
            </strong>
            <br />
            {check.detail}
          </p>
        ))}
        <p className="muted">{diagnostics?.note}</p>
      </details>
      <details>
        <summary>Local storage and cache</summary>
        <button className="text-button" disabled={busy} onClick={measure}>
          {busy ? "Working…" : "Measure local storage"}
        </button>
        {storage && (
          <>
            <p>{bytes(storage.free_bytes)} free on the data drive.</p>
            <p className="muted">{storage.note}</p>
            <ul>
              {Object.entries(storage.models).map(([name, size]) => (
                <li key={name}>
                  {name}: {bytes(size)}
                </li>
              ))}
            </ul>
            <p>
              Clear cache removes only generated decoded audio and vocal stems
              for that job. Original recordings, saved transcripts, translations
              and raw responses are kept. Generated audio can be rebuilt for
              future tasks.
            </p>
            <ul className="storage-jobs">
              {storage.jobs.map((job) => (
                <li key={job.id}>
                  <strong>{job.filename}</strong>
                  <span>
                    {bytes(job.bytes)} total · {bytes(job.cache_bytes)}{" "}
                    generated cache
                  </span>
                  <button
                    className="button small"
                    disabled={busy || job.active || !job.cache_bytes}
                    onClick={() => clear(job.id)}
                  >
                    Clear generated cache for {job.filename}
                  </button>
                  {job.error && <p>{job.error}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
      </details>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
