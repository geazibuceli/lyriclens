import { useCallback, useEffect, useRef } from "react";
import { active, api } from "./api";
import type { Job, Models } from "./types";

export function useWorkspaceRefresh(
  setJobs: (jobs: Job[]) => void,
  setModels: (models: Models) => void,
  setError: (error: string) => void,
) {
  const refreshRef = useRef<() => Promise<void>>(async () => {});

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight: Promise<void> | undefined;
    let requested = false;
    let hasActiveJobs = false;
    const controller = new AbortController();

    function schedule() {
      clearTimeout(timer);
      if (!disposed && !document.hidden) {
        timer = setTimeout(() => void refresh(), hasActiveJobs ? 2500 : 30000);
      }
    }

    function refresh(): Promise<void> {
      if (disposed) return Promise.resolve();
      clearTimeout(timer);
      // A refresh requested after an edit must run after any older response.
      requested = true;
      if (inFlight) return inFlight;
      inFlight = (async () => {
        do {
          requested = false;
          const results = await Promise.allSettled([
            api<Job[]>("/jobs", { signal: controller.signal }),
            api<Models>("/models", { signal: controller.signal }),
          ]);
          if (disposed) return;
          const [jobs, models] = results;
          if (jobs.status === "fulfilled") {
            hasActiveJobs = jobs.value.some(
              (job) =>
                active(job) ||
                Object.values(job.translations ?? {}).some((translation) =>
                  ["queued", "processing"].includes(translation.state),
                ),
            );
            setJobs(jobs.value);
          }
          if (models.status === "fulfilled") setModels(models.value);
          for (const result of results) {
            if (result.status === "rejected") {
              setError((result.reason as Error).message);
              break;
            }
          }
        } while (requested && !disposed);
      })().finally(() => {
        inFlight = undefined;
        schedule();
      });
      return inFlight;
    }

    function visibilityChanged() {
      clearTimeout(timer);
      if (!document.hidden) void refresh();
    }

    refreshRef.current = refresh;
    document.addEventListener("visibilitychange", visibilityChanged);
    if (!document.hidden) void refresh();
    return () => {
      disposed = true;
      clearTimeout(timer);
      controller.abort();
      document.removeEventListener("visibilitychange", visibilityChanged);
    };
  }, [setJobs, setModels, setError]);

  return useCallback(() => refreshRef.current(), []);
}
