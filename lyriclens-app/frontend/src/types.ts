import type { Translation } from "./translation";

export type Segment = {
  start: number;
  end: number;
  text: string;
  language?: string;
  language_source?: string;
};
export type Result = {
  state: string;
  original: Segment[];
  edited: Segment[] | null;
  detected_language?: string;
  language_source?: string;
  seconds: number;
  warnings?: string[];
  error?: string;
};
export type Job = {
  id: string;
  filename: string;
  title?: string;
  model_profile?: string;
  inference?: { hallucination_silence_threshold?: number | null };
  state: string;
  stage: string;
  requested_language: string;
  results: Record<string, Result>;
  translations?: Record<string, Translation>;
  audio?: { duration: number };
  error?: string;
  created_at: string;
  started_at?: string;
  stage_history?: { stage: string; at: string }[];
  pipelines: string[];
  imported_snapshot?: boolean;
};
export type Models = {
  prepared: boolean;
  separation_prepared: boolean;
  ffmpeg_available: boolean;
  languages: Record<string, string>;
  max_seconds: number;
  max_bytes: number;
  model_id: string;
  profiles: { id: string; label: string; prepared: boolean; note: string }[];
};
