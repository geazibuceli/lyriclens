import { DemoStudio } from "./demo-studio";
import React, { useState, useEffect, useRef } from "react";
import {
  AudioLines,
  ArrowUpRight,
  Plus,
  Music2,
  Trash2,
  Headphones,
  X,
} from "lucide-react";
import { ReviewPlayback, type RepeatRange } from "./playback";
import { TranscriptComparison } from "./comparison";
import { WorkspaceTools } from "./workspace-tools";
import { TaskProgress } from "./progress";
import { BackupPanel } from "./backup-panel";
import type { Job, Models } from "./types";
import { active, api } from "./api";
import { Transcript } from "./transcript-editor";
import { UploadForm } from "./upload-form";
import { Library, JobTitle } from "./library";

export function App() {
  const [jobs, setJobs] = useState<Job[]>([]),
    [selected, setSelected] = useState<string | null>(
      new URLSearchParams(window.location.search).get("job"),
    ),
    [models, setModels] = useState<Models | null>(null);
  const [file, setFile] = useState<File | null>(null),
    [language, setLanguage] = useState("auto"),
    [pipeline, setPipeline] = useState("direct"),
    [modelProfile, setModelProfile] = useState("configured");
  const [reduceHallucinations, setReduceHallucinations] = useState(false);
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
      form.append("reduce_hallucinations", String(reduceHallucinations));
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
      setReduceHallucinations(
        job.inference?.hallucination_silence_threshold != null,
      );
      setLanguage(
        job.requested_language === "mixed" ? "auto" : job.requested_language,
      );
      setPipeline(
        job.pipelines.length > 1 ? "both" : (job.pipelines[0] ?? "direct"),
      );
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
        <Library jobs={jobs} selected={selected} select={setSelected} />
        <div className="local-card">
          <span className="live-dot" />
          <strong>Your audio stays yours.</strong>
          <p>Transcribe, review and export on your computer.</p>
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
            <span className="eyebrow">YOUR LOCAL LYRICS STUDIO</span>
            <h1>
              {job ? (
                "Listen. Refine. Synchronize."
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
                ? "Listen to the recording, refine the lyrics and save your edits."
                : "Turn your recordings into reviewed, synchronized lyrics."}
            </p>
          </div>
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
          {!job && <DemoStudio />}
          {!job ? (
            <UploadForm
              models={models}
              file={file}
              preview={preview}
              language={language}
              pipeline={pipeline}
              modelProfile={modelProfile}
              reduceHallucinations={reduceHallucinations}
              setReduceHallucinations={setReduceHallucinations}
              busy={busy}
              drag={drag}
              input={input}
              choose={choose}
              submit={submit}
              setDrag={setDrag}
              setLanguage={setLanguage}
              setPipeline={setPipeline}
              setModelProfile={setModelProfile}
            />
          ) : (
            <div>
              <div className="clip-bar">
                <Music2 size={21} />
                <div>
                  <strong>{job.title || job.filename}</strong>
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
              <JobTitle key={job.id} job={job} refresh={() => void refresh()} />
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
                    audio={audio}
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
          <div className="bottom-notes">
            <span>
              01 <strong>Original language</strong>
              <p>Choose from seven languages or automatic detection.</p>
            </span>
            <span>
              02 <strong>Your words, your edit</strong>
              <p>Review timestamps, refine text, export freely.</p>
            </span>
            <span>
              03 <strong>Listen and check</strong>
              <p>Replay a passage to check the words and timing.</p>
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
