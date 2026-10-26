import { useRef, useState } from "react";
import { ListeningStudio } from "./listening-studio";
import type { Segment } from "./types";
import demo from "../public/demo/transcript.json";

export function DemoStudio() {
  const [open, setOpen] = useState(false);
  const [segments, setSegments] = useState<Segment[]>(demo);
  const audio = useRef<HTMLAudioElement>(null);
  function download() {
    const text = segments
      .map((s) => {
        const hundredths = Math.round(s.start * 100);
        return `[${String(Math.floor(hundredths / 6000)).padStart(2, "0")}:${((hundredths % 6000) / 100).toFixed(2).padStart(5, "0")}]${s.text}`;
      })
      .join("\n");
    const url = URL.createObjectURL(
      new Blob([text], { type: "text/plain;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "lyriclens-demo.lrc";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section className="demo-card">
      <span className="eyebrow">LISTEN → REVIEW → SYNC → EXPORT</span>
      <h2>Try the studio before downloading models</h2>
      <p>
        Original text narrated by a synthetic voice. Explore editing and
        synchronization with prepared audio; this demo does not measure singing
        recognition.
      </p>
      <button className="button small" onClick={() => setOpen(!open)}>
        {open ? "Close demo" : "Open interactive demo"}
      </button>
      {open && (
        <DemoEditor
          audio={audio}
          segments={segments}
          change={setSegments}
          download={download}
        />
      )}
    </section>
  );
}

function DemoEditor({
  audio,
  segments,
  change,
  download,
}: {
  audio: React.RefObject<HTMLAudioElement | null>;
  segments: Segment[];
  change: (s: Segment[]) => void;
  download: () => void;
}) {
  return (
    <div className="demo-editor">
      <audio
        ref={audio}
        controls
        src="/demo/voice.wav"
        aria-label="Synthetic voice demo audio"
      />
      <ListeningStudio audio={audio} segments={segments} change={change} />
      {segments.map((s, i) => (
        <label key={i}>
          Line {i + 1}
          <textarea
            aria-label={`Line ${i + 1}`}
            value={s.text}
            maxLength={20000}
            onChange={(e) =>
              change(
                segments.map((line, j) =>
                  j === i ? { ...line, text: e.target.value } : line,
                ),
              )
            }
          />
        </label>
      ))}
      <div className="studio-toolbar">
        <button className="button small" onClick={download}>
          Export demo LRC
        </button>
        <button className="button small" onClick={() => change(demo)}>
          Reset example
        </button>
      </div>
      <p className="muted">Demo changes stay in this session only.</p>
    </div>
  );
}
