import React, { useMemo, useState, type RefObject } from "react";
import { Download, Check, X, Languages } from "lucide-react";
import { TranslationPanel, type Translation } from "./translation";
import { ReviewPlayback, type RepeatRange } from "./playback";
import { useHistory } from "./history";
import { reviewFlags } from "./review-flags";
import { useDraft, validSegments } from "./drafts";
import { SegmentTools } from "./segment-tools";
import type { Segment, Result, Job, Models } from "./types";
import { api, clock } from "./api";
import { RegionRetry } from "./region-retry";
import { ListeningStudio, useAudioTime } from "./listening-studio";
import { LyricsImport } from "./lyrics-import";

export function Transcript({
  job,
  pipeline,
  result,
  seek,
  saved,
  repeat,
  repeating,
  stopReview,
  audio,
  models,
}: {
  models: Models | null;
  audio: RefObject<HTMLAudioElement | null>;
  job: Job;
  pipeline: string;
  result: Result;
  seek: (n: number) => void;
  saved: () => void;
  repeat: (segment: Segment, index: number) => void;
  repeating: RepeatRange | null;
  stopReview: () => void;
}) {
  const time = useAudioTime(audio);
  const history = useHistory<Segment[]>(result.edited ?? result.original ?? []);
  const segments = history.value,
    setSegments = history.set;
  const [savedVersion, setSavedVersion] = useState(JSON.stringify(segments));
  const dirty = JSON.stringify(segments) !== savedVersion;
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [multilingualBusy, setMultilingualBusy] = useState(false);
  const [query, setQuery] = useState("");
  const savedTranslation = Object.entries(job.translations ?? {}).find(
    ([key, t]) =>
      key.startsWith(`${pipeline}:`) && t.state === "completed" && !t.stale,
  )?.[1];
  const flags = useMemo(
    () => segments.map((_, i) => reviewFlags(segments, i, job.audio?.duration)),
    [segments, job.audio?.duration],
  );
  const reviewQueue = flags.flatMap((reasons, index) =>
    reasons.length ? [{ index, reasons }] : [],
  );
  function visitSegment(index: number) {
    document
      .getElementById(`segment-${job.id}-${pipeline}-${index}`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
    document
      .querySelector<HTMLTextAreaElement>(
        `#segment-${job.id}-${pipeline}-${index} textarea`,
      )
      ?.focus({ preventScroll: true });
    seek(segments[index].start);
  }
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
        if (
          (event.target as HTMLElement).closest(
            ".translation-panel, .lyrics-import",
          )
        )
          return;
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
      <LyricsImport
        segments={segments}
        duration={job.audio?.duration ?? 0}
        disabled={saving || result.state !== "completed"}
        apply={(imported) => {
          stopReview();
          setSegments(imported);
        }}
      />
      <details className="review-queue">
        <summary>Review suggestions ({reviewQueue.length} passages)</summary>
        <p className="muted">
          Suggestions update as you edit. They are checks to make while
          listening, not confidence scores; repeated lyrics may be intentional.
        </p>
        {reviewQueue.length === 0 ? (
          <p>No automatic suggestions. Listen through to check the words.</p>
        ) : (
          <ul>
            {reviewQueue.map(({ index, reasons }) => (
              <li key={index}>
                <button
                  className="text-button"
                  onClick={() => visitSegment(index)}
                >
                  Review segment {index + 1}: {reasons.join("; ")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </details>
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
      <RegionRetry
        job={job}
        pipeline={pipeline}
        segments={segments}
        models={models}
      />
      <div className="multilingual-controls">
        <p className="muted">
          For songs with multiple languages, choose each passage's language,
          adjust its boundaries and save before retranscribing.
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
      <ListeningStudio
        audio={audio}
        segments={segments}
        change={setSegments}
        translation={
          dirty
            ? undefined
            : (savedTranslation?.edited ?? savedTranslation?.segments)
        }
      />
      <div className="segments">
        {segments.map((s, i) => (
          <div
            className={`segment ${time >= s.start && time < s.end ? "segment-active" : ""}`}
            key={i}
            aria-current={time >= s.start && time < s.end ? "true" : undefined}
          >
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
              {flags[i].map((flag) => (
                <p className="review-flag" key={flag}>
                  Review suggestion: {flag}. Listen to this passage to check.
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
            {["txt", "json", "srt", "lrc"].map((format) => (
              <a
                key={format}
                aria-disabled={dirty || saving}
                href={
                  dirty || saving
                    ? undefined
                    : `/api/jobs/${job.id}/export?pipeline=${pipeline}&format=${format}`
                }
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
