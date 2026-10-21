# Drafts, segment editing, bilingual exports and job backups

## Browser drafts

Transcript and translation text changes are stored automatically in this browser profile after a 300 ms pause. A best-effort flush also runs when leaving the page. After reloading or reopening a job, choose **Restore browser draft** or **Discard browser draft**. Restoring changes the editor only. **Save edits** or **Save translation edits** still updates the server, exports and backups.

Drafts are stored per job, route and translation target in the current browser. Conflicting saved changes produce a notice; stale translations need regeneration before draft restoration. Drafts exclude undo history and backups, and stay local to the browser without encryption or synchronization. Clearing browser storage, private mode, quota limits or an abrupt crash can lose a draft. Each draft is capped at two million serialized characters, subject to the browser quota. Save edits to keep a server copy.

## Search and segment boundaries

The library searches recording titles and original filenames with Unicode normalization and case-insensitive matching. Filter by job status or requested language. Filters affect the library list, not the open editor. **Rename recording** saves a display title; leaving it blank restores the filename display. Renaming preserves the original file, transcript and audio hash, and titles travel with job backups.

Each route has **Search transcript**, which searches saved or unsaved text using Unicode NFC and case-insensitive matching while retaining accents. Matching buttons scroll to the segment and seek the original audio. Search does not change text or locate exact word times.

Open **Split or merge segment N**. Choose an interior split time and a text cut separately. The preview shows the cut; no forced alignment is inferred. Text positions count Unicode code points, preserving surrogate pairs but not guaranteeing complete grapheme clusters. Both new segments inherit the original language and can then be relabeled. There is a maximum of 1000 segments.

**Merge segment N with next** requires ordered, nonoverlapping segments with the same language. It spans the first start to the next end, includes any intervening gap and joins the texts with a newline. Different-language segments must remain separate or be relabeled explicitly first. Merged text is limited to 20000 characters. Split/merge changes participate in undo/redo and browser drafts; save them before retranscription, translation or export. Neither operation rewrites the original recognition output.

## Review suggestions and synchronized lyrics

### Import lyrics

Open **Import lyrics (TXT / LRC)** in a completed transcript. Paste text or choose a UTF-8 TXT/LRC file up to 2 MB, then choose:

- **Keep current passage times:** one nonempty line per existing passage. Language labels and times are preserved.
- **Distribute lines evenly:** creates approximate passages across the recording for manual synchronization. This does not align words to audio or infer passage languages.
- **Use timestamps from LRC:** reads `[mm:ss]`, `[mm:ss.xx]` or millisecond timestamps. Repeated tags are expanded, entries are sorted and text at the same time is combined. A blank timestamp ends the preceding passage. Common descriptive metadata is ignored; offset and enhanced word-timestamp formats are unsupported.

The preview shows the passage count and first five passages. **Apply imported lyrics** replaces the editor as one undoable change; it preserves the original recognition output. Review timing, then save edits. Imports are limited to 1000 passages and 20000 characters per passage; invalid or out-of-bounds timestamps are rejected.

### Review and export

Open **Review suggestions** above the transcript to navigate passages with empty text, invalid or unordered times, long duration or repeated text. Selecting a suggestion seeks the audio and focuses the passage editor. Suggestions update with unsaved edits and are listening prompts, not model confidence scores. Repeated choruses may be correct.

Save edits before exporting. The transcript's current-version export links are unavailable while edits are unsaved. Original TXT and raw responses remain available independently.

Choose **LRC** under **Export** for synchronized lyrics. Each nonempty line receives its passage's start time, rounded to centiseconds (`[mm:ss.xx]`). Multiline passages share a timestamp; LRC has no end times or word-level timing. API: `GET /api/jobs/{id}/export?pipeline=direct&format=lrc`.

## Bilingual exports

After saving a current translation, open **Export translation** and choose **Bilingual TXT** or **Bilingual SRT**. Each block contains the saved source followed by the translation. SRT uses the source timings. Regenerate translations after changing source text, language labels or segment boundaries.

API: `GET /api/jobs/{id}/export?pipeline=direct&translation=pt&bilingual=true&format=srt`. Bilingual mode supports TXT and SRT; missing translations, stale source or unavailable alignment are rejected.

## Backup and restore

Open **Backup and restore a job**. Stop active work and save edits, then download the selected job's `.lyriclens.zip` archive. It includes the byte-identical original recording, saved original/edited results, translations, raw responses where present, model identifiers/revisions and job configuration. It excludes model weights, decoded audio/stems, browser drafts, environments and the entire library database. Back up each job separately. Archives can contain private recordings and text and are not encrypted.

Choose the archive under **Job backup ZIP**, then **Restore as a separate job**. The importer checks format/version, allowed members, metadata, recording size/SHA-256, segment timing and translation alignment. It rejects duplicate/linked members, arbitrary paths, encrypted ZIPs and oversized content. Entries are copied by known names; archive paths are never extracted. Existing jobs are not replaced and imported active states become interrupted. No model download or recognition starts during restoration.

Imported ASR snapshots cannot resume recognition automatically from supplied model settings. Upload the restored original as a new recognition job if needed; saved transcript/translation editing and exports remain available. A valid stopped translation checkpoint can resume against its preserved source with the explicitly prepared local translation model.

Original recording size and duration must fit the configured application limits (default 150 MiB / 600 seconds). Job metadata and each optional raw response are limited to 32 MiB; the restore body limit adds bounded archive/multipart overhead. Backups created from another installation with larger limits may be rejected. Raw responses are retained as diagnostic data, not executed. Keep the source archive until the restored job is checked.

API: `GET /api/jobs/{id}/backup` downloads one stopped job; `POST /api/backups/restore` accepts a multipart `file` and creates a new UUID. Models must be prepared separately after moving to another machine.

## Continuous checks

The GitHub workflow runs backend tests, frontend formatting and the production build. A Chromium job checks editing, recovery, waveform, storage and playback using temporary data and silence recordings. It uploads logs and screenshots. Run real-model evaluations separately with prepared checkpoints.

Run the same isolated browser workflow locally with installed dependencies and Playwright Chromium:

```powershell
.\.venv\Scripts\python.exe lyriclens-app/scripts/ci_browser.py --backend-port 8013 --frontend-port 5183
```

Default CI ports are 8011/5181. Occupied ports are rejected without stopping existing services; the runner terminates only processes it created. The smoke scripts support `LYRICLENS_BROWSER_URL` for isolated test servers. Local Chromium runs passed desktop/mobile layouts and axe WCAG A/AA checks. These checks do not establish singing accuracy or replace assistive-technology review.
