import type { Job } from "./types";

export const active = (job: Job) =>
  ["queued", "processing"].includes(job.state);
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, init);
  if (!response.ok) {
    const data = await response.json().catch(() => ({
      detail: `Request failed (HTTP ${response.status}). Please retry.`,
    }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the submitted values",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
