import React, { useEffect, useState, type RefObject } from "react";
import { Waveform } from "./waveform";

export type RepeatRange = {
  pipeline: string;
  index: number;
  start: number;
  end: number;
};

export function ReviewPlayback({
  audio,
  jobId,
  deleting,
  range,
  stop,
}: {
  audio: RefObject<HTMLAudioElement | null>;
  jobId: string;
  deleting: boolean;
  range: RepeatRange | null;
  stop: () => void;
}) {
  const [speed, setSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [compatible, setCompatible] = useState(false);
  useEffect(() => {
    const player = audio.current;
    if (player) {
      player.playbackRate = speed;
      player.preservesPitch = true;
    }
  }, [audio, speed]);
  useEffect(() => {
    const player = audio.current;
    if (!player || !range || !playing || deleting) return;
    const repeat = () => {
      if (
        !player.paused &&
        (player.currentTime >= range.end || player.currentTime < range.start)
      ) {
        player.currentTime = range.start;
      }
    };
    let frame = 0;
    const tick = () => {
      repeat();
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    player.addEventListener("timeupdate", repeat);
    return () => {
      cancelAnimationFrame(frame);
      player.removeEventListener("timeupdate", repeat);
    };
  }, [audio, range, playing, deleting]);
  return (
    <section className="review-playback" aria-label="Review playback">
      <audio
        ref={audio}
        controls
        src={
          deleting
            ? undefined
            : `/api/jobs/${jobId}/audio${compatible ? "?compatible=true" : ""}`
        }
        preload="metadata"
        aria-label="Original clip playback"
        onError={(event) => {
          setPlaying(false);
          const code = event.currentTarget.error?.code;
          setError(
            code === 3 || code === 4
              ? "This browser could not decode the recording. Try compatible WAV playback."
              : "Audio could not be loaded. Reload the audio or try compatible WAV playback.",
          );
        }}
        onPlay={() => {
          setPlaying(true);
          setError("");
        }}
        onPause={() => setPlaying(false)}
        onLoadedMetadata={() => {
          setError("");
          if (audio.current) {
            audio.current.playbackRate = speed;
            audio.current.preservesPitch = true;
          }
        }}
        onEnded={() => {
          if (range && audio.current && !deleting) {
            audio.current.currentTime = range.start;
            void audio.current.play().catch(() => {
              stop();
              setError("Playback stopped. Press play to listen again.");
            });
          }
        }}
      />
      <div className="review-controls">
        <button
          className="button small"
          disabled={deleting}
          onClick={() => {
            stop();
            setError("");
            audio.current?.load();
          }}
        >
          Reload audio
        </button>
        <button
          className="button small"
          disabled={deleting || compatible}
          onClick={() => {
            stop();
            setPlaying(false);
            setError("");
            setCompatible(true);
          }}
        >
          {compatible
            ? "Compatible WAV playback"
            : "Try compatible WAV playback"}
        </button>
        <label>
          Playback speed
          <select
            aria-label="Playback speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {[0.5, 0.75, 1, 1.25].map((value) => (
              <option key={value} value={value}>
                {value}×{value === 1 ? " (normal)" : ""}
              </option>
            ))}
          </select>
        </label>
        {range ? (
          <div className="repeat-status">
            <span role="status">
              Repeating segment {range.index + 1}: {range.start.toFixed(2)}–
              {range.end.toFixed(2)}s
            </span>
            <button className="button small" onClick={stop}>
              Stop repeat
            </button>
          </div>
        ) : (
          <p className="muted">
            Choose Repeat beside a transcript segment to listen in a loop.
          </p>
        )}
      </div>
      <p className="muted">
        Adjust listening speed while keeping transcript and export times.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <Waveform jobId={jobId} audio={audio} disabled={deleting} stop={stop} />
    </section>
  );
}
