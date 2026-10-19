import { useRef, useState } from "react";

// Cap history by both count and serialized size; large transcripts retain fewer steps.
export function useHistory<T>(initial: T) {
  type History = { past: T[]; present: T; future: T[] };
  const [state, setState] = useState<History>({
    past: [],
    present: initial,
    future: [],
  });
  const latest = useRef(state);
  function update(next: History) {
    latest.current = next;
    setState(next);
  }
  function bounded(values: T[]) {
    let size = 0;
    const kept: T[] = [];
    for (const value of values.slice(-50).reverse()) {
      size += JSON.stringify(value).length;
      if (size > 2_000_000) break;
      kept.unshift(value);
    }
    return kept;
  }
  function set(value: T) {
    const old = latest.current;
    if (JSON.stringify(value) === JSON.stringify(old.present)) return;
    update({
      past: bounded([...old.past, old.present]),
      present: value,
      future: [],
    });
  }
  function undo() {
    const old = latest.current;
    if (old.past.length)
      update({
        past: old.past.slice(0, -1),
        present: old.past.at(-1)!,
        future: bounded([...old.future, old.present]),
      });
  }
  function redo() {
    const old = latest.current;
    if (old.future.length)
      update({
        past: bounded([...old.past, old.present]),
        present: old.future.at(-1)!,
        future: old.future.slice(0, -1),
      });
  }
  return {
    value: state.present,
    set,
    undo,
    redo,
    canUndo: !!state.past.length,
    canRedo: !!state.future.length,
  };
}
