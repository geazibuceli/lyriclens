# Listening studio

Open **Open interactive demo** on the upload page to try editing, playback,
synchronization and LRC export without preparing a model. The demo uses original
English text and a synthetic speaking voice. It does not demonstrate singing
recognition quality. Changes stay in the current browser session.

For your own recordings, the original player stays visible while you edit.
Use **Audio source** to switch between **Original audio** and **Isolated vocals**
when a completed full-recording vocal result is available. Switching preserves
the playback position, speed and playing/paused state, and stops segment repeat.
The lyric-following view continues using the same recording timeline. Cropped
vocal results are excluded when they do not cover that timeline. Clearing generated
cache removes isolated playback files; use the original or run separation again.

If the original format fails to load, the player automatically tries a compatible
WAV once, preserving the listening position. A loading indicator and final error
replace silent failures; **Reload audio** retries the current source. Browsers
that block automatic resumption show a prompt to press Play. The waveform always
shows the original recording, regardless of the selected playback source.

The current passage is highlighted as playback moves. Each recognition route
has its own **Follow lyrics** view, using that editor's current text, including
unsaved changes. Gaps display a musical note rather than a stale lyric.

Use **Play / pause** and **Fullscreen** in the listening view. A completed,
non-stale saved translation for the same route can be displayed beside the
source. It is hidden when source text has unsaved changes. If multiple target
translations exist, the first matching saved translation is used.

## Synchronize imported lyrics

1. Import TXT or LRC in the transcript editor.
2. Select **Suggest timing from the existing transcript** to associate normalized
   lyric lines with the recognized text in order. Repeated lines match later
   occurrences. Punctuation and letter case are ignored; letter accents remain.
3. Inspect the preview and apply. All lines must match; mismatches are reported
   without changing the editor. Overlapping source passages must be resolved.
4. Open **Tap to synchronize**, play the audio and press **Mark start now** at
   each line's beginning. Choose **Next line** to resume at a particular line.
   The previous line ends at that instant; future lines are temporarily
   distributed through the remaining recording until you mark them.
5. Use undo/redo or the existing timestamp fields to refine boundaries. Save
   edits, then export LRC, SRT, TXT or JSON.

Suggested timing reuses ASR segment boundaries and interpolates character
positions. It is not acoustic forced alignment and cannot repair an incorrect
transcript automatically. Uniform line distribution remains available for
lyrics that differ substantially from recognition.

## Verification

Run `npm.cmd run test:studio` and `npm.cmd run build` in `frontend`.
With the frontend running, execute `scripts/studio_browser_smoke.py` using a
Python environment with Playwright and Chromium installed. It exercises the
bundled demo and the actual editor with deterministic API fixtures, including
mobile overflow, playback highlighting, import, save, undo and downloaded LRC.
It also records the README video and screenshot. These fixture checks do not
validate real inference quality.
