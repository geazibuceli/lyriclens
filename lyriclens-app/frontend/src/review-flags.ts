export function reviewFlags(
  segments: { start: number; end: number; text: string }[],
  index: number,
  duration?: number,
) {
  const segment = segments[index];
  const text = segment.text.trim();
  const flags: string[] = [];
  if (
    !Number.isFinite(segment.start) ||
    !Number.isFinite(segment.end) ||
    segment.start < 0 ||
    segment.end <= segment.start ||
    (duration !== undefined && segment.end > duration)
  )
    flags.push("Invalid timing: keep start and end within the clip");
  if (index > 0 && segment.start < segments[index - 1].start)
    flags.push("Passage starts before the previous passage");
  if (!text) flags.push("Empty passage: add words or remove this segment");
  if (segment.end - segment.start > 20)
    flags.push("Long passage: review words and timing");
  if (index > 0 && text && text === segments[index - 1].text.trim())
    flags.push("Same text as previous passage: check against audio");
  // Bound pattern length and inspected text; avoid expensive regex backtracking.
  const sample = text.slice(0, 2000);
  let repeated = false;
  for (let width = 8; width <= 64 && !repeated; width++) {
    for (let start = 0; start + width * 3 <= sample.length; start++) {
      const pattern = sample.slice(start, start + width);
      if (
        sample.startsWith(pattern, start + width) &&
        sample.startsWith(pattern, start + width * 2)
      ) {
        repeated = true;
        break;
      }
    }
  }
  if (repeated)
    flags.push(
      "Repeated text pattern: may be a chorus or a recognition repetition",
    );
  return flags;
}
