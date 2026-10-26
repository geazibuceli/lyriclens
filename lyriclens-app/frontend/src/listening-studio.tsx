import { useEffect, useRef, useState, type RefObject } from "react";
import type { Segment } from "./types";

export function useAudioTime(audio: RefObject<HTMLAudioElement | null>) {
  const [time, setTime] = useState(-1);
  useEffect(() => {
    const player = audio.current;
    if (!player) return;
    const update = () => setTime(player.currentTime);
    update();
    player.addEventListener("timeupdate", update);
    player.addEventListener("seeked", update);
    return () => {
      player.removeEventListener("timeupdate", update);
      player.removeEventListener("seeked", update);
    };
  }, [audio]);
  return time;
}

export function ListeningStudio({
  audio,
  segments,
  change,
  translation,
}: {
  audio: RefObject<HTMLAudioElement | null>;
  segments: Segment[];
  change: (segments: Segment[]) => void;
  translation?: Segment[];
}) {
  const time = useAudioTime(audio);
  const [open, setOpen] = useState(false);
  const [bilingual, setBilingual] = useState(false);
  const [next, setNext] = useState(0);
  const [message, setMessage] = useState("");
  const root = useRef<HTMLElement>(null);
  const current = segments.findIndex((s) => time >= s.start && time < s.end);
  function stamp() {
    const player = audio.current;
    if (!player || next >= segments.length) return;
    const t = player.currentTime;
    const previous = segments[next - 1];
    const end = player.duration;
    if (
      !Number.isFinite(end) ||
      t < 0 ||
      end - t < (segments.length - next) * 0.01 ||
      (previous && t <= previous.start)
    ) {
      setMessage(
        "Choose a time after the previous line and before the end of the audio.",
      );
      return;
    }
    const step = (end - t) / (segments.length - next);
    change(
      segments.map((s, i) =>
        i >= next
          ? {
              ...s,
              start: t + (i - next) * step,
              end: t + (i - next + 1) * step,
            }
          : i === next - 1
            ? { ...s, end: t }
            : s,
      ),
    );
    setNext(next + 1);
    setMessage("Timing marked. Save edits to update exports.");
  }
  return (
    <section
      ref={root}
      className={`listening-studio ${open ? "focus-open" : ""}`}
      aria-label="Listening studio"
    >
      <div className="studio-toolbar">
        <button
          className="button small"
          onClick={() => {
            if (open && document.fullscreenElement === root.current)
              void document.exitFullscreen().catch(() => {});
            setOpen(!open);
          }}
        >
          {open ? "Close listening view" : "Follow lyrics"}
        </button>
        {open && (
          <>
            <button
              className="button small"
              onClick={() => {
                if (document.fullscreenElement)
                  void document
                    .exitFullscreen()
                    .catch(() => setMessage("Could not exit fullscreen."));
                else
                  void root.current
                    ?.requestFullscreen?.()
                    .catch(() =>
                      setMessage("Fullscreen is unavailable in this browser."),
                    );
              }}
            >
              Fullscreen
            </button>
            <button
              className="button small"
              onClick={() => {
                const player = audio.current;
                if (player) {
                  if (player.paused)
                    void player
                      .play()
                      .catch(() =>
                        setMessage("Use the player to start audio."),
                      );
                  else player.pause();
                }
              }}
            >
              Play / pause
            </button>
            {translation && (
              <label>
                <input
                  type="checkbox"
                  checked={bilingual}
                  onChange={(e) => setBilingual(e.target.checked)}
                />{" "}
                Show saved translation
              </label>
            )}
          </>
        )}
      </div>
      {open && (
        <div className="lyric-stage" aria-label="Synchronized lyrics">
          <p className="lyric-neighbor">
            {current >= 0 ? segments[current - 1]?.text : ""}
          </p>
          <p className="lyric-current">
            {current >= 0 ? segments[current].text : "♪"}
          </p>
          {bilingual && current >= 0 && (
            <p>
              {translation?.find((s) => time >= s.start && time < s.end)?.text}
            </p>
          )}
          <p className="lyric-neighbor">
            {
              segments[
                current >= 0
                  ? current + 1
                  : segments.findIndex((s) => s.start > time)
              ]?.text
            }
          </p>
        </div>
      )}
      <details>
        <summary>Tap to synchronize</summary>
        <p>
          Listen and mark the start of each line. Unmarked lines are
          redistributed until you mark them. Undo restores previous timing in
          the editor.
        </p>
        <label>
          Next line{" "}
          <select
            aria-label="Next line"
            value={Math.min(next, segments.length)}
            onChange={(e) => setNext(Number(e.target.value))}
          >
            {segments.map((s, i) => (
              <option key={i} value={i}>
                {i + 1}. {s.text.slice(0, 65)}
              </option>
            ))}
            <option value={segments.length}>Finished</option>
          </select>
        </label>
        <button
          className="button small"
          disabled={next >= segments.length}
          onClick={stamp}
        >
          Mark start now
        </button>
      </details>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
