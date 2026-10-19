import React, { useEffect, useState, type RefObject } from "react";

export function Waveform({
  jobId,
  audio,
  disabled,
  stop,
}: {
  jobId: string;
  audio: RefObject<HTMLAudioElement | null>;
  disabled: boolean;
  stop: () => void;
}) {
  const [data, setData] = useState<{
    duration: number;
    peaks: number[];
  } | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [position, setPosition] = useState(0);
  useEffect(() => {
    const player = audio.current;
    if (!player) return;
    const update = () => setPosition(player.currentTime);
    player.addEventListener("timeupdate", update);
    player.addEventListener("seeked", update);
    return () => {
      player.removeEventListener("timeupdate", update);
      player.removeEventListener("seeked", update);
    };
  }, [audio, jobId]);
  async function load() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/jobs/${jobId}/waveform`);
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "Waveform unavailable");
      }
      setData(await response.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="waveform">
      {!data && (
        <button
          className="text-button"
          onClick={load}
          disabled={busy || disabled}
        >
          {busy ? "Decoding waveform…" : "Load audio waveform"}
        </button>
      )}
      {data && (
        <>
          <svg
            viewBox="0 0 1200 80"
            preserveAspectRatio="none"
            role="img"
            aria-label="Original audio amplitude waveform"
          >
            <path
              d={data.peaks
                .map(
                  (value, index) =>
                    `M${(index * 1200) / data.peaks.length},${40 - value * 38}v${Math.max(0.5, value * 76)}`,
                )
                .join(" ")}
              stroke="currentColor"
            />
            <path
              d={`M${Math.min(1200, (position / data.duration) * 1200)},0v80`}
              stroke="#a34c0f"
              strokeWidth="3"
            />
          </svg>
          <label>
            Waveform position: {position.toFixed(2)} /{" "}
            {data.duration.toFixed(2)} seconds
            <input
              aria-label="Waveform position seconds"
              type="range"
              min="0"
              max={data.duration}
              step="0.01"
              value={Math.min(position, data.duration)}
              disabled={disabled}
              onChange={(event) => {
                stop();
                const value = Number(event.target.value);
                if (audio.current) audio.current.currentTime = value;
                setPosition(value);
              }}
            />
          </label>
          <p className="muted">
            Use the waveform slider or arrow keys to move through the recording.
          </p>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
