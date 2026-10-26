import React from "react";
import {
  AudioLines,
  ArrowUpRight,
  Upload,
  Headphones,
  LoaderCircle,
} from "lucide-react";
import type { Models } from "./types";
import { BatchUpload } from "./batch-upload";

type UploadFormProps = {
  models: Models | null;
  file: File | null;
  preview: string;
  language: string;
  pipeline: string;
  modelProfile: string;
  reduceHallucinations: boolean;
  setReduceHallucinations: (value: boolean) => void;
  busy: boolean;
  drag: boolean;
  input: React.RefObject<HTMLInputElement | null>;
  choose: (file: File | undefined) => void;
  submit: (event: React.FormEvent) => void;
  setDrag: (drag: boolean) => void;
  setLanguage: (language: string) => void;
  setPipeline: (pipeline: string) => void;
  setModelProfile: (profile: string) => void;
};

export function UploadForm({
  models,
  file,
  preview,
  language,
  pipeline,
  modelProfile,
  reduceHallucinations,
  setReduceHallucinations,
  busy,
  drag,
  input,
  choose,
  submit,
  setDrag,
  setLanguage,
  setPipeline,
  setModelProfile,
}: UploadFormProps) {
  const chosenModelPrepared =
    models?.profiles?.find((p) => p.id === modelProfile)?.prepared ??
    models?.prepared;
  const vocalFilterProfile = ["large-v3", "aligned", "configured"].find((id) =>
    models?.profiles?.some((p) => p.id === id && p.prepared),
  );
  return (
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
          {Math.round((models?.max_bytes ?? 157286400) / 1024 / 1024)} MB max
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
      <div className="settings primary-settings">
        <label>
          Audio language
          <select
            aria-label="Audio language"
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
      </div>
      <section
        className="recognition-guidance"
        aria-label="Singing recognition settings"
      >
        <strong>Check the recognition route before transcribing</strong>
        <p className="muted">
          Selected:{" "}
          {models?.profiles?.find((p) => p.id === modelProfile)?.label ??
            modelProfile}
          {" · "}
          {pipeline === "both"
            ? "Original audio and isolated vocals"
            : pipeline === "vocals"
              ? "Isolated vocals"
              : "Original audio"}
          .
          {language === "auto"
            ? " If you know the sung language, select it above to avoid a wrong language guess."
            : " The selected language will be used for recognition."}
        </p>
        <div className="studio-toolbar">
          <button
            type="button"
            className="button small"
            disabled={
              !models?.profiles?.some((p) => p.id === "large-v3" && p.prepared)
            }
            onClick={() => {
              setModelProfile("large-v3");
              setPipeline(models?.separation_prepared ? "both" : "direct");
            }}
          >
            Try Large-v3{models?.separation_prepared ? " + compare vocals" : ""}
          </button>
          <button
            type="button"
            className="button small"
            disabled={!models?.separation_prepared || !vocalFilterProfile}
            onClick={() => {
              setModelProfile(vocalFilterProfile!);
              setPipeline("vocals");
              setReduceHallucinations(true);
            }}
          >
            Filter instrumental sections
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => {
              setModelProfile("configured");
              setPipeline("direct");
              setReduceHallucinations(false);
            }}
          >
            Use the lighter model
          </button>
        </div>
        <label>
          <input
            type="checkbox"
            checked={reduceHallucinations}
            onChange={(e) => setReduceHallucinations(e.target.checked)}
          />{" "}
          Reduce suspected hallucinations around instrumental gaps
          (experimental)
        </label>
        <p className="muted">
          Detects likely vocals conservatively, retaining three seconds of
          context and short gaps. It also uses native word alignment. It can
          skip legitimate singing; turn it off and compare if words are missing.
          Compare isolated vocals for music with strong accompaniment. The
          instrumental-filter shortcut selects isolated vocals and enables this
          protection.
        </p>
        <p className="muted">
          Large-v3 uses more time and memory. Compare the results by listening;
          vocal isolation can also distort words. Detailed model and route
          controls are below.
        </p>
      </section>
      <details className="advanced-options">
        <summary>Advanced transcription options</summary>
        <p>Adjust voice isolation and recognition model.</p>
        <div className="settings">
          <label>
            Listening mode
            <select
              aria-label="Listening mode"
              value={pipeline}
              onChange={(e) => setPipeline(e.target.value)}
            >
              <option value="direct">Original audio</option>
              <option value="vocals">Isolated vocals</option>
              <option value="both">Compare both pipelines</option>
            </select>
            <small>Vocal isolation can help, or introduce artifacts.</small>
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
              {models?.profiles?.find((p) => p.id === modelProfile)?.note ??
                "Choose a model, then review the result against the audio."}
            </small>
          </label>
        </div>
      </details>

      {models && (!chosenModelPrepared || !models.ffmpeg_available) && (
        <p className="notice">
          Setup needed: {!models.ffmpeg_available ? "install FFmpeg. " : ""}
          {!chosenModelPrepared
            ? "Prepare the transcription model using the setup guide."
            : ""}{" "}
          Processing will be available once setup is complete.
        </p>
      )}
      {pipeline !== "direct" && !models?.separation_prepared && (
        <p className="notice">
          The optional vocal model must be prepared first. Original audio mode
          works independently.
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
            !models?.ffmpeg_available ||
            (pipeline !== "direct" && !models?.separation_prepared)
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
      <BatchUpload
        reduceHallucinations={reduceHallucinations}
        language={language}
        pipeline={pipeline}
        modelProfile={modelProfile}
        ready={
          !!chosenModelPrepared &&
          !!models?.ffmpeg_available &&
          (pipeline === "direct" || !!models?.separation_prepared)
        }
      />
    </form>
  );
}
