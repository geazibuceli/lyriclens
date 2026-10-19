import React, { useEffect, useRef, useState } from "react";

type Draft<T> = { version: 1; base: string; value: T; at: string };
export function useDraft<T>(
  key: string,
  value: T,
  base: string,
  restore: (value: T) => void,
  valid: (value: unknown) => value is T,
  enabled = true,
) {
  const storageKey = "lyriclens:draft:v1:" + key;
  const [pending, setPending] = useState<Draft<T> | null>(() => {
    try {
      const item = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      return item?.version === 1 &&
        typeof item.base === "string" &&
        valid(item.value)
        ? item
        : null;
    } catch {
      return null;
    }
  });
  const [error, setError] = useState(""),
    [savedAt, setSavedAt] = useState("");
  const serialized = JSON.stringify(value);
  const latest = useRef({ value, base, serialized, pending, enabled });
  latest.current = { value, base, serialized, pending, enabled };
  function persist() {
    const current = latest.current;
    if (!current.enabled || current.pending) return;
    try {
      if (current.serialized === current.base) {
        localStorage.removeItem(storageKey);
        setError("");
        setSavedAt("");
        return;
      }
      const at = new Date().toISOString();
      const data = JSON.stringify({
        version: 1,
        base: current.base,
        value: current.value,
        at,
      });
      if (data.length > 2_000_000)
        throw new Error("Draft is too large for browser storage");
      localStorage.setItem(storageKey, data);
      setSavedAt(at);
      setError("");
    } catch {
      setError(
        "Browser draft could not be stored. Save your edits to the job before leaving this page.",
      );
    }
  }
  useEffect(() => {
    const timer = setTimeout(persist, 300);
    return () => clearTimeout(timer);
  }, [storageKey, serialized, base, pending, enabled]);
  useEffect(() => {
    const flush = () => persist();
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);
    return () => {
      flush();
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("beforeunload", flush);
    };
  }, [storageKey]);
  return (
    <div className="draft-status">
      {pending && (
        <div className="notice">
          <p>
            A browser draft is available.{" "}
            {pending.base !== base
              ? "The saved source changed; restoring replaces this editor draft. Review before saving."
              : "Your saved job is unchanged until you save edits."}
          </p>
          <button
            className="button small"
            disabled={!enabled}
            onClick={() => {
              restore(pending.value);
              setPending(null);
            }}
          >
            Restore browser draft
          </button>{" "}
          <button
            className="text-button"
            onClick={() => {
              try {
                localStorage.removeItem(storageKey);
              } catch {}
              setPending(null);
            }}
          >
            Discard browser draft
          </button>
        </div>
      )}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : savedAt && serialized !== base ? (
        <p className="muted">
          Browser draft saved at {new Date(savedAt).toLocaleTimeString()}. Use
          Save edits to update exports and backups.
        </p>
      ) : null}
    </div>
  );
}
export function validSegments(value: unknown): value is {
  start: number;
  end: number;
  text: string;
  language?: string;
  language_source?: string;
}[] {
  return (
    Array.isArray(value) &&
    value.length <= 1000 &&
    value.every(
      (s) =>
        s &&
        typeof s === "object" &&
        Number.isFinite(s.start) &&
        Number.isFinite(s.end) &&
        typeof s.text === "string" &&
        s.text.length <= 20000 &&
        (s.language === undefined ||
          ["ko", "ja", "zh", "en", "es", "pt", "fr"].includes(s.language)) &&
        (s.language_source === undefined ||
          s.language_source === "user instruction"),
    )
  );
}
