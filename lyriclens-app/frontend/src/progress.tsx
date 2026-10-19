import React, { useEffect, useState } from "react";

export function Elapsed({
  since,
  active,
  label = "Elapsed",
}: {
  since?: string;
  active: boolean;
  label?: string;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, since]);
  const start = since ? Date.parse(since) : NaN;
  if (!active || !Number.isFinite(start)) return null;
  return (
    <span>
      {label}: {Math.max(0, Math.floor((now - start) / 1000))}s
    </span>
  );
}
export function TaskProgress({
  job,
}: {
  job: {
    state: string;
    stage: string;
    started_at?: string;
    stage_history?: { stage: string; at: string }[];
  };
}) {
  const history = (job.stage_history ?? []).filter(
    (item) =>
      !job.started_at || Date.parse(item.at) >= Date.parse(job.started_at),
  );
  const active = job.state === "processing";
  return (
    <section className="task-progress" aria-label="Task progress">
      <p role="status">
        <strong>{job.stage}</strong> ·{" "}
        {job.state === "queued" ? (
          "Waiting for worker"
        ) : (
          <Elapsed
            since={job.started_at}
            active={active}
            label="Current attempt"
          />
        )}
      </p>
      <p className="muted">
        Stages report actual work; recognition and separation have no reliable
        percentage or remaining-time estimate.
      </p>
      {!!history.length && (
        <details>
          <summary>Stages in this attempt</summary>
          <ol>
            {history.map((item, i) => (
              <li key={`${item.at}-${i}`}>
                <strong>{item.stage}</strong> ·{" "}
                {new Date(item.at).toLocaleTimeString()}
                {i === history.length - 1 && active ? " · in progress" : ""}
                {i < history.length - 1
                  ? ` · ${Math.max(0, Math.round((Date.parse(history[i + 1].at) - Date.parse(item.at)) / 1000))}s`
                  : ""}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
