import type { Segment } from "./types";

const normalize = (s: string) =>
  Array.from(
    s
      .normalize("NFKC")
      .toLocaleLowerCase()
      .replace(/[^\p{L}\p{N}]/gu, ""),
  ).join("");

// Monotonic text anchors reuse recognition timestamps. This is not acoustic forced alignment.
export function alignLyrics(
  lines: string[],
  source: Segment[],
  duration: number,
): Segment[] {
  const anchors = source.filter(
    (s) =>
      normalize(s.text) &&
      Number.isFinite(s.start) &&
      Number.isFinite(s.end) &&
      s.start >= 0 &&
      s.end > s.start &&
      s.end <= duration,
  );
  if (!anchors.length)
    throw new Error(
      "The transcript needs passages with text and valid timestamps.",
    );
  if (anchors.some((s, i) => i > 0 && s.start < anchors[i - 1].end))
    throw new Error(
      "Resolve overlapping or unordered transcript passages before suggesting timing.",
    );
  let text = "";
  const times: number[] = [];
  for (const s of anchors) {
    const chars = Array.from(normalize(s.text));
    chars.forEach((c, i) => {
      text += c;
      for (let unit = 0; unit < c.length; unit++)
        times.push(s.start + ((s.end - s.start) * i) / chars.length);
    });
  }
  // Exact normalized line anchors avoid guessing from unrelated lyrics.
  let cursor = 0;
  const starts = lines.map((line) => {
    const normalized = normalize(line);
    if (!normalized)
      throw new Error("Each line must contain letters or numbers.");
    const at = text.indexOf(normalized, cursor);
    if (at < 0)
      throw new Error(
        "Could not match every line in order. Correct the transcript or use manual synchronization.",
      );
    cursor = at + normalized.length;
    return times[at];
  });
  return lines.map((line, i) => ({
    start: starts[i],
    end: starts[i + 1] ?? anchors.at(-1)!.end,
    text: line,
  }));
}
