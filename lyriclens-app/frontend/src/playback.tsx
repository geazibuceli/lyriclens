import React, { useEffect, useRef, useState, type RefObject } from "react";
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
  isolatedAvailable = false,
  deleting,
  range,
  stop,
}: {
  audio: RefObject<HTMLAudioElement | null>;
  jobId: string;
  isolatedAvailable?: boolean;
  deleting: boolean;
  range: RepeatRange | null;
  stop: () => void;
}) {
  const [speed, setSpeed] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [compatible, setCompatible] = useState(false);
  const [pipeline, setPipeline] = useState("direct");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const restore = useRef<{
    time: number;
    resume: boolean;
    source: string;
    applied: boolean;
  } | null>(null);
  const position = useRef(0);
  const requestedPlayback = useRef(false);
  const source = `/api/jobs/${jobId}/audio${pipeline === "vocals" ? "?pipeline=vocals" : compatible ? "?compatible=true" : ""}`;
  function remember(nextSource = source) {
    const player = audio.current;
    restore.current = {
      time: player?.currentTime || position.current,
      resume: !!player && (!player.paused || requestedPlayback.current),
      source: new URL(nextSource, window.location.href).href,
      applied: false,
    };
    setPlaying(false);
    setLoading(true);
    setError("");
  }
  function fallback() {
    remember(`/api/jobs/${jobId}/audio?compatible=true`);
    setCompatible(true);
    setNotice("Trying compatible WAV playback...");
  }
  useEffect(() => {
    if (!loading || deleting) return;
    const timer = setTimeout(() => {
      if (pipeline === "direct" && !compatible) fallback();
      else {
        setLoading(false);
        setError(
          "Audio is taking too long to load. Reload audio or switch to the original recording.",
        );
      }
    }, 15000);
    return () => clearTimeout(timer);
  }, [loading, deleting, pipeline, compatible]);
  useEffect(() => {
    if (pipeline === "vocals" && !isolatedAvailable) {
      remember(
        `/api/jobs/${jobId}/audio${compatible ? "?compatible=true" : ""}`,
      );
      setPipeline("direct");
      setNotice(
        "Isolated playback is no longer available. Returning to original audio.",
      );
    }
  }, [isolatedAvailable, pipeline]);
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
        src={deleting ? undefined : source}
        preload="metadata"
        aria-label={
          pipeline === "vocals"
            ? "Isolated vocals playback"
            : "Original clip playback"
        }
        onTimeUpdate={(event) => {
          position.current = event.currentTarget.currentTime;
        }}
        onError={() => {
          if (deleting) return;
          if (
            audio.current?.currentSrc &&
            audio.current.currentSrc !==
              new URL(source, window.location.href).href
          )
            return;
          if (pipeline === "direct" && !compatible) {
            fallback();
            return;
          }
          setPlaying(false);
          setLoading(false);
          requestedPlayback.current = false;
          setError(
            pipeline === "vocals"
              ? "Isolated audio could not be loaded. Its cache may have been cleared. Select Original audio to continue."
              : "Compatible WAV audio could not be loaded. Reload audio and check the server connection.",
          );
        }}
        onPlay={() => {
          requestedPlayback.current = true;
          setPlaying(true);
          setError("");
        }}
        onPause={() => {
          requestedPlayback.current = false;
          setPlaying(false);
        }}
        onLoadedMetadata={() => {
          if (
            audio.current?.currentSrc !==
            new URL(source, window.location.href).href
          )
            return;
          setError("");
          setLoading(false);
          if (
            audio.current &&
            audio.current.currentSrc ===
              new URL(source, window.location.href).href
          ) {
            if (restore.current)
              audio.current.currentTime = Math.min(
                restore.current.time,
                Math.max(0, audio.current.duration - 0.01),
              );
            if (restore.current) restore.current.applied = true;
            audio.current.playbackRate = speed;
            audio.current.preservesPitch = true;
          }
        }}
        onCanPlay={() => {
          const pending = restore.current;
          const player = audio.current;
          if (
            !player ||
            player.readyState < 3 ||
            player.currentSrc !== new URL(source, window.location.href).href
          )
            return;
          setLoading(false);
          if (
            pending &&
            (!pending.applied || pending.source !== player.currentSrc)
          )
            return;
          restore.current = null;
          if (compatible && pipeline === "direct")
            setNotice(
              "Playing the original recording in compatible WAV format.",
            );
          else setNotice("");
          if (pending?.resume && audio.current)
            void audio.current.play().catch(() => {
              setError(
                "Audio is ready. Press Play to resume at the saved position.",
              );
            });
        }}
        onWaiting={() => setLoading(true)}
        onStalled={() => setLoading(true)}
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
      {loading && (
        <p role="status">
          Loading {pipeline === "vocals" ? "isolated vocals" : "audio"}...
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="review-controls">
        <label>
          Audio source
          <select
            aria-label="Audio source"
            value={pipeline}
            disabled={deleting}
            onChange={(event) => {
              remember(
                `/api/jobs/${jobId}/audio${event.target.value === "vocals" ? "?pipeline=vocals" : compatible ? "?compatible=true" : ""}`,
              );
              stop();
              setNotice("");
              setPipeline(event.target.value);
            }}
          >
            <option value="direct">Original audio</option>
            <option value="vocals" disabled={!isolatedAvailable}>
              Isolated vocals
            </option>
          </select>
        </label>
        <button
          className="button small"
          disabled={deleting}
          onClick={() => {
            remember();
            stop();
            audio.current?.load();
          }}
        >
          Reload audio
        </button>
        <button
          className="button small"
          disabled={deleting || compatible || pipeline === "vocals"}
          onClick={() => {
            fallback();
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
        Switch audio sources or adjust speed while keeping the recording
        timeline. The waveform shows the original recording.
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
