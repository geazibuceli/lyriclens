import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AudioLines,
  ArrowUpRight,
  Upload,
  Plus,
  Music2,
  Trash2,
  Headphones,
  Download,
  Check,
  LoaderCircle,
  X,
  Languages,
} from "lucide-react";
import "./style.css";
import { TranslationPanel, type Translation } from "./translation";
import { ReviewPlayback, type RepeatRange } from "./playback";
import { TranscriptComparison } from "./comparison";
import { useHistory } from "./history";
import { reviewFlags } from "./review-flags";
import { WorkspaceTools } from "./workspace-tools";
import { TaskProgress } from "./progress";
import { useDraft, validSegments } from "./drafts";
import { SegmentTools } from "./segment-tools";
import { BackupPanel } from "./backup-panel";

type Segment = {
  start: number;
  end: number;
  text: string;
  language?: string;
  language_source?: string;
};
type Result = {
  state: string;
  original: Segment[];
  edited: Segment[] | null;
  detected_language?: string;
  language_source?: string;
  seconds: number;
  warnings?: string[];
  error?: string;
};
type Job = {
  id: string;
  filename: string;
  model_profile?: string;
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
type Models = {
  prepared: boolean;
  separation_prepared: boolean;
  ffmpeg_available: boolean;
  languages: Record<string, string>;
  max_seconds: number;
  max_bytes: number;
  model_id: string;
  profiles: { id: string; label: string; prepared: boolean; note: string }[];
};
const active = (job: Job) => ["queued", "processing"].includes(job.state);
async function api<T>(path: string, init?: RequestInit): Promise<T> {
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
const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;

function RegionRetry({
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
        Your language instruction applies to the chosen passage with two seconds
        of surrounding context. Results open as a separate job with timestamps
        in the original clip. No segment language is inferred.
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

function Transcript({
  job,
  pipeline,
  result,
  seek,
  saved,
  repeat,
  repeating,
  stopReview,
}: {
  job: Job;
  pipeline: string;
  result: Result;
  seek: (n: number) => void;
  saved: () => void;
  repeat: (segment: Segment, index: number) => void;
  repeating: RepeatRange | null;
  stopReview: () => void;
}) {
  const history = useHistory<Segment[]>(result.edited ?? result.original ?? []);
  const segments = history.value,
    setSegments = history.set;
  const [savedVersion, setSavedVersion] = useState(JSON.stringify(segments));
  const dirty = JSON.stringify(segments) !== savedVersion;
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [multilingualBusy, setMultilingualBusy] = useState(false);
  const [query, setQuery] = useState("");
  const draft = useDraft(
    `${job.id}:${pipeline}`,
    segments,
    savedVersion,
    setSegments,
    validSegments,
    result.state === "completed",
  );
  const matches = query.trim()
    ? segments
        .map((s, i) => ({ s, i }))
        .filter(({ s }) =>
          s.text
            .normalize("NFC")
            .toLocaleLowerCase()
            .includes(query.trim().normalize("NFC").toLocaleLowerCase()),
        )
    : [];
  if (result.state === "failed")
    return (
      <section className="transcript">
        <h3>{pipeline === "direct" ? "Original audio" : "Isolated vocals"}</h3>
        <p role="alert" className="error">
          {result.error}
        </p>
      </section>
    );
  async function save() {
    setSaving(true);
    setError("");
    try {
      await api(`/jobs/${job.id}/edit`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline, segments }),
      });
      setSavedVersion(JSON.stringify(segments));
      saved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function recognizePassages() {
    setMultilingualBusy(true);
    setError("");
    try {
      const child = await api<Job>(
        `/jobs/${job.id}/retranscribe-multilingual`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pipeline, default_language: "auto" }),
        },
      );
      window.location.assign(`?job=${child.id}`);
    } catch (e) {
      setError((e as Error).message);
      setMultilingualBusy(false);
    }
  }
  return (
    <section
      className="transcript"
      onKeyDown={(event) => {
        if ((event.target as HTMLElement).closest(".translation-panel")) return;
        if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
        const key = event.key.toLowerCase();
        if (key === "z" || key === "y") {
          event.preventDefault();
          if (saving) return;
          stopReview();
          if (key === "y" || event.shiftKey) history.redo();
          else history.undo();
        } else if (event.key === "Enter" && dirty && !saving) {
          event.preventDefault();
          void save();
        }
      }}
    >
      {draft}
      <div className="transcript-search">
        <label>
          Search transcript
          <input
            type="search"
            aria-label="Search transcript"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {query.trim() && (
          <>
            <p>{matches.length} matching segments (including unsaved text)</p>
            <ul>
              {matches.map(({ s, i }) => (
                <li key={i}>
                  <button
                    className="text-button"
                    onClick={() => {
                      document
                        .getElementById(`segment-${job.id}-${pipeline}-${i}`)
                        ?.scrollIntoView({
                          block: "center",
                          behavior: "smooth",
                        });
                      seek(s.start);
                    }}
                  >
                    Segment {i + 1} at {clock(s.start)}: {s.text.slice(0, 100)}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div className="edit-history">
        <button
          className="button small"
          disabled={!history.canUndo || saving}
          onClick={() => {
            stopReview();
            history.undo();
          }}
        >
          Undo transcript edit
        </button>
        <button
          className="button small"
          disabled={!history.canRedo || saving}
          onClick={() => {
            stopReview();
            history.redo();
          }}
        >
          Redo transcript edit
        </button>
        <p className="muted">
          Ctrl/Cmd+Z: undo ? Ctrl/Cmd+Shift+Z: redo ? Ctrl/Cmd+Enter: save.
          History stays in this open editor.
        </p>
      </div>
      <div className="result-heading">
        <div>
          <span className="eyebrow">
            {pipeline === "direct" ? "DIRECT PIPELINE" : "VOCAL-ASSISTED"}
          </span>
          <h3>
            {pipeline === "direct" ? "Original audio" : "Isolated vocals"}
          </h3>
        </div>
        <span className="badge">{result.seconds.toFixed(1)}s</span>
      </div>
      <p className="muted">
        {result.language_source === "user-instructed passage languages"
          ? "Languages: saved segment instructions"
          : result.language_source === "user instruction"
            ? "Language instruction"
            : "Estimated language"}
        :{" "}
        <strong>
          {result.language_source === "user-instructed passage languages"
            ? "See segment labels"
            : result.detected_language || "Unknown"}
        </strong>{" "}
        · Segment timing is approximate
      </p>
      <button
        className="button small translation-shortcut"
        onClick={() => {
          const panel = document.getElementById(
            `translation-${job.id}-${pipeline}`,
          ) as HTMLDetailsElement | null;
          if (panel) {
            panel.open = true;
            panel.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }}
      >
        <Languages size={16} />
        Translate transcript
      </button>
      {result.warnings?.map((w) => (
        <p className="notice" key={w}>
          {w}
        </p>
      ))}
      <RegionRetry job={job} pipeline={pipeline} segments={segments} />
      <div className="multilingual-controls">
        <p className="muted">
          Two or more languages? Set the language on each passage below, adjust
          its boundaries and save. Labels are your instructions, not automatic
          language detection.
        </p>
        <button
          className="button small"
          disabled={
            dirty ||
            multilingualBusy ||
            new Set(segments.map((s) => s.language).filter(Boolean)).size < 2
          }
          onClick={recognizePassages}
        >
          {multilingualBusy
            ? "Queuing passages…"
            : "Retranscribe saved multilingual passages"}
        </button>
        <p className="muted">
          Creates a separate result from saved passage intervals. Gaps outside
          those intervals are omitted; unlabeled passages use automatic
          detection.
        </p>
      </div>
      {!segments.length && (
        <p>No words returned. You can add and edit a segment below.</p>
      )}
      <div className="segments">
        {segments.map((s, i) => (
          <div className="segment" key={i}>
            <div className="segment-controls">
              <button
                className="timestamp"
                onClick={() => seek(s.start)}
                aria-label={`Play from ${s.start} seconds`}
              >
                {clock(s.start)}
              </button>
              <button
                className="text-button segment-repeat"
                aria-label={`Repeat segment ${i + 1}`}
                aria-pressed={
                  repeating?.pipeline === pipeline && repeating.index === i
                }
                disabled={
                  !Number.isFinite(s.start) ||
                  !Number.isFinite(s.end) ||
                  s.start < 0 ||
                  s.end <= s.start ||
                  s.end > (job.audio?.duration ?? 0)
                }
                onClick={() =>
                  repeating?.pipeline === pipeline && repeating.index === i
                    ? stopReview()
                    : repeat(s, i)
                }
              >
                Repeat
              </button>
            </div>
            <div
              className="segment-content"
              id={`segment-${job.id}-${pipeline}-${i}`}
            >
              {reviewFlags(segments, i).map((flag) => (
                <p className="review-flag" key={flag}>
                  Review suggestion: {flag}. This is not proof of an error.
                </p>
              ))}
              <label className="segment-language">
                Segment {i + 1} language
                <select
                  aria-label={`Segment ${i + 1} language`}
                  value={s.language ?? ""}
                  onChange={(e) => {
                    setSegments(
                      segments.map((segment, n) =>
                        n === i
                          ? {
                              ...segment,
                              language: e.target.value || undefined,
                              language_source: e.target.value
                                ? "user instruction"
                                : undefined,
                            }
                          : segment,
                      ),
                    );
                  }}
                >
                  <option value="">
                    Unspecified (use clip/fallback language)
                  </option>
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
              <div className="timing">
                <label>
                  Start{" "}
                  <input
                    aria-label={`Segment ${i + 1} start seconds`}
                    type="number"
                    min="0"
                    step="0.01"
                    value={s.start}
                    onChange={(e) => {
                      stopReview();

                      setSegments(
                        segments.map((v, n) =>
                          n === i ? { ...v, start: Number(e.target.value) } : v,
                        ),
                      );
                    }}
                  />
                </label>
                <label>
                  End{" "}
                  <input
                    aria-label={`Segment ${i + 1} end seconds`}
                    type="number"
                    min="0"
                    step="0.01"
                    value={s.end}
                    onChange={(e) => {
                      stopReview();

                      setSegments(
                        segments.map((v, n) =>
                          n === i ? { ...v, end: Number(e.target.value) } : v,
                        ),
                      );
                    }}
                  />
                </label>
                <button
                  className="icon"
                  aria-label={`Remove segment ${i + 1}`}
                  onClick={() => {
                    stopReview();

                    setSegments(segments.filter((_, n) => i !== n));
                  }}
                >
                  <X size={14} />
                </button>
              </div>
              <SegmentTools
                segments={segments}
                index={i}
                change={setSegments}
                stop={stopReview}
              />
              <textarea
                aria-label={`Segment ${i + 1} transcript`}
                value={s.text}
                onChange={(e) => {
                  setSegments(
                    segments.map((v, n) =>
                      n === i ? { ...v, text: e.target.value } : v,
                    ),
                  );
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <button
        className="text-button"
        onClick={() => {
          setSegments([
            ...segments,
            {
              start: Math.min(
                segments.at(-1)?.end ?? 0,
                Math.max(0, (job.audio?.duration || 1) - 0.01),
              ),
              end: job.audio?.duration || 1,
              text: "",
            },
          ]);
        }}
      >
        + Add segment
      </button>
      <div className="result-actions">
        <button
          className="button small"
          disabled={saving || !dirty}
          onClick={save}
        >
          {saving ? (
            "Saving…"
          ) : dirty ? (
            "Save edits"
          ) : (
            <>
              <Check size={14} /> Saved
            </>
          )}
        </button>
        <details>
          <summary>
            <Download size={14} /> Export
          </summary>
          <div className="exports">
            {["txt", "json", "srt"].map((format) => (
              <a
                key={format}
                href={`/api/jobs/${job.id}/export?pipeline=${pipeline}&format=${format}`}
              >
                {format.toUpperCase()}
              </a>
            ))}
            <a
              href={`/api/jobs/${job.id}/export?pipeline=${pipeline}&format=txt&original=true`}
            >
              Original TXT
            </a>
            <a href={`/api/jobs/${job.id}/raw?pipeline=${pipeline}`}>
              Raw response
            </a>
          </div>
        </details>
      </div>
      {dirty && <p className="muted">Save edits before exporting.</p>}
      <TranslationPanel
        jobId={job.id}
        pipeline={pipeline}
        translations={job.translations ?? {}}
        sourceLanguage={result.detected_language ?? job.requested_language}
        sourceDirty={dirty}
        sourceLanguages={(result.edited ?? result.original ?? [])
          .filter((s) => s.text.trim())
          .map((s) => s.language)}
        refresh={saved}
        seek={seek}
      />
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([]),
    [selected, setSelected] = useState<string | null>(
      new URLSearchParams(window.location.search).get("job"),
    ),
    [models, setModels] = useState<Models | null>(null);
  const [file, setFile] = useState<File | null>(null),
    [language, setLanguage] = useState("auto"),
    [pipeline, setPipeline] = useState("direct"),
    [modelProfile, setModelProfile] = useState("configured");
  const [error, setError] = useState(""),
    [deleting, setDeleting] = useState(false),
    [busy, setBusy] = useState(false),
    [drag, setDrag] = useState(false);
  const audio = useRef<HTMLAudioElement>(null),
    input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState("");
  const [repeatRange, setRepeatRange] = useState<RepeatRange | null>(null);
  useEffect(() => {
    setRepeatRange(null);
  }, [selected]);
  function stopReview() {
    setRepeatRange(null);
    audio.current?.pause();
  }
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const job = jobs.find((j) => j.id === selected);
  const chosenModelPrepared =
    models?.profiles?.find((p) => p.id === modelProfile)?.prepared ??
    models?.prepared;
  async function refresh() {
    try {
      const [j, m] = await Promise.all([
        api<Job[]>("/jobs"),
        api<Models>("/models"),
      ]);
      setJobs(j);
      setModels(m);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 2500);
    return () => clearInterval(timer);
  }, []);
  function choose(f: File | undefined) {
    if (f) {
      setFile(f);
      setError("");
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("language", language);
      form.append("pipeline", pipeline);
      form.append("model_profile", modelProfile);
      const j = await api<Job>("/jobs", { method: "POST", body: form });
      setSelected(j.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!job || deleting) return;
    setDeleting(true);
    setError("");
    try {
      if (audio.current) {
        audio.current.pause();
        audio.current.removeAttribute("src");
        audio.current.load();
      }
      await api(`/jobs/${job.id}`, { method: "DELETE" });
      setSelected(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  }
  async function retranscribe() {
    if (!job) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/jobs/${job.id}/audio`);
      if (!response.ok) throw new Error("Audio could not be loaded");
      setFile(new File([await response.blob()], job.filename));
      setModelProfile(job.model_profile ?? "configured");
      setSelected(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app">
      <aside>
        <a className="brand" href="/" aria-label="LyricLens home">
          <span className="brand-icon">
            <AudioLines size={23} />
          </span>
          lyriclens<span className="brand-dot">.</span>
        </a>
        <button
          className="new-button"
          onClick={() => {
            setSelected(null);
            setFile(null);
          }}
        >
          <Plus size={17} /> New transcription
        </button>
        <p className="nav-label">
          YOUR LIBRARY <span>{jobs.length}</span>
        </p>
        <nav aria-label="Transcription library">
          {jobs.length === 0 ? (
            <p className="library-empty">
              Your listening sessions
              <br />
              will live here.
            </p>
          ) : (
            jobs.map((j) => (
              <button
                className={`job-link ${selected === j.id ? "selected" : ""}`}
                key={j.id}
                onClick={() => setSelected(j.id)}
              >
                <Music2 size={17} />
                <span>
                  {j.filename}
                  <small>
                    {j.state} ·{" "}
                    {new Date(j.created_at).toLocaleDateString("en")}
                  </small>
                </span>
              </button>
            ))
          )}
        </nav>
        <div className="local-card">
          <span className="live-dot" />
          <strong>Your audio stays yours.</strong>
          <p>Local processing. No cloud inference. No lyrics lookup.</p>
        </div>
        <div className="sidebar-foot">
          A little closer to every word.
          <Headphones size={17} />
        </div>
      </aside>
      <main>
        <header>
          <span className="breadcrumb">
            Workspace <span>/</span>{" "}
            {job ? "Transcription" : "New transcription"}
          </span>
          <span className="local-pill">
            <span className="live-dot" /> LOCAL WORKSPACE
          </span>
        </header>
        <div className="main-content">
          <div className="intro">
            <span className="eyebrow">LISTEN BEYOND THE MELODY</span>
            <h1>
              {job ? (
                "Make every word yours."
              ) : (
                <>
                  The music you love.
                  <br />
                  <em>The words you’re missing.</em>
                </>
              )}
            </h1>
            <p>
              {job
                ? "Listen, review, and refine your transcription. Your original result is always preserved."
                : "Turn a music clip into an editable transcript, then translate it locally into another language."}
            </p>
            {!job && (
              <p className="muted">
                Already have a transcription? Open it in Your Library and choose{" "}
                <strong>Translate transcript</strong>.
              </p>
            )}
          </div>
          <WorkspaceTools />
          <BackupPanel
            jobId={job?.id}
            active={
              !!job &&
              (active(job) ||
                Object.values(job.translations ?? {}).some((t) =>
                  ["queued", "processing"].includes(t.state),
                ))
            }
            onRestored={(id) => {
              setSelected(id);
              void refresh();
            }}
          />
          {error && (
            <div className="error global-error" role="alert">
              {error}
              <button
                className="icon"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!job ? (
            <form onSubmit={submit}>
              <div
                className={`upload ${drag ? "drag" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDrag(true);
                }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDrag(false);
                  choose(e.dataTransfer.files[0]);
                }}
              >
                <div className="upload-art">
                  <AudioLines size={35} strokeWidth={1.4} />
                  <span className="orbit orbit-one" />
                  <span className="orbit orbit-two" />
                </div>
                <h2>{file ? file.name : "Drop a little music here"}</h2>
                <p>
                  {file
                    ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready when you are`
                    : "Drag your audio file here, or choose one from your device."}
                </p>
                <button
                  type="button"
                  className="button outline"
                  onClick={() => input.current?.click()}
                >
                  <Upload size={16} />
                  {file ? "Choose another file" : "Choose audio file"}
                </button>
                <input
                  ref={input}
                  aria-label="Upload music clip"
                  type="file"
                  accept=".wav,.mp3,.flac,.m4a,.mp4"
                  onChange={(e) => choose(e.target.files?.[0])}
                />
                <span className="format-note">
                  WAV, MP3, FLAC, M4A, MP4 <span>·</span> Up to{" "}
                  {(models?.max_seconds ?? 600) / 60} minutes <span>·</span>{" "}
                  {Math.round((models?.max_bytes ?? 157286400) / 1024 / 1024)}{" "}
                  MB max
                </span>
              </div>
              {file && (
                <audio
                  className="preview-audio"
                  controls
                  src={preview}
                  aria-label="Uploaded clip preview"
                />
              )}
              <div className="settings">
                <label>
                  Audio language
                  <select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    <option value="auto">Auto-detect language</option>
                    {Object.entries(
                      models?.languages ?? {
                        ko: "Korean",
                        ja: "Japanese",
                        zh: "Mandarin Chinese",
                        en: "English",
                        es: "Spanish",
                        pt: "Portuguese",
                        fr: "French",
                      },
                    ).map(([key, name]) => (
                      <option value={key} key={key}>
                        {name}
                      </option>
                    ))}
                  </select>
                  <small>You can correct the language and run it again.</small>
                </label>
                <label>
                  Listening mode
                  <select
                    value={pipeline}
                    onChange={(e) => setPipeline(e.target.value)}
                  >
                    <option value="direct">Original audio</option>
                    <option value="vocals">Isolated vocals</option>
                    <option value="both">Compare both pipelines</option>
                  </select>
                  <small>
                    Vocal isolation can help, or introduce artifacts.
                  </small>
                </label>
                <label>
                  Recognition model
                  <select
                    aria-label="Recognition model"
                    value={modelProfile}
                    onChange={(e) => setModelProfile(e.target.value)}
                  >
                    {(
                      models?.profiles ?? [
                        {
                          id: "configured",
                          label: "Configured model",
                          prepared: models?.prepared ?? false,
                          note: "",
                        },
                      ]
                    ).map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {profile.label}
                        {profile.prepared ? "" : " (not prepared)"}
                      </option>
                    ))}
                  </select>
                  <small>
                    {models?.profiles?.find((p) => p.id === modelProfile)
                      ?.note ??
                      "Model output is always preserved. Review singing against the audio."}
                  </small>
                </label>
              </div>
              {models && (!chosenModelPrepared || !models.ffmpeg_available) && (
                <p className="notice">
                  Setup needed:{" "}
                  {!models.ffmpeg_available ? "install FFmpeg. " : ""}
                  {!chosenModelPrepared
                    ? "Prepare the transcription model using the setup guide."
                    : ""}{" "}
                  Processing will be available once setup is complete.
                </p>
              )}
              {pipeline !== "direct" && !models?.separation_prepared && (
                <p className="notice">
                  The optional vocal model must be prepared first. Original
                  audio mode works independently.
                </p>
              )}
              <div className="submit-row">
                <span>
                  <Headphones size={16} /> Best with one clear lead vocalist
                </span>
                <button
                  className="button"
                  disabled={
                    !file ||
                    busy ||
                    !chosenModelPrepared ||
                    !models?.ffmpeg_available
                  }
                  type="submit"
                >
                  {busy ? (
                    <LoaderCircle className="spin" size={17} />
                  ) : (
                    <AudioLines size={17} />
                  )}{" "}
                  Transcribe clip <ArrowUpRight size={17} />
                </button>
              </div>
            </form>
          ) : (
            <div>
              <div className="clip-bar">
                <Music2 size={21} />
                <div>
                  <strong>{job.filename}</strong>
                  <small>
                    {job.state} · {job.stage}
                  </small>
                </div>
                {active(job) ? (
                  <button
                    className="text-button"
                    onClick={async () => {
                      try {
                        await api(`/jobs/${job.id}/cancel`, { method: "POST" });
                        await refresh();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    Cancel
                  </button>
                ) : (
                  <button
                    className="icon"
                    onClick={remove}
                    disabled={
                      deleting ||
                      Object.values(job.translations ?? {}).some((t) =>
                        ["queued", "processing"].includes(t.state),
                      )
                    }
                    title="Cancel active translation before deleting this job"
                    aria-label="Delete job and its audio"
                  >
                    <Trash2 size={18} />
                  </button>
                )}
              </div>
              {!job.imported_snapshot &&
                ["interrupted", "canceled", "failed", "completed"].includes(
                  job.state,
                ) &&
                job.pipelines.some(
                  (p) => job.results[p]?.state !== "completed",
                ) && (
                  <div className="resume-task">
                    <p>
                      Resume keeps completed routes and saved edits. An
                      unfinished recognition route starts again from its
                      beginning.
                    </p>
                    <button
                      className="button small"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        setError("");
                        try {
                          await api(`/jobs/${job.id}/resume`, {
                            method: "POST",
                          });
                          await refresh();
                        } catch (e) {
                          setError((e as Error).message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Resume unfinished transcription
                    </button>
                  </div>
                )}
              <ReviewPlayback
                key={job.id}
                audio={audio}
                jobId={job.id}
                deleting={deleting}
                range={repeatRange}
                stop={stopReview}
              />
              {active(job) && <TaskProgress job={job} />}
              {job.error && (
                <p role="alert" className="error">
                  {job.error}
                </p>
              )}
              <TranscriptComparison
                results={job.results}
                seek={(time) => {
                  setRepeatRange(null);
                  if (audio.current) {
                    audio.current.currentTime = time;
                    void audio.current.play().catch(() => {});
                  }
                }}
              />
              <div
                className={`results ${Object.keys(job.results).length > 1 ? "compare" : ""}`}
              >
                {Object.entries(job.results).map(([p, r]) => (
                  <Transcript
                    key={`${job.id}-${p}-${r.state}`}
                    job={job}
                    pipeline={p}
                    result={r}
                    repeating={repeatRange}
                    stopReview={stopReview}
                    repeat={(segment, index) => {
                      if (!audio.current) return;
                      setRepeatRange({
                        pipeline: p,
                        index,
                        start: segment.start,
                        end: segment.end,
                      });
                      try {
                        audio.current.currentTime = segment.start;
                        void audio.current.play().catch(() => {
                          stopReview();
                          setError(
                            "Audio could not be played. Try the original player controls.",
                          );
                        });
                      } catch {
                        stopReview();
                        setError(
                          "Audio is not ready. Wait for it to load and try again.",
                        );
                      }
                    }}
                    seek={(n) => {
                      setRepeatRange(null);
                      if (audio.current) {
                        audio.current.currentTime = n;
                        void audio.current.play().catch(() => {});
                      }
                    }}
                    saved={() => void refresh()}
                  />
                ))}
              </div>
              {!active(job) && (
                <button
                  className="button outline"
                  disabled={busy}
                  onClick={retranscribe}
                >
                  Run again with a different language or mode{" "}
                  <ArrowUpRight size={15} />
                </button>
              )}
            </div>
          )}
          <div className="bottom-notes">
            <span>
              01 <strong>Original language</strong>
              <p>Seven language targets. No automatic translation.</p>
            </span>
            <span>
              02 <strong>Your words, your edit</strong>
              <p>Review timestamps, refine text, export freely.</p>
            </span>
            <span>
              03 <strong>Honest by design</strong>
              <p>Singing can be difficult. Always check the audio.</p>
            </span>
          </div>
          <footer>
            <span>BUILT FOR CLOSE LISTENING</span>
            <span>LyricLens / Local edition</span>
          </footer>
        </div>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
