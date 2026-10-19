import React, { useEffect, useState } from "react";
import { Elapsed } from "./progress";
import { useDraft } from "./drafts";

type Segment = { start: number; end: number; text: string; language?: string };
export type Translation = {
  state: string;
  source_language: string;
  source_languages?: string[];
  target_language: string;
  source_segments: Segment[];
  segments: Segment[];
  edited: Segment[] | null;
  source_version: string;
  stale: boolean;
  completed_segments: number;
  cancel_requested?: boolean;
  error?: string;
  warning: string;
  started_at?: string;
};
const languages: Record<string, string> = {
  ko: "Korean",
  ja: "Japanese",
  zh: "Mandarin Chinese",
  en: "English",
  es: "Spanish",
  pt: "Portuguese",
  fr: "French",
};

export function TranslationPanel({
  jobId,
  pipeline,
  translations,
  sourceLanguage,
  sourceLanguages,
  sourceDirty,
  refresh,
  seek,
}: {
  jobId: string;
  pipeline: string;
  translations: Record<string, Translation>;
  sourceLanguage: string;
  sourceLanguages: (string | undefined)[];
  sourceDirty: boolean;
  refresh: () => void;
  seek: (time: number) => void;
}) {
  const pending = Object.entries(translations).find(
    ([name, item]) =>
      name.startsWith(`${pipeline}:`) &&
      ["queued", "processing"].includes(item.state),
  )?.[1];
  const [source, setSource] = useState(
    pending?.source_language ??
      (sourceLanguage in languages ? sourceLanguage : "en"),
  );
  const [target, setTarget] = useState(
    pending?.target_language ?? (sourceLanguage === "pt" ? "en" : "pt"),
  );
  const [ready, setReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [texts, setTexts] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const current = translations[`${pipeline}:${target}`];
  const active = Object.values(translations).some((t) =>
    ["queued", "processing"].includes(t.state),
  );
  const segments = current?.edited ?? current?.segments ?? [];
  const version = JSON.stringify(segments);
  useEffect(() => {
    let canceled = false;
    fetch("/api/translation")
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((data) => {
        if (!canceled) setReady(data.prepared && data.dependencies_available);
      })
      .catch(() => {
        if (!canceled) setReady(false);
      });
    return () => {
      canceled = true;
    };
  }, []);
  useEffect(() => {
    setTexts(segments.map((s) => s.text));
    setDirty(false);
  }, [target, version]);

  async function send(path: string, body: object, method = "POST") {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/jobs/${jobId}/${path}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Translation request failed. Please retry.",
        );
      }
      if (method === "PUT") setDirty(false);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const request = {
    pipeline,
    source_language: source,
    target_language: target,
  };
  return (
    <details
      className="translation-panel"
      id={`translation-${jobId}-${pipeline}`}
    >
      <summary>Translate transcript</summary>
      <p className="muted">
        Translate your saved transcript locally. Review the wording for meaning;
        rhyme and rhythm may change. Saved language labels take priority over
        the source selection.
      </p>
      <div className="settings">
        <label>
          Translation source language
          <select
            aria-label="Translation source language"
            value={source}
            disabled={active || busy || dirty}
            onChange={(e) => {
              setSource(e.target.value);
              if (
                target === e.target.value &&
                sourceLanguages.every(
                  (lang) => !lang || lang === e.target.value,
                )
              )
                setTarget(e.target.value === "pt" ? "en" : "pt");
            }}
          >
            {Object.entries(languages).map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Translation target language
          <select
            aria-label="Translation target language"
            value={target}
            disabled={active || busy || dirty}
            onChange={(e) => setTarget(e.target.value)}
          >
            {Object.entries(languages).map(([code, name]) => (
              <option
                key={code}
                value={code}
                disabled={
                  sourceLanguages.length > 0 &&
                  sourceLanguages.every((lang) => (lang || source) === code)
                }
              >
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {ready === false && (
        <p className="notice">
          Translation needs one-time local setup. Install the optional
          translation dependencies, then run{" "}
          <code>python -m lyriclens.models translation-download</code> and
          reload this page.
        </p>
      )}
      {sourceDirty && (
        <p className="notice">
          Save transcript edits before translating or exporting a translation.
        </p>
      )}
      <button
        className="button small"
        disabled={
          !ready ||
          busy ||
          active ||
          sourceDirty ||
          dirty ||
          !sourceLanguages.length ||
          sourceLanguages.every((lang) => (lang || source) === target)
        }
        onClick={() => send("translate", request)}
      >
        {busy
          ? "Submitting…"
          : current
            ? "Translate saved text again"
            : "Translate saved text"}
      </button>
      {current && ["queued", "processing"].includes(current.state) && (
        <div role="status">
          <p>
            Translating locally: {current.completed_segments} /{" "}
            {current.source_segments.length} segments
            {" · "}
            <Elapsed
              since={current.started_at}
              active={current.state === "processing"}
            />
          </p>
          <progress
            aria-label="Translation segments completed"
            value={current.completed_segments}
            max={Math.max(1, current.source_segments.length)}
          />
          <button
            className="text-button"
            disabled={busy || current.cancel_requested}
            onClick={() => send("translation/cancel", request)}
          >
            {current.cancel_requested
              ? "Cancellation requested"
              : "Cancel translation"}
          </button>
        </div>
      )}
      {current?.error && (
        <p className="error" role="alert">
          {current.error}
        </p>
      )}
      {current && ["canceled", "interrupted"].includes(current.state) && (
        <p className="notice">
          Translation stopped. You can translate the saved text again.
        </p>
      )}
      {current &&
        ["canceled", "interrupted", "failed"].includes(current.state) &&
        !current.stale && (
          <button
            className="button small"
            disabled={busy || active || sourceDirty}
            onClick={() =>
              send("translation/resume", {
                ...request,
                source_language: current.source_language,
              })
            }
          >
            Resume translation from saved segments
          </button>
        )}
      {current?.stale && (
        <p className="notice" role="status">
          The source transcript changed. Translate again before editing or
          exporting this translation.
        </p>
      )}
      {current?.state === "completed" && (
        <>
          <p className="muted">
            {(current.source_languages ?? [current.source_language])
              .map((code) => languages[code] ?? code)
              .join(" + ")}{" "}
            → {languages[current.target_language]} · Source:{" "}
            {current.source_version} transcript
          </p>
          <p className="notice">{current.warning}</p>
          <div className="translation-rows">
            <TranslationDraft
              key={target}
              jobId={jobId}
              pipeline={pipeline}
              target={target}
              texts={texts}
              segments={segments}
              change={(value) => {
                setTexts(value);
                setDirty(true);
              }}
              enabled={!current.stale}
            />
            {current.segments.map((segment, index) => (
              <div className="translation-row" key={index}>
                <div>
                  <button
                    className="timestamp"
                    onClick={() => seek(segment.start)}
                    aria-label={`Play translated segment ${index + 1}`}
                  >
                    {segment.start.toFixed(1)}s
                  </button>
                  <p
                    className="translation-source"
                    lang={
                      current.source_segments[index]?.language ??
                      current.source_language
                    }
                  >
                    {current.source_segments[index]?.text}
                  </p>
                </div>
                <label>
                  Translated segment {index + 1}
                  <textarea
                    aria-label={`Translated segment ${index + 1}`}
                    lang={current.target_language}
                    value={texts[index] ?? ""}
                    disabled={busy || current.stale}
                    maxLength={20000}
                    onChange={(e) => {
                      const next = [...texts];
                      next[index] = e.target.value;
                      setTexts(next);
                      setDirty(true);
                    }}
                  />
                </label>
              </div>
            ))}
          </div>
          <div className="result-actions">
            <button
              className="button small"
              disabled={!dirty || busy || current.stale || sourceDirty}
              onClick={() =>
                send(
                  "translation",
                  { pipeline, target_language: target, texts },
                  "PUT",
                )
              }
            >
              {busy ? "Saving…" : "Save translation edits"}
            </button>
            {!dirty && !sourceDirty && !current.stale && (
              <details>
                <summary>Export translation</summary>
                <div className="exports">
                  {["txt", "json", "srt"].map((format) => (
                    <a
                      key={format}
                      href={`/api/jobs/${jobId}/export?pipeline=${pipeline}&translation=${target}&format=${format}`}
                    >
                      {format.toUpperCase()}
                    </a>
                  ))}
                  {["txt", "srt"].map((format) => (
                    <a
                      key={"bilingual-" + format}
                      href={`/api/jobs/${jobId}/export?pipeline=${pipeline}&translation=${target}&format=${format}&bilingual=true`}
                    >
                      Bilingual {format.toUpperCase()}
                    </a>
                  ))}
                </div>
              </details>
            )}
          </div>
          {dirty && (
            <p className="muted">
              Save translation edits before exporting or changing the target
              language.
            </p>
          )}
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}

function TranslationDraft({
  jobId,
  pipeline,
  target,
  texts,
  segments,
  change,
  enabled,
}: {
  jobId: string;
  pipeline: string;
  target: string;
  texts: string[];
  segments: Segment[];
  change: (texts: string[]) => void;
  enabled: boolean;
}) {
  return useDraft(
    `${jobId}:${pipeline}:translation:${target}`,
    texts,
    JSON.stringify(segments.map((s) => s.text)),
    change,
    (value: unknown): value is string[] =>
      Array.isArray(value) &&
      value.length === segments.length &&
      value.every((text) => typeof text === "string" && text.length <= 20000),
    enabled,
  );
}
